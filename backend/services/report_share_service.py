from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.repositories import report_share_repository
from backend.services import brand_service, report_service


MAX_SHARE_DAYS = 90
DEFAULT_SHARE_DAYS = 14


class ReportShareError(Exception):
    status_code = 400


class ReportShareNotFound(ReportShareError):
    status_code = 404


class ReportShareGone(ReportShareError):
    status_code = 410


def create_share(report_id: str, actor: dict[str, Any], expires_in_days: int | None = None) -> dict[str, Any] | None:
    report = report_service.get_report(report_id)
    if not report:
        return None
    days = _valid_days(expires_in_days)
    token = secrets.token_urlsafe(24)
    now = _now()
    share = {
        "share_id": f"S-{uuid4().hex[:12]}",
        "report_id": report_id,
        "workspace_id": actor.get("workspace_id"),
        "created_by": actor.get("user_id"),
        "token_hash": _token_hash(token),
        "token_preview": token[-8:],
        "permission": "view",
        "expires_at": (now + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "revoked_at": None,
        "created_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "last_accessed_at": None,
        "access_count": 0,
    }
    report_share_repository.create_share(share)
    public_share = _public_share(share)
    public_share["share_token"] = token
    return public_share


def list_shares(report_id: str, actor: dict[str, Any]) -> dict[str, Any] | None:
    report = report_service.get_report(report_id)
    if not report:
        return None
    rows = report_share_repository.list_shares(report_id, actor.get("workspace_id"))
    return {
        "report_id": report_id,
        "items": [_public_share(row) for row in rows],
    }


def revoke_share(share_id: str, actor: dict[str, Any]) -> dict[str, Any]:
    share = report_share_repository.get_share(share_id)
    if not share or (share.get("workspace_id") and share.get("workspace_id") != actor.get("workspace_id")):
        raise ReportShareNotFound(f"Report share not found: {share_id}")
    if not share.get("revoked_at"):
        report_share_repository.revoke_share(share_id, _now().isoformat(timespec="seconds").replace("+00:00", "Z"))
        share = report_share_repository.get_share(share_id) or share
    return _public_share(share)


def get_shared_report(share_token: str, access_context: dict[str, Any] | None = None) -> dict[str, Any]:
    token = str(share_token or "").strip()
    if len(token) < 16:
        raise ReportShareNotFound("Share link not found")
    share = report_share_repository.get_share_by_token_hash(_token_hash(token))
    if not share:
        raise ReportShareNotFound("Share link not found")
    status = _share_status(share)
    if status == "revoked":
        raise ReportShareGone("Share link has been revoked")
    if status == "expired":
        raise ReportShareGone("Share link has expired")
    report = report_service.get_report(share["report_id"])
    if not report:
        raise ReportShareNotFound("Shared report not found")
    accessed_at = _now().isoformat(timespec="seconds").replace("+00:00", "Z")
    report_share_repository.record_access(share["share_id"], accessed_at)
    report_share_repository.record_access_event(_access_event(share, accessed_at, access_context or {}))
    share = report_share_repository.get_share(share["share_id"]) or share
    public_share = _public_share(share)
    brand = brand_service.get_brand_for_workspace(share.get("workspace_id"))
    return {
        "report": report,
        "share": public_share,
        "presentation": _presentation(report, public_share, brand),
    }


def list_share_access_logs(share_id: str, actor: dict[str, Any], page: int = 1, page_size: int = 20) -> dict[str, Any]:
    share = report_share_repository.get_share(share_id)
    if not share or (share.get("workspace_id") and share.get("workspace_id") != actor.get("workspace_id")):
        raise ReportShareNotFound(f"Report share not found: {share_id}")
    safe_page = max(1, int(page or 1))
    safe_size = max(1, min(100, int(page_size or 20)))
    offset = (safe_page - 1) * safe_size
    summary = report_share_repository.access_summary(share_id, actor.get("workspace_id"))
    total = int(summary.get("total") or 0)
    rows = report_share_repository.list_access_logs(
        share_id,
        workspace_id=actor.get("workspace_id"),
        limit=safe_size,
        offset=offset,
    )
    return {
        "share": _public_share(share),
        "summary": {
            "total": total,
            "unique_visitors": int(summary.get("unique_visitors") or 0),
            "latest_accessed_at": summary.get("latest_accessed_at"),
        },
        "items": [_public_access_log(row) for row in rows],
        "pagination": {
            "page": safe_page,
            "page_size": safe_size,
            "total": total,
            "total_pages": max(1, (total + safe_size - 1) // safe_size),
        },
    }


def _valid_days(value: int | None) -> int:
    if value is None:
        return DEFAULT_SHARE_DAYS
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ReportShareError("expires_in_days must be an integer") from exc
    if days < 1 or days > MAX_SHARE_DAYS:
        raise ReportShareError(f"expires_in_days must be between 1 and {MAX_SHARE_DAYS}")
    return days


def _public_share(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "share_id": row.get("share_id"),
        "report_id": row.get("report_id"),
        "token_preview": row.get("token_preview"),
        "permission": row.get("permission", "view"),
        "status": _share_status(row),
        "expires_at": row.get("expires_at"),
        "revoked_at": row.get("revoked_at"),
        "created_at": row.get("created_at"),
        "last_accessed_at": row.get("last_accessed_at"),
        "access_count": int(row.get("access_count") or 0),
    }


def _public_access_log(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "access_id": row.get("access_id"),
        "share_id": row.get("share_id"),
        "accessed_at": row.get("accessed_at"),
        "visitor_hash": row.get("visitor_hash"),
        "user_agent": row.get("user_agent") or "",
        "referrer": row.get("referrer") or "",
    }


def _presentation(report: dict[str, Any], share: dict[str, Any], brand: dict[str, Any]) -> dict[str, Any]:
    sections = report.get("sections") or []
    highlights = []
    for section in sections[:4]:
        content = str(section.get("content") or "").strip()
        highlights.append(
            {
                "heading": section.get("heading") or "分析结论",
                "summary": content[:120] + ("..." if len(content) > 120 else ""),
            }
        )
    scope_label = "全局经营分析"
    if report.get("product_id"):
        scope_label = f"单品分析 · {report.get('product_id')}"
    elif report.get("category"):
        scope_label = f"品类分析 · {report.get('category')}"
    ai_generation = report.get("ai_generation") or {}
    return {
        "brand": brand.get("brand_name") or brand_service.DEFAULT_BRAND["brand_name"],
        "label": brand.get("report_label") or brand_service.DEFAULT_BRAND["report_label"],
        "logo_url": brand.get("logo_url") or "",
        "primary_color": brand.get("primary_color") or brand_service.DEFAULT_BRAND["primary_color"],
        "accent_color": brand.get("accent_color") or brand_service.DEFAULT_BRAND["accent_color"],
        "cover_style": brand.get("cover_style") or brand_service.DEFAULT_BRAND["cover_style"],
        "title": report.get("title") or "店铺经营分析报告",
        "scope_label": scope_label,
        "generated_at": report.get("generated_at"),
        "expires_at": share.get("expires_at"),
        "access_count": share.get("access_count", 0),
        "status": share.get("status"),
        "section_count": len(sections),
        "ai_status": ai_generation.get("status") or "rule_template",
        "ai_message": ai_generation.get("message"),
        "highlights": highlights,
        "data_disclaimer": report.get("data_disclaimer"),
    }


def _share_status(row: dict[str, Any]) -> str:
    if row.get("revoked_at"):
        return "revoked"
    expires_at = _parse_time(row.get("expires_at"))
    if expires_at and expires_at <= _now():
        return "expired"
    return "active"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _access_event(share: dict[str, Any], accessed_at: str, context: dict[str, Any]) -> dict[str, Any]:
    ip_address = str(context.get("ip_address") or "").strip() or "unknown"
    user_agent = _truncate(context.get("user_agent"), 220)
    referrer = _truncate(context.get("referrer"), 420)
    return {
        "access_id": f"A-{uuid4().hex[:16]}",
        "share_id": share["share_id"],
        "workspace_id": share.get("workspace_id"),
        "accessed_at": accessed_at,
        "visitor_hash": hashlib.sha256(f"{share['share_id']}|{ip_address}".encode("utf-8")).hexdigest()[:16],
        "user_agent": user_agent,
        "referrer": referrer,
    }


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _now() -> datetime:
    return datetime.now(UTC)
