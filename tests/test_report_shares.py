from __future__ import annotations


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


def _create_report(client, token: str | None = None) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post("/api/reports/generate", json={"product_id": "P0001"}, headers=headers)
    payload = _json(response)
    assert response.status_code == 201
    return payload["data"]["report_id"]


def _reset_brand(client, token: str) -> None:
    response = client.put(
        "/api/brand/settings",
        json={
            "brand_name": "ViralPick AI",
            "report_label": "店铺经营分析报告",
            "logo_url": "",
            "primary_color": "#00a99d",
            "accent_color": "#f0a51b",
            "cover_style": "signal-grid",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_report_share_lifecycle(client):
    token = _login(client)
    _reset_brand(client, token)
    report_id = _create_report(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    unauthenticated = client.post(f"/api/reports/{report_id}/shares", json={"expires_in_days": 7})
    assert unauthenticated.status_code == 401

    created = client.post(
        f"/api/reports/{report_id}/shares",
        json={"expires_in_days": 7},
        headers=headers,
    )
    created_payload = _json(created)
    assert created.status_code == 201
    share = created_payload["data"]
    assert share["status"] == "active"
    assert share["share_token"]
    assert "#shared-report=" in share["share_url"]

    listed = client.get(f"/api/reports/{report_id}/shares", headers=headers)
    listed_payload = _json(listed)
    assert listed.status_code == 200
    assert any(item["share_id"] == share["share_id"] for item in listed_payload["data"]["items"])

    shared = client.get(
        f"/api/reports/shared/{share['share_token']}",
        headers={"User-Agent": "ViralPick Test Browser", "X-Forwarded-For": "203.0.113.25"},
    )
    shared_payload = _json(shared)
    assert shared.status_code == 200
    assert shared_payload["success"] is True
    assert shared_payload["data"]["report"]["report_id"] == report_id
    assert shared_payload["data"]["share"]["access_count"] >= 1
    assert shared_payload["data"]["presentation"]["brand"] == "ViralPick AI"
    assert shared_payload["data"]["presentation"]["section_count"] >= 1
    assert shared_payload["data"]["presentation"]["highlights"]
    assert "data_disclaimer" in shared_payload["data"]["presentation"]

    access_logs = client.get(f"/api/reports/shares/{share['share_id']}/access-logs", headers=headers)
    access_payload = _json(access_logs)
    assert access_logs.status_code == 200
    assert access_payload["data"]["summary"]["total"] >= 1
    assert access_payload["data"]["summary"]["unique_visitors"] >= 1
    assert access_payload["data"]["items"][0]["user_agent"] == "ViralPick Test Browser"
    assert len(access_payload["data"]["items"][0]["visitor_hash"]) == 16
    assert "203.0.113.25" not in str(access_payload["data"])

    revoked = client.delete(f"/api/reports/shares/{share['share_id']}", headers=headers)
    revoked_payload = _json(revoked)
    assert revoked.status_code == 200
    assert revoked_payload["data"]["status"] == "revoked"

    after_revoke = client.get(f"/api/reports/shared/{share['share_token']}")
    after_payload = _json(after_revoke)
    assert after_revoke.status_code == 410
    assert after_payload["success"] is False


def test_report_share_validates_expiration(client):
    token = _login(client)
    report_id = _create_report(client, token)
    response = client.post(
        f"/api/reports/{report_id}/shares",
        json={"expires_in_days": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = _json(response)
    assert response.status_code == 400
    assert payload["success"] is False


def test_shared_report_uses_workspace_brand_settings(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brand_response = client.put(
        "/api/brand/settings",
        json={
            "brand_name": "ViralPick Growth Lab",
            "report_label": "Executive Commerce Signal",
            "logo_url": "https://example.com/brand.png",
            "primary_color": "#2457ff",
            "accent_color": "#ffb21a",
            "cover_style": "editorial-light",
        },
        headers=headers,
    )
    assert brand_response.status_code == 200

    report_id = _create_report(client, token)
    share_response = client.post(f"/api/reports/{report_id}/shares", json={"expires_in_days": 7}, headers=headers)
    share_payload = _json(share_response)
    assert share_response.status_code == 201

    shared = client.get(f"/api/reports/shared/{share_payload['data']['share_token']}")
    shared_payload = _json(shared)
    presentation = shared_payload["data"]["presentation"]
    assert shared.status_code == 200
    assert presentation["brand"] == "ViralPick Growth Lab"
    assert presentation["label"] == "Executive Commerce Signal"
    assert presentation["logo_url"] == "https://example.com/brand.png"
    assert presentation["primary_color"] == "#2457ff"
    assert presentation["accent_color"] == "#ffb21a"
    assert presentation["cover_style"] == "editorial-light"

    _reset_brand(client, token)


def test_shared_report_rejects_unknown_token(client):
    response = client.get("/api/reports/shared/not-a-real-token")
    payload = _json(response)
    assert response.status_code == 404
    assert payload["success"] is False


def test_report_share_access_logs_require_share_permission(client):
    token = _login(client)
    report_id = _create_report(client, token)
    share_response = client.post(
        f"/api/reports/{report_id}/shares",
        json={"expires_in_days": 7},
        headers={"Authorization": f"Bearer {token}"},
    )
    share = _json(share_response)["data"]

    unauthenticated = client.get(f"/api/reports/shares/{share['share_id']}/access-logs")
    assert unauthenticated.status_code == 401
