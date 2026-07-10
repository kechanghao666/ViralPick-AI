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


def test_hot_scoring_returns_active_model_metadata(client):
    response = client.get("/api/hot-products/scoring?limit=3")
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["model"]["model_id"]
    assert round(sum(payload["data"]["weights"].values()), 4) == 1.0
    assert payload["data"]["items"]


def test_scoring_model_management_requires_authentication(client):
    response = client.get("/api/scoring/models")
    payload = _json(response)
    assert response.status_code == 401
    assert payload["success"] is False


def test_owner_can_create_and_activate_scoring_model(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    weights = {
        "sales_growth": 0.10,
        "gmv_growth": 0.10,
        "positive_rate": 0.30,
        "comment_heat": 0.10,
        "price_competitiveness": 0.15,
        "video_interaction": 0.20,
        "conversion_rate": 0.05,
    }
    created = client.post(
        "/api/scoring/models",
        json={"model_name": "口碑优先模型", "note": "提高好评率权重", "weights": weights},
        headers=headers,
    )
    created_payload = _json(created)
    assert created.status_code == 201
    assert created_payload["data"]["status"] == "active"
    model_id = created_payload["data"]["model_id"]

    models = client.get("/api/scoring/models", headers=headers)
    models_payload = _json(models)
    assert models.status_code == 200
    assert models_payload["data"]["active_model"]["model_id"] == model_id
    assert any(item["model_id"] == model_id for item in models_payload["data"]["items"])

    scoring = client.get("/api/hot-products/scoring?limit=3")
    scoring_payload = _json(scoring)
    assert scoring.status_code == 200
    assert scoring_payload["data"]["model"]["model_id"] == model_id
    assert scoring_payload["data"]["weights"]["positive_rate"] == 0.3


def test_scoring_model_rejects_invalid_weights(client):
    token = _login(client)
    response = client.post(
        "/api/scoring/models",
        json={
            "model_name": "非法模型",
            "weights": {
                "sales_growth": 0.20,
                "gmv_growth": 0.20,
                "positive_rate": 0.20,
                "comment_heat": 0.10,
                "price_competitiveness": 0.10,
                "video_interaction": 0.10,
                "conversion_rate": 0.05,
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = _json(response)
    assert response.status_code == 400
    assert payload["success"] is False


def test_analyst_cannot_create_scoring_model(client):
    owner_token = _login(client)
    created = client.post(
        "/api/team/members",
        json={
            "email": "score-analyst@example.com",
            "display_name": "Score Analyst",
            "password": "Score@2026",
            "role": "analyst",
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201
    analyst_token = _login(client, "score-analyst@example.com", "Score@2026")
    response = client.post(
        "/api/scoring/models",
        json={
            "model_name": "无权模型",
            "weights": {
                "sales_growth": 0.20,
                "gmv_growth": 0.20,
                "positive_rate": 0.15,
                "comment_heat": 0.10,
                "price_competitiveness": 0.15,
                "video_interaction": 0.15,
                "conversion_rate": 0.05,
            },
        },
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    payload = _json(response)
    assert response.status_code == 403
    assert payload["success"] is False
