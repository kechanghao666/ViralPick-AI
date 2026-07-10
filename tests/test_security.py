from __future__ import annotations

from backend import rate_limiter
from backend.repositories import auth_repository
from backend.services import auth_service


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def test_login_lockout_after_repeated_failed_attempts(client, monkeypatch):
    monkeypatch.setattr(auth_service, "AUTH_MAX_FAILED_ATTEMPTS", 2)
    monkeypatch.setattr(auth_service, "AUTH_LOCKOUT_MINUTES", 15)

    try:
        first = client.post(
            "/api/auth/login",
            json={"email": "demo@viralpick.ai", "password": "wrong-password"},
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        assert first.status_code == 401

        second = client.post(
            "/api/auth/login",
            json={"email": "demo@viralpick.ai", "password": "wrong-password"},
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        second_payload = _json(second)
        assert second.status_code == 423
        assert second_payload["success"] is False

        locked = client.post(
            "/api/auth/login",
            json={"email": "demo@viralpick.ai", "password": "ViralPick@2026"},
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        assert locked.status_code == 423
    finally:
        auth_repository.reset_failed_logins("U-DEMO-ADMIN")


def test_auth_rate_limit_returns_429(initialized_database):
    from backend.app import create_app

    rate_limiter.reset_rate_limits()
    app = create_app()
    app.config.update(
        TESTING=True,
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_AUTH_PER_WINDOW=2,
        RATE_LIMIT_WINDOW_SECONDS=60,
    )
    client = app.test_client()
    headers = {"X-Forwarded-For": "203.0.113.55"}

    for _ in range(2):
        response = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "bad-password"},
            headers=headers,
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "bad-password"},
        headers=headers,
    )
    payload = _json(limited)
    assert limited.status_code == 429
    assert payload["success"] is False
    assert limited.headers["X-RateLimit-Bucket"] == "auth"
    assert limited.headers["X-RateLimit-Remaining"] == "0"
    assert int(limited.headers["Retry-After"]) > 0
    rate_limiter.reset_rate_limits()


def test_cors_headers_cover_authenticated_mutation_methods(client):
    response = client.options("/api/team/members", headers={"Origin": "https://example.com"})
    assert response.status_code < 500
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
    assert "PATCH" in response.headers["Access-Control-Allow-Methods"]
    assert "DELETE" in response.headers["Access-Control-Allow-Methods"]
