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


def test_team_members_require_authentication(client):
    response = client.get("/api/team/members")
    payload = _json(response)
    assert response.status_code == 401
    assert payload["success"] is False


def test_owner_can_create_and_update_member(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/api/team/members",
        json={
            "email": "analyst@example.com",
            "display_name": "运营分析师",
            "password": "Analyst@2026",
            "role": "analyst",
        },
        headers=headers,
    )
    create_payload = _json(create)
    assert create.status_code == 201
    assert create_payload["data"]["role"] == "analyst"
    user_id = create_payload["data"]["user_id"]

    update = client.patch(
        f"/api/team/members/{user_id}",
        json={"role": "viewer", "status": "suspended"},
        headers=headers,
    )
    update_payload = _json(update)
    assert update.status_code == 200
    assert update_payload["data"]["role"] == "viewer"
    assert update_payload["data"]["status"] == "suspended"

    members = client.get("/api/team/members", headers=headers)
    members_payload = _json(members)
    assert members.status_code == 200
    assert any(item["email"] == "analyst@example.com" for item in members_payload["data"]["items"])


def test_member_creation_rejects_duplicate_email(client):
    token = _login(client)
    response = client.post(
        "/api/team/members",
        json={
            "email": "demo@viralpick.ai",
            "display_name": "重复账号",
            "password": "Password@2026",
            "role": "analyst",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = _json(response)
    assert response.status_code == 400
    assert payload["success"] is False


def test_analyst_cannot_manage_team(client):
    owner_token = _login(client)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    created = client.post(
        "/api/team/members",
        json={
            "email": "limited@example.com",
            "display_name": "受限分析师",
            "password": "Limited@2026",
            "role": "analyst",
        },
        headers=owner_headers,
    )
    assert created.status_code == 201

    analyst_token = _login(client, "limited@example.com", "Limited@2026")
    response = client.post(
        "/api/team/members",
        json={
            "email": "viewer@example.com",
            "display_name": "只读成员",
            "password": "Viewer@2026",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    payload = _json(response)
    assert response.status_code == 403
    assert payload["success"] is False


def test_owner_cannot_suspend_self_or_change_own_role(client):
    token = _login(client)
    me = _json(client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}))["data"]
    response = client.patch(
        f"/api/team/members/{me['user_id']}",
        json={"role": "viewer", "status": "suspended"},
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = _json(response)
    assert response.status_code == 400
    assert payload["success"] is False
