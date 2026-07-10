from __future__ import annotations

from backend.services import alert_service, ops_service


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def _login(client) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "demo@viralpick.ai", "password": "ViralPick@2026"},
    )
    assert response.status_code == 200
    return _json(response)["data"]["access_token"]


def _monitoring_fixture(severity: str = "warn") -> dict:
    return {
        "generated_at": "2026-06-30T00:00:00Z",
        "health_state": "warn" if severity == "warn" else "critical",
        "summary": {"critical": 1 if severity == "critical" else 0, "warn": 1 if severity == "warn" else 0},
        "metrics": [],
        "alerts": [
            {
                "code": "backup_missing",
                "severity": severity,
                "title": "尚未创建数据库备份",
                "message": "建议创建备份。",
                "metadata": {},
            }
        ],
    }


def test_owner_can_read_alert_status(client):
    token = _login(client)
    response = client.get("/api/ops/alerts/status", headers={"Authorization": f"Bearer {token}"})
    payload = _json(response)

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["provider"] == "webhook"
    assert "enabled" in payload["data"]
    assert "configured" in payload["data"]


def test_dispatch_alerts_returns_disabled_without_network_call(client, monkeypatch):
    token = _login(client)
    monkeypatch.setattr(alert_service, "ALERTS_ENABLED", False)
    monkeypatch.setattr(alert_service, "ALERT_WEBHOOK_URL", "")
    monkeypatch.setattr(alert_service, "ALERT_MIN_SEVERITY", "warn")
    monkeypatch.setattr(ops_service, "get_monitoring", lambda actor: _monitoring_fixture("warn"))

    response = client.post("/api/ops/alerts/dispatch", headers={"Authorization": f"Bearer {token}"})
    payload = _json(response)

    assert response.status_code == 200
    assert payload["data"]["sent"] is False
    assert payload["data"]["reason"] == "disabled"
    assert len(payload["data"]["matched_alerts"]) == 1
    assert payload["data"]["payload_preview"]["alert_codes"] == ["backup_missing"]


def test_dispatch_alerts_posts_configured_webhook(client, monkeypatch):
    token = _login(client)
    recorded = {}

    class FakeResponse:
        status_code = 204

    def fake_post(url, json, timeout):
        recorded["url"] = url
        recorded["json"] = json
        recorded["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(alert_service, "ALERTS_ENABLED", True)
    monkeypatch.setattr(alert_service, "ALERT_WEBHOOK_URL", "https://alerts.example.test/webhook")
    monkeypatch.setattr(alert_service, "ALERT_MIN_SEVERITY", "critical")
    monkeypatch.setattr(alert_service, "ALERT_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(alert_service.requests, "post", fake_post)
    monkeypatch.setattr(ops_service, "get_monitoring", lambda actor: _monitoring_fixture("critical"))

    response = client.post("/api/ops/alerts/dispatch", headers={"Authorization": f"Bearer {token}"})
    payload = _json(response)

    assert response.status_code == 200
    assert payload["data"]["sent"] is True
    assert payload["data"]["response"]["status_code"] == 204
    assert recorded["url"] == "https://alerts.example.test/webhook"
    assert recorded["timeout"] == 3
    assert recorded["json"]["alerts"][0]["severity"] == "critical"
