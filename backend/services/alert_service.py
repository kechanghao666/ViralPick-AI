from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests

from backend.config import (
    ALERT_MIN_SEVERITY,
    ALERT_TIMEOUT_SECONDS,
    ALERT_WEBHOOK_URL,
    ALERTS_ENABLED,
    APP_ENV,
    APP_NAME,
    APP_VERSION,
)


SEVERITY_RANK = {"info": 1, "warn": 2, "critical": 3}


class AlertError(Exception):
    status_code = 400


def get_status() -> dict[str, Any]:
    parsed = urlparse(ALERT_WEBHOOK_URL) if ALERT_WEBHOOK_URL else None
    return {
        "enabled": ALERTS_ENABLED,
        "configured": bool(ALERT_WEBHOOK_URL),
        "provider": "webhook",
        "endpoint_host": parsed.netloc if parsed else "",
        "min_severity": _normalise_severity(ALERT_MIN_SEVERITY),
        "timeout_seconds": ALERT_TIMEOUT_SECONDS,
    }


def dispatch_monitoring_alerts(
    monitoring: dict[str, Any],
    actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = get_status()
    matched_alerts = _filter_alerts(monitoring.get("alerts") or [], status["min_severity"])
    payload = _build_payload(monitoring, matched_alerts, actor)
    if not matched_alerts:
        return {
            "sent": False,
            "reason": "no_matching_alerts",
            "status": status,
            "matched_alerts": [],
            "payload_preview": _payload_preview(payload),
        }
    if not status["enabled"]:
        return {
            "sent": False,
            "reason": "disabled",
            "status": status,
            "matched_alerts": matched_alerts,
            "payload_preview": _payload_preview(payload),
        }
    if not status["configured"]:
        return {
            "sent": False,
            "reason": "not_configured",
            "status": status,
            "matched_alerts": matched_alerts,
            "payload_preview": _payload_preview(payload),
        }

    try:
        response = requests.post(ALERT_WEBHOOK_URL, json=payload, timeout=ALERT_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise AlertError(f"Alert webhook request failed: {exc}") from exc
    if response.status_code >= 400:
        raise AlertError(f"Alert webhook returned HTTP {response.status_code}")

    return {
        "sent": True,
        "reason": "sent",
        "status": status,
        "matched_alerts": matched_alerts,
        "response": {"status_code": response.status_code},
        "payload_preview": _payload_preview(payload),
    }


def _filter_alerts(alerts: list[dict[str, Any]], min_severity: str) -> list[dict[str, Any]]:
    threshold = SEVERITY_RANK[_normalise_severity(min_severity)]
    return [
        alert
        for alert in alerts
        if SEVERITY_RANK.get(str(alert.get("severity") or "info"), 1) >= threshold
        and alert.get("code") != "all_clear"
    ]


def _build_payload(
    monitoring: dict[str, Any],
    alerts: list[dict[str, Any]],
    actor: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "event": "viralpick.monitoring.alerts",
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "environment": APP_ENV,
        },
        "generated_at": monitoring.get("generated_at"),
        "dispatched_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "health_state": monitoring.get("health_state"),
        "summary": monitoring.get("summary") or {},
        "alerts": alerts,
        "actor": {
            "user_id": actor.get("user_id") if actor else None,
            "email": actor.get("email") if actor else None,
            "role": actor.get("role") if actor else None,
        },
    }


def _payload_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": payload.get("event"),
        "health_state": payload.get("health_state"),
        "alert_count": len(payload.get("alerts") or []),
        "alert_codes": [item.get("code") for item in payload.get("alerts") or []],
    }


def _normalise_severity(value: str | None) -> str:
    severity = str(value or "warn").lower().strip()
    return severity if severity in SEVERITY_RANK else "warn"
