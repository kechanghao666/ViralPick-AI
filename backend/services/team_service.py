from __future__ import annotations

import re
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from werkzeug.security import generate_password_hash

from backend.permissions import ROLE_LABELS, has_permission, role_matrix
from backend.repositories import team_repository


ROLES = {"owner", "admin", "analyst", "viewer"}
STATUSES = {"active", "suspended"}
MAX_INVITE_DAYS = 30
DEFAULT_INVITE_DAYS = 7


class TeamError(Exception):
    status_code = 400


class PermissionDenied(TeamError):
    status_code = 403


class NotFound(TeamError):
    status_code = 404


def list_members(actor: dict[str, Any]) -> dict[str, Any]:
    members = team_repository.list_workspace_members(actor["workspace_id"])
    return {
        "workspace": {
            "workspace_id": actor["workspace_id"],
            "workspace_name": actor["workspace_name"],
            "plan": actor["plan"],
        },
        "current_user_role": actor["role"],
        "can_manage": _can_manage(actor),
        "roles": role_matrix(),
        "items": [_public_member(member) for member in members],
    }


def list_invitations(actor: dict[str, Any], limit: int = 50) -> dict[str, Any]:
    _require_manager(actor)
    safe_limit = max(1, min(100, int(limit or 50)))
    invitations = team_repository.list_invitations(actor["workspace_id"], limit=safe_limit)
    return {
        "workspace_id": actor["workspace_id"],
        "can_manage": _can_manage(actor),
        "items": [_public_invitation(invitation) for invitation in invitations],
    }


