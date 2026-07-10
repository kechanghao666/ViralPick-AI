from __future__ import annotations

from uuid import uuid4


DEFAULT_BRAND = {
    "brand_name": "ViralPick AI",
    "report_label": "店铺经营分析报告",
    "logo_url": "",
    "primary_color": "#00a99d",
    "accent_color": "#f0a51b",
    "cover_style": "signal-grid",
}


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
    email = f"brand-{role}-{suffix}@example.com"
    password = f"Brand{suffix}@2026"
    response = client.post(
        "/api/team/members",
        json={
            "email": email,
            "display_name": f"品牌测试 {role}",
            "password": password,
            "role": role,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return email, password


def _reset_brand(client, token: str) -> None:
    response = client.put("/api/brand/settings", json=DEFAULT_BRAND, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_owner_can_read_and_update_brand_settings(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _reset_brand(client, token)

    current = client.get("/api/brand/settings", headers=headers)
    current_payload = _json(current)
    assert current.status_code == 200
    assert current_payload["data"]["brand_name"] == "ViralPick AI"
    assert current_payload["data"]["can_manage"] is True
    assert "cover_styles" in current_payload["data"]

    updated = client.put(
        "/api/brand/settings",
        json={
            "brand_name": "ViralPick Growth Lab",
            "report_label": "Executive Commerce Signal",
            "logo_url": "https://example.com/logo.png",
            "primary_color": "#1248ff",
            "accent_color": "#f0a51b",
            "cover_style": "executive-dark",
        },
        headers=headers,
    )
    updated_payload = _json(updated)
    assert updated.status_code == 200
    assert updated_payload["success"] is True
    assert updated_payload["data"]["brand_name"] == "ViralPick Growth Lab"
    assert updated_payload["data"]["primary_color"] == "#1248ff"
    assert "logo.png" in updated_payload["data"]["logo_url"]

    _reset_brand(client, token)


def test_brand_settings_reject_invalid_payloads(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    bad_color = client.put(
        "/api/brand/settings",
        json={"brand_name": "ViralPick AI", "report_label": "Commerce Brief", "primary_color": "teal"},
        headers=headers,
    )
    assert bad_color.status_code == 400
    assert _json(bad_color)["success"] is False

    bad_logo = client.put(
        "/api/brand/settings",
        json={"brand_name": "ViralPick AI", "report_label": "Commerce Brief", "logo_url": "javascript:alert(1)"},
        headers=headers,
    )
    assert bad_logo.status_code == 400
    assert _json(bad_logo)["success"] is False


def test_viewer_can_read_brand_but_cannot_update(client):
    email, password = _create_member(client, "viewer")
    viewer_token = _login(client, email, password)
    headers = {"Authorization": f"Bearer {viewer_token}"}

    current = client.get("/api/brand/settings", headers=headers)
    assert current.status_code == 200
    assert _json(current)["data"]["can_manage"] is False

    denied = client.put(
        "/api/brand/settings",
        json={"brand_name": "Viewer Brand", "report_label": "Viewer Brief"},
        headers=headers,
    )
    assert denied.status_code == 403
    assert _json(denied)["success"] is False
