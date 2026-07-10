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


def test_team_invitation_lifecycle(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    suffix = uuid4().hex[:8]
    email = f"invite-{suffix}@example.com"
    password = f"Invite{suffix}@2026"

    created = client.post(
        "/api/team/invitations",
        json={
            "email": email,
            "display_name": "邀请成员",
            "role": "analyst",
            "expires_in_days": 7,
        },
        headers=headers,
    )
    created_payload = _json(created)
    assert created.status_code == 201
    invitation = created_payload["data"]
    assert invitation["email"] == email
    assert invitation["status"] == "pending"
    assert invitation["invite_token"]
    assert "#invite=" in invitation["invite_url"]

    listed = client.get("/api/team/invitations", headers=headers)
    listed_payload = _json(listed)
    assert listed.status_code == 200
    assert any(item["invitation_id"] == invitation["invitation_id"] for item in listed_payload["data"]["items"])

    public_detail = client.get(f"/api/team/invitations/{invitation['invite_token']}")
    public_payload = _json(public_detail)
    assert public_detail.status_code == 200
    assert public_payload["data"]["email"] == email
    assert public_payload["data"]["workspace"]["workspace_name"]
    assert "invite_token" not in public_payload["data"]

    accepted = client.post(
        f"/api/team/invitations/{invitation['invite_token']}/accept",
        json={
            "display_name": "Accepted Analyst",
            "password": password,
            "password_confirm": password,
        },
    )
    accepted_payload = _json(accepted)
    assert accepted.status_code == 201
    assert accepted_payload["data"]["member"]["email"] == email
    assert accepted_payload["data"]["member"]["role"] == "analyst"

    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert _json(login)["data"]["user"]["email"] == email

    reused = client.post(
        f"/api/team/invitations/{invitation['invite_token']}/accept",
        json={"display_name": "Duplicate", "password": password, "password_confirm": password},
    )
    assert reused.status_code == 400
    assert _json(reused)["success"] is False


def test_team_invitation_can_be_revoked(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    email = f"revoke-{uuid4().hex[:8]}@example.com"

    created = client.post(
        "/api/team/invitations",
        json={"email": email, "display_name": "待撤销成员", "role": "viewer"},
        headers=headers,
    )
    invitation = _json(created)["data"]
    revoked = client.delete(f"/api/team/invitations/{invitation['invitation_id']}", headers=headers)
    revoked_payload = _json(revoked)
    assert revoked.status_code == 200
    assert revoked_payload["data"]["status"] == "revoked"

    public_detail = client.get(f"/api/team/invitations/{invitation['invite_token']}")
    assert public_detail.status_code == 400
    assert _json(public_detail)["success"] is False


def test_viewer_cannot_manage_team_invitations(client):
    owner_token = _login(client)
    suffix = uuid4().hex[:8]
    viewer_email = f"viewer-invite-{suffix}@example.com"
    viewer_password = f"Viewer{suffix}@2026"
    create_viewer = client.post(
        "/api/team/members",
        json={
            "email": viewer_email,
            "display_name": "只读邀请测试",
            "password": viewer_password,
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert create_viewer.status_code == 201
    viewer_token = _login(client, viewer_email, viewer_password)
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    listed = client.get("/api/team/invitations", headers=viewer_headers)
    assert listed.status_code == 403

    created = client.post(
        "/api/team/invitations",
        json={"email": f"blocked-{suffix}@example.com", "display_name": "blocked", "role": "analyst"},
        headers=viewer_headers,
    )
    assert created.status_code == 403
