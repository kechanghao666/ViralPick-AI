from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from backend.permissions import has_permission
from backend.repositories import brand_repository


DEFAULT_BRAND = {
    "brand_name": "ViralPick AI",
    "report_label": "店铺经营分析报告",
    "logo_url": "",
    "primary_color": "#00a99d",
    "accent_color": "#f0a51b",
    "cover_style": "signal-grid",
}

LEGACY_REPORT_LABELS = {
    "Commerce " + "Intelligence " + "Brief",
    "店铺" + "智能" + "经营分析报告",
}

COVER_STYLES = {
    "signal-grid": "信号网格",
    "executive-dark": "深色高管版",
    "editorial-light": "浅色刊物版",
}


class BrandError(Exception):
    status_code = 400


class PermissionDenied(BrandError):
    status_code = 403


def get_brand_settings(actor: dict[str, Any]) -> dict[str, Any]:
    row = brand_repository.get_brand_settings(actor["workspace_id"])
    return {
        **_settings_from_row(row, actor["workspace_id"]),
        "can_manage": has_permission(actor, "brand.manage"),
        "cover_styles": [{"value": value, "label": label} for value, label in COVER_STYLES.items()],
    }


def get_brand_for_workspace(workspace_id: str | None) -> dict[str, Any]:
    workspace = str(workspace_id or "").strip()
    if not workspace:
        return {**DEFAULT_BRAND, "workspace_id": None, "is_default": True}
    return _settings_from_row(brand_repository.get_brand_settings(workspace), workspace)


def update_brand_settings(actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not has_permission(actor, "brand.manage"):
        raise PermissionDenied("Missing brand.manage permission")
    current = _settings_from_row(brand_repository.get_brand_settings(actor["workspace_id"]), actor["workspace_id"])
    validated = _validate_payload(payload, current)
    now = _now_iso()
    brand_repository.upsert_brand_settings(
        {
            **validated,
            "workspace_id": actor["workspace_id"],
            "updated_by": actor.get("user_id"),
            "created_at": current.get("created_at") or now,
            "updated_at": now,
        }
    )
    return get_brand_settings(actor)


def _settings_from_row(row: dict[str, Any] | None, workspace_id: str | None) -> dict[str, Any]:
    if not row:
        return {
            **DEFAULT_BRAND,
            "workspace_id": workspace_id,
            "updated_by": None,
            "created_at": None,
            "updated_at": None,
            "is_default": True,
        }
    return {
        "workspace_id": row.get("workspace_id"),
        "brand_name": row.get("brand_name") or DEFAULT_BRAND["brand_name"],
        "report_label": _normalize_report_label(row.get("report_label")),
        "logo_url": row.get("logo_url") or "",
        "primary_color": row.get("primary_color") or DEFAULT_BRAND["primary_color"],
        "accent_color": row.get("accent_color") or DEFAULT_BRAND["accent_color"],
        "cover_style": row.get("cover_style") or DEFAULT_BRAND["cover_style"],
        "updated_by": row.get("updated_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "is_default": False,
    }


def _normalize_report_label(value: Any) -> str:
    label = str(value or "").strip()
    if not label or label in LEGACY_REPORT_LABELS:
        return DEFAULT_BRAND["report_label"]
    return label


def _validate_payload(payload: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    brand_name = _clean_text(payload.get("brand_name", current["brand_name"]), "brand_name", 2, 60)
    report_label = _clean_text(payload.get("report_label", current["report_label"]), "report_label", 2, 80)
    logo_url = _validate_logo_url(payload.get("logo_url", current.get("logo_url") or ""))
    primary_color = _validate_color(payload.get("primary_color", current["primary_color"]), "primary_color")
    accent_color = _validate_color(payload.get("accent_color", current["accent_color"]), "accent_color")
    cover_style = str(payload.get("cover_style", current["cover_style"]) or "").strip()
    if cover_style not in COVER_STYLES:
        raise BrandError(f"cover_style must be one of {', '.join(COVER_STYLES)}")
    return {
        "brand_name": brand_name,
        "report_label": report_label,
        "logo_url": logo_url,
        "primary_color": primary_color,
        "accent_color": accent_color,
        "cover_style": cover_style,
    }


def _clean_text(value: Any, field: str, min_length: int, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) < min_length or len(text) > max_length:
        raise BrandError(f"{field} must be between {min_length} and {max_length} characters")
    return text


def _validate_color(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", text):
        raise BrandError(f"{field} must be a hex color such as #00a99d")
    return text.lower()


def _validate_logo_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BrandError("logo_url must be an http(s) URL or blank")
    if len(text) > 500:
        raise BrandError("logo_url must be 500 characters or fewer")
    return text


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
