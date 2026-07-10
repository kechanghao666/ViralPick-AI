from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from werkzeug.security import check_password_hash, generate_password_hash

from backend.config import AUTH_LOCKOUT_MINUTES, AUTH_MAX_FAILED_ATTEMPTS, AUTH_TOKEN_TTL_HOURS
from backend.repositories import auth_repository


class AuthenticationError(Exception):
    pass


class AuthenticationLockedError(AuthenticationError):
    status_code = 423


class RegistrationError(AuthenticationError):
    status_code = 400


def register(
    email: str,
    password: str,
    display_name: str | None = None,
    workspace_name: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    clean_password = str(password or "")
    clean_display_name = str(display_name or "").strip() or normalized_email.split("@")[0]
    clean_workspace_name = str(workspace_name or "").strip() or f"{clean_display_name}的经营空间"
    if len(clean_password) < 8:
        raise RegistrationError("password must be at least 8 characters")
    if len(clean_display_name) > 80:
        raise RegistrationError("display_name must be 80 characters or fewer")
    if len(clean_workspace_name) > 80:
        raise RegistrationError("workspace_name must be 80 characters or fewer")
    if auth_repository.get_user_by_email(normalized_email):
        raise RegistrationError("email already exists")

    now = _to_iso(_now())
    workspace_id = f"W-{uuid4().hex[:16]}"
    user_id = f"U-{uuid4().hex[:16]}"
    auth_repository.create_workspace_with_owner(
        workspace_id=workspace_id,
        workspace_name=clean_workspace_name,
        user_id=user_id,
        email=normalized_email,
        password_hash=generate_password_hash(clean_password),
        display_name=clean_display_name,
        plan="business-trial",
        created_at=now,
    )
    session = login(normalized_email, clean_password, ip_address=ip_address)
    audit(
        action="auth.register",
        user=session["user"],
        resource_type="workspace",
        resource_id=workspace_id,
        metadata={"workspace_name": clean_workspace_name},
        ip_address=ip_address,
    )
    return session


def login(email: str, password: str, ip_address: str | None = None) -> dict[str, Any]:
    normalized_email = email.strip()
    user = auth_repository.get_user_by_email(normalized_email)
    if not user or user.get("status") != "active":
        _audit_failed_login(user, "unknown_or_inactive", ip_address, normalized_email)
        raise AuthenticationError("Invalid email or password")
    if _is_locked(user):
        audit(
            action="auth.login_locked",
            user=_public_user(user),
            resource_type="user",
            resource_id=user.get("user_id"),
            metadata={"locked_until": user.get("locked_until")},
            ip_address=ip_address,
        )
        raise AuthenticationLockedError("Account is temporarily locked due to repeated failed login attempts")
    if not check_password_hash(user["password_hash"], password):
        locked_until = _record_failed_login(user, ip_address)
        if locked_until:
            raise AuthenticationLockedError("Account is temporarily locked due to repeated failed login attempts")
        raise AuthenticationError("Invalid email or password")

    now = _now()
    expires_at = now + timedelta(hours=AUTH_TOKEN_TTL_HOURS)
    raw_token = secrets.token_urlsafe(32)
    token_id = f"T-{uuid4().hex[:16]}"
    auth_repository.create_token(
        token_id=token_id,
        user_id=user["user_id"],
        token_hash=_hash_token(raw_token),
        token_name="web-session",
        created_at=_to_iso(now),
        expires_at=_to_iso(expires_at),
    )
    auth_repository.reset_failed_logins(user["user_id"])
    auth_repository.touch_login(user["user_id"], _to_iso(now))
    audit(
        action="auth.login",
        user=_public_user(user),
        resource_type="session",
        resource_id=token_id,
        metadata={"token_name": "web-session"},
        ip_address=ip_address,
    )
    return {
        "access_token": raw_token,
        "token_type": "Bearer",
        "expires_at": _to_iso(expires_at),
        "user": _public_user(user),
    }


def authenticate_bearer(authorization_header: str | None) -> dict[str, Any] | None:
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    row = auth_repository.get_token_user(_hash_token(token))
    if not row or row.get("revoked_at") or row.get("status") != "active":
        return None
    try:
        expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    if expires_at <= _now():
        return None
    auth_repository.touch_token(row["token_id"], _to_iso(_now()))
    return _public_user(row)


def logout(authorization_header: str | None, ip_address: str | None = None) -> bool:
    token = _extract_token(authorization_header)
    if not token:
        return False
    token_hash = _hash_token(token)
    user = auth_repository.get_token_user(token_hash)
    changed = auth_repository.revoke_token(token_hash, _to_iso(_now()))
    if user:
        audit(
            action="auth.logout",
            user=_public_user(user),
            resource_type="session",
            resource_id=user.get("token_id"),
            metadata={},
            ip_address=ip_address,
        )
    return changed > 0


def _is_locked(user: dict[str, Any]) -> bool:
    locked_until = user.get("locked_until")
    if not locked_until:
        return False
    try:
        return datetime.fromisoformat(str(locked_until).replace("Z", "+00:00")) > _now()
    except ValueError:
        return False


def _record_failed_login(user: dict[str, Any], ip_address: str | None) -> str | None:
    failed_count = int(user.get("failed_login_count") or 0) + 1
    locked_until = None
    if AUTH_MAX_FAILED_ATTEMPTS > 0 and failed_count >= AUTH_MAX_FAILED_ATTEMPTS:
        locked_until = _to_iso(_now() + timedelta(minutes=max(1, AUTH_LOCKOUT_MINUTES)))
    auth_repository.record_failed_login(user["user_id"], failed_count, locked_until)
    audit(
        action="auth.login_failed",
        user=_public_user(user),
        resource_type="user",
        resource_id=user.get("user_id"),
        metadata={
            "reason": "bad_password",
            "failed_login_count": failed_count,
            "locked": bool(locked_until),
            "locked_until": locked_until,
        },
        ip_address=ip_address,
    )
    return locked_until


def _audit_failed_login(
    user: dict[str, Any] | None,
    reason: str,
    ip_address: str | None,
    email: str,
) -> None:
    metadata = {"reason": reason, "email_hash": _hash_token(email.lower()) if email else None}
    audit(
        action="auth.login_failed",
        user=_public_user(user) if user else None,
        resource_type="user",
        resource_id=user.get("user_id") if user else None,
        metadata=metadata,
        ip_address=ip_address,
    )


def _normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise RegistrationError("valid email is required")
    return email


def audit(
    action: str,
    user: dict[str, Any] | None,
    resource_type: str,
    resource_id: str | None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    auth_repository.insert_audit_log(
        audit_id=f"A-{uuid4().hex[:18]}",
        workspace_id=user.get("workspace_id") if user else None,
        user_id=user.get("user_id") if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        ip_address=ip_address,
        created_at=_to_iso(_now()),
    )


def _extract_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user["user_id"],
        "workspace_id": user["workspace_id"],
        "workspace_name": user["workspace_name"],
        "plan": user["plan"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


def _now() -> datetime:
    return datetime.now(UTC)


def _to_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