def create_invitation(actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    _require_manager(actor)
    email = _normalize_email(payload.get("email"))
    display_name = str(payload.get("display_name") or "").strip() or email.split("@")[0]
    role = _validate_role(payload.get("role") or "analyst")
    days = _validate_invite_days(payload.get("expires_in_days"))
    if len(display_name) > 80:
        raise TeamError("display_name must be 80 characters or fewer")
    _ensure_role_assignable(actor, role)
    if team_repository.get_member_by_email(email):
        raise TeamError("email already exists")

    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    invitation = {
        "invitation_id": f"INV-{uuid4().hex[:14]}",
        "workspace_id": actor["workspace_id"],
        "email": email,
        "display_name": display_name,
        "role": role,
        "token_hash": _hash_token(token),
        "token_preview": token[-8:],
        "invited_by": actor["user_id"],
        "created_at": _to_iso(now),
        "expires_at": _to_iso(now + timedelta(days=days)),
        "accepted_at": None,
        "revoked_at": None,
    }
    team_repository.create_invitation(invitation)
    return {**_public_invitation(invitation), "invite_token": token}


def revoke_invitation(actor: dict[str, Any], invitation_id: str) -> dict[str, Any]:
    _require_manager(actor)
    invitation = team_repository.get_invitation(actor["workspace_id"], invitation_id)
    if not invitation:
        raise NotFound(f"Invitation not found: {invitation_id}")
    if not invitation.get("accepted_at") and not invitation.get("revoked_at"):
        team_repository.revoke_invitation(actor["workspace_id"], invitation_id, _now_iso())
        invitation = team_repository.get_invitation(actor["workspace_id"], invitation_id) or invitation
    return _public_invitation(invitation)


def get_invitation_by_token(invite_token: str) -> dict[str, Any]:
    invitation = _valid_invitation(invite_token)
    return _public_invitation_detail(invitation)


def accept_invitation(invite_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    invitation = _valid_invitation(invite_token)
    password = str(payload.get("password") or "")
    password_confirm = str(payload.get("password_confirm") or payload.get("confirm_password") or "")
    display_name = str(payload.get("display_name") or invitation.get("display_name") or "").strip()
    if len(password) < 8:
        raise TeamError("password must be at least 8 characters")
    if password_confirm and password != password_confirm:
        raise TeamError("password confirmation does not match")
    if not display_name:
        raise TeamError("display_name cannot be empty")
    if len(display_name) > 80:
        raise TeamError("display_name must be 80 characters or fewer")
    if team_repository.get_member_by_email(invitation["email"]):
        raise TeamError("email already exists")

    user_id = f"U-{uuid4().hex[:16]}"
    accepted_at = _now_iso()
    team_repository.create_member(
        user_id=user_id,
        workspace_id=invitation["workspace_id"],
        email=invitation["email"],
        password_hash=generate_password_hash(password),
        display_name=display_name,
        role=invitation["role"],
        status="active",
        created_at=accepted_at,
    )
    team_repository.mark_invitation_accepted(invitation["invitation_id"], accepted_at)
    member = team_repository.get_member(invitation["workspace_id"], user_id) or {}
    return {
        "member": _public_member(member),
        "workspace": {
            "workspace_id": invitation.get("workspace_id"),
            "workspace_name": invitation.get("workspace_name"),
            "plan": invitation.get("plan"),
        },
    }


def create_member(actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    _require_manager(actor)
    email = _normalize_email(payload.get("email"))
    display_name = str(payload.get("display_name") or "").strip() or email.split("@")[0]
    role = _validate_role(payload.get("role") or "analyst")
    password = str(payload.get("password") or "")
    if len(display_name) > 80:
        raise TeamError("display_name must be 80 characters or fewer")
    if len(password) < 8:
        raise TeamError("password must be at least 8 characters")
    _ensure_role_assignable(actor, role)
    if team_repository.get_member_by_email(email):
        raise TeamError("email already exists")

    user_id = f"U-{uuid4().hex[:16]}"
    team_repository.create_member(
        user_id=user_id,
        workspace_id=actor["workspace_id"],
        email=email,
        password_hash=generate_password_hash(password),
        display_name=display_name,
        role=role,
        status="active",
        created_at=_now_iso(),
    )
    member = team_repository.get_member(actor["workspace_id"], user_id)
    return _public_member(member or {})


def update_member(actor: dict[str, Any], user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _require_manager(actor)
    member = team_repository.get_member(actor["workspace_id"], user_id)
    if not member:
        raise NotFound(f"Member not found: {user_id}")

    role = _validate_role(payload.get("role")) if "role" in payload else None
    status = _validate_status(payload.get("status")) if "status" in payload else None
    display_name = str(payload.get("display_name")).strip() if "display_name" in payload else None
    if display_name is not None and not display_name:
        raise TeamError("display_name cannot be empty")
    if display_name is not None and len(display_name) > 80:
        raise TeamError("display_name must be 80 characters or fewer")
    if role:
        _ensure_role_assignable(actor, role)
    _ensure_member_manageable(actor, member, role=role, status=status)

    team_repository.update_member(
        workspace_id=actor["workspace_id"],
        user_id=user_id,
        display_name=display_name,
        role=role,
        status=status,
    )
    updated = team_repository.get_member(actor["workspace_id"], user_id)
    return _public_member(updated or {})


def _require_manager(actor: dict[str, Any]) -> None:
    if not _can_manage(actor):
        raise PermissionDenied("Missing team.manage permission")


def _can_manage(actor: dict[str, Any]) -> bool:
    return has_permission(actor, "team.manage")


def _ensure_role_assignable(actor: dict[str, Any], role: str) -> None:
    if actor.get("role") == "owner":
        return
    if role in {"owner", "admin"}:
        raise PermissionDenied("Only owner can assign owner or admin roles")


def _ensure_member_manageable(
    actor: dict[str, Any],
    member: dict[str, Any],
    role: str | None = None,
    status: str | None = None,
) -> None:
    if actor["user_id"] == member["user_id"] and (role is not None or status == "suspended"):
        raise TeamError("You cannot change your own role or suspend yourself")
    if actor.get("role") != "owner" and member.get("role") in {"owner", "admin"}:
        raise PermissionDenied("Only owner can manage owner or admin members")


def _normalize_email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise TeamError("valid email is required")
    return email


def _validate_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    if role not in ROLES:
        raise TeamError("role must be one of owner, admin, analyst, or viewer")
    return role


def _validate_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status not in STATUSES:
        raise TeamError("status must be active or suspended")
    return status


def _validate_invite_days(value: Any) -> int:
    if value in {None, ""}:
        return DEFAULT_INVITE_DAYS
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise TeamError("expires_in_days must be an integer") from exc
    if days < 1 or days > MAX_INVITE_DAYS:
        raise TeamError(f"expires_in_days must be between 1 and {MAX_INVITE_DAYS}")
    return days


def _valid_invitation(invite_token: str) -> dict[str, Any]:
    token = str(invite_token or "").strip()
    if len(token) < 16:
        raise NotFound("Invitation not found")
    invitation = team_repository.get_invitation_by_token_hash(_hash_token(token))
    if not invitation:
        raise NotFound("Invitation not found")
    if invitation.get("workspace_status") != "active":
        raise TeamError("Workspace is not active")
    if invitation.get("accepted_at"):
        raise TeamError("Invitation has already been accepted")
    if invitation.get("revoked_at"):
        raise TeamError("Invitation has been revoked")
    expires_at = _parse_time(invitation.get("expires_at"))
    if expires_at and expires_at <= datetime.now(UTC):
        raise TeamError("Invitation has expired")
    return invitation


def _public_member(member: dict[str, Any]) -> dict[str, Any]:
    role = member.get("role")
    return {
        "user_id": member.get("user_id"),
        "workspace_id": member.get("workspace_id"),
        "email": member.get("email"),
        "display_name": member.get("display_name"),
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        "capabilities": next((item["capabilities"] for item in role_matrix() if item["role"] == role), []),
        "status": member.get("status"),
        "created_at": member.get("created_at"),
        "last_login_at": member.get("last_login_at"),
    }


def _public_invitation(invitation: dict[str, Any]) -> dict[str, Any]:
    status = _invitation_status(invitation)
    role = invitation.get("role")
    return {
        "invitation_id": invitation.get("invitation_id"),
        "workspace_id": invitation.get("workspace_id"),
        "email": invitation.get("email"),
        "display_name": invitation.get("display_name"),
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        "token_preview": invitation.get("token_preview"),
        "status": status,
        "invited_by": invitation.get("invited_by"),
        "created_at": invitation.get("created_at"),
        "expires_at": invitation.get("expires_at"),
        "accepted_at": invitation.get("accepted_at"),
        "revoked_at": invitation.get("revoked_at"),
    }


def _public_invitation_detail(invitation: dict[str, Any]) -> dict[str, Any]:
    public = _public_invitation(invitation)
    public["workspace"] = {
        "workspace_id": invitation.get("workspace_id"),
        "workspace_name": invitation.get("workspace_name"),
        "plan": invitation.get("plan"),
    }
    return public


def _invitation_status(invitation: dict[str, Any]) -> str:
    if invitation.get("accepted_at"):
        return "accepted"
    if invitation.get("revoked_at"):
        return "revoked"
    expires_at = _parse_time(invitation.get("expires_at"))
    if expires_at and expires_at <= datetime.now(UTC):
        return "expired"
    return "pending"


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _to_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
