from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.permissions import has_permission
from backend.repositories import scoring_model_repository


SCORING_WEIGHT_KEYS = [
    "sales_growth",
    "gmv_growth",
    "positive_rate",
    "comment_heat",
    "price_competitiveness",
    "video_interaction",
    "conversion_rate",
]
DEFAULT_WEIGHTS = {
    "sales_growth": 0.20,
    "gmv_growth": 0.20,
    "positive_rate": 0.15,
    "comment_heat": 0.10,
    "price_competitiveness": 0.15,
    "video_interaction": 0.15,
    "conversion_rate": 0.05,
}
WEIGHT_LABELS = {
    "sales_growth": "销量增长率",
    "gmv_growth": "销售额增长率",
    "positive_rate": "好评率",
    "comment_heat": "评论热度",
    "price_competitiveness": "价格竞争力",
    "video_interaction": "内容运营互动",
    "conversion_rate": "转化率",
}


class ScoringModelError(Exception):
    status_code = 400


class PermissionDenied(ScoringModelError):
    status_code = 403


def get_active_model(workspace_id: str | None = None) -> dict[str, Any]:
    row = scoring_model_repository.get_active_model(workspace_id)
    if row:
        return _public_model(row)
    return {
        "model_id": "SM-RUNTIME-DEFAULT",
        "workspace_id": workspace_id,
        "model_name": "多平台电商默认评分模型",
        "weights": DEFAULT_WEIGHTS,
        "weight_labels": WEIGHT_LABELS,
        "status": "active",
        "note": "运行时默认模型。建议初始化数据库后使用 scoring_models 表记录版本。",
        "created_by": None,
        "created_at": None,
        "activated_at": None,
    }


def list_models(actor: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    rows = scoring_model_repository.list_models(actor.get("workspace_id"), limit=limit)
    return {
        "active_model": get_active_model(actor.get("workspace_id")),
        "items": [_public_model(row) for row in rows],
        "weight_labels": WEIGHT_LABELS,
        "can_manage": has_permission(actor, "scoring.manage"),
    }


def create_model(payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    _require_manage(actor)
    weights = _validate_weights(payload.get("weights") or {})
    now = _now_iso()
    model = {
        "model_id": f"SM-{uuid4().hex[:12]}",
        "workspace_id": actor.get("workspace_id"),
        "model_name": str(payload.get("model_name") or "自定义爆品评分模型").strip()[:80],
        "weights_json": json.dumps(weights, ensure_ascii=False),
        "status": "active",
        "note": str(payload.get("note") or "").strip()[:300],
        "created_by": actor.get("user_id"),
        "created_at": now,
        "activated_at": now,
    }
    scoring_model_repository.archive_active_models(actor.get("workspace_id"), now)
    scoring_model_repository.create_model(model)
    return _public_model(model)


def _require_manage(actor: dict[str, Any]) -> None:
    if not has_permission(actor, "scoring.manage"):
        raise PermissionDenied("Permission denied")


def _validate_weights(raw_weights: dict[str, Any]) -> dict[str, float]:
    missing = [key for key in SCORING_WEIGHT_KEYS if key not in raw_weights]
    extra = [key for key in raw_weights if key not in SCORING_WEIGHT_KEYS]
    if missing:
        raise ScoringModelError(f"缺少评分权重：{', '.join(missing)}")
    if extra:
        raise ScoringModelError(f"不支持的评分权重：{', '.join(extra)}")
    weights: dict[str, float] = {}
    for key in SCORING_WEIGHT_KEYS:
        try:
            value = float(raw_weights[key])
        except (TypeError, ValueError) as exc:
            raise ScoringModelError(f"{key} must be numeric") from exc
        if value < 0:
            raise ScoringModelError(f"{key} must be greater than or equal to 0")
        weights[key] = round(value, 4)
    total = round(sum(weights.values()), 4)
    if abs(total - 1.0) > 0.001:
        raise ScoringModelError("评分权重之和必须等于 1")
    return weights


def _public_model(row: dict[str, Any]) -> dict[str, Any]:
    weights = row.get("weights")
    if not weights:
        try:
            weights = json.loads(row.get("weights_json") or "{}")
        except json.JSONDecodeError:
            weights = DEFAULT_WEIGHTS
    return {
        "model_id": row.get("model_id"),
        "workspace_id": row.get("workspace_id"),
        "model_name": row.get("model_name"),
        "weights": {key: round(float(weights.get(key, 0)), 4) for key in SCORING_WEIGHT_KEYS},
        "weight_labels": WEIGHT_LABELS,
        "status": row.get("status", "active"),
        "note": row.get("note"),
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "activated_at": row.get("activated_at"),
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
