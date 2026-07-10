from __future__ import annotations

from uuid import uuid4


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def _login(client, email: str = "demo@viralpick.ai", password: str = "ViralPick@2026") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return _json(response)["data"]["access_token"]


def _create_member(client, role: str) -> tuple[str, str]:
    token = _login(client)
    suffix = uuid4().hex[:8]
    email = f"perm-{role}-{suffix}@example.com"
    password = f"Perm{suffix}@2026"
    response = client.post(
        "/api/team/members",
        json={
            "email": email,
            "display_name": f"权限测试 {role}",
            "password": password,
            "role": role,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return email, password


def test_auth_permissions_endpoint_returns_role_matrix(client):
    token = _login(client)
    response = client.get("/api/auth/permissions", headers={"Authorization": f"Bearer {token}"})
    payload = _json(response)

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["role"] == "owner"
    assert "ops.manage" in payload["data"]["permissions"]
    assert "reports.generate" in payload["data"]["permissions"]
    assert {item["role"] for item in payload["data"]["matrix"]} == {"owner", "admin", "analyst", "viewer"}


def test_viewer_can_read_team_and_reports_but_cannot_write(client):
    email, password = _create_member(client, "viewer")
    viewer_token = _login(client, email, password)
    headers = {"Authorization": f"Bearer {viewer_token}"}

    permissions = _json(client.get("/api/auth/permissions", headers=headers))["data"]["permissions"]
    assert "reports.view" in permissions
    assert "reports.generate" not in permissions
    assert "imports.manage" not in permissions

    team = client.get("/api/team/members", headers=headers)
    assert team.status_code == 200

    denied_endpoints = [
        client.post("/api/reports/generate", json={"product_id": "P0001"}, headers=headers),
        client.get("/api/imports", headers=headers),
        client.post("/api/scoring/models", json={}, headers=headers),
        client.get("/api/ops/status", headers=headers),
        client.get("/api/audit/logs", headers=headers),
    ]
    for response in denied_endpoints:
        assert response.status_code == 403
        assert _json(response)["success"] is False


def test_analyst_can_generate_reports_and_import_but_not_administer(client):
    email, password = _create_member(client, "analyst")
    analyst_token = _login(client, email, password)
    headers = {"Authorization": f"Bearer {analyst_token}"}

    report = client.post("/api/reports/generate", json={"product_id": "P0001"}, headers=headers)
    assert report.status_code == 201

    imports = client.get("/api/imports", headers=headers)
    assert imports.status_code == 200

    denied_endpoints = [
        client.get("/api/ops/status", headers=headers),
        client.get("/api/audit/logs", headers=headers),
        client.post("/api/scoring/models", json={}, headers=headers),
        client.post(
            "/api/team/members",
            json={
                "email": f"blocked-{uuid4().hex[:8]}@example.com",
                "display_name": "blocked",
                "password": "Blocked@2026",
                "role": "viewer",
            },
            headers=headers,
        ),
    ]
    for response in denied_endpoints:
        assert response.status_code == 403
        assert _json(response)["success"] is False
