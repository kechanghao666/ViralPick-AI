from __future__ import annotations


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def _login(client, email: str = "demo@viralpick.ai", password: str = "ViralPick@2026") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    payload = _json(response)
    assert response.status_code == 200
    return payload["data"]["access_token"]


def test_audit_logs_require_authentication(client):
    response = client.get("/api/audit/logs")
    payload = _json(response)
    assert response.status_code == 401
    assert payload["success"] is False


def test_owner_can_view_audit_logs_and_filter_by_action(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    report = client.post("/api/reports/generate", json={"product_id": "P0001"}, headers=headers)
    assert report.status_code == 201

    logs = client.get("/api/audit/logs?page=1&page_size=10", headers=headers)
    payload = _json(logs)
    assert logs.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["items"]
    assert payload["data"]["summary"]["total"] >= len(payload["data"]["items"])
    assert payload["data"]["filters"]["actions"]

    filtered = client.get("/api/audit/logs?action=report.generate", headers=headers)
    filtered_payload = _json(filtered)
    assert filtered.status_code == 200
    assert filtered_payload["data"]["items"]
    assert all(item["action"] == "report.generate" for item in filtered_payload["data"]["items"])
    assert all(item["action_label"] == "生成报告" for item in filtered_payload["data"]["items"])
    assert all(item["resource_label"] == "经营报告" for item in filtered_payload["data"]["items"])


def test_non_admin_cannot_view_audit_logs(client):
    owner_token = _login(client)
    create = client.post(
        "/api/team/members",
        json={
            "email": "audit-analyst@example.com",
            "display_name": "审计受限分析师",
            "password": "Audit@2026",
            "role": "analyst",
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert create.status_code == 201

    analyst_token = _login(client, "audit-analyst@example.com", "Audit@2026")
    response = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {analyst_token}"})
    payload = _json(response)
    assert response.status_code == 403
    assert payload["success"] is False
