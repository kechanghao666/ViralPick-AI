from __future__ import annotations

import json

from backend.services import local_knowledge_service


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def test_legacy_endpoints_are_available(client):
    endpoints = [
        "/api/health",
        "/api/overview",
        "/api/categories",
        "/api/products/rankings?metric=gmv&limit=3",
        "/api/products/P0001",
        "/api/hot-products?limit=3",
        "/api/comments/sentiment",
        "/api/sales/trend?days=7",
        "/api/competitors?limit=3",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200, endpoint
        assert _json(response)["success"] is True


def test_ready_endpoint_and_operational_headers(client):
    response = client.get("/api/ready", headers={"X-Request-ID": "test-request-id"})
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["database"] == "ready"
    assert payload["data"]["product_count"] > 0
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_auth_login_me_and_logout(client):
    login = client.post(
        "/api/auth/login",
        json={"email": "demo@viralpick.ai", "password": "ViralPick@2026"},
    )
    payload = _json(login)
    assert login.status_code == 200
    assert payload["success"] is True
    token = payload["data"]["access_token"]
    assert payload["data"]["user"]["role"] == "owner"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    me_payload = _json(me)
    assert me.status_code == 200
    assert me_payload["data"]["email"] == "demo@viralpick.ai"

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200

    after_logout = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert after_logout.status_code == 401


def test_auth_register_creates_workspace_and_session(client):
    response = client.post(
        "/api/auth/register",
        json={
            "workspace_name": "星河家居旗舰店",
            "display_name": "经营负责人",
            "email": "owner-register@example.com",
            "password": "Register@2026",
        },
    )
    payload = _json(response)
    assert response.status_code == 201
    assert payload["success"] is True
    assert payload["data"]["access_token"]
    assert payload["data"]["user"]["role"] == "owner"
    assert payload["data"]["user"]["workspace_name"] == "星河家居旗舰店"

    token = payload["data"]["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    me_payload = _json(me)
    assert me.status_code == 200
    assert me_payload["data"]["email"] == "owner-register@example.com"


def test_auth_required_can_protect_report_generation(client):
    client.application.config["AUTH_REQUIRED"] = True

    unauthenticated = client.post("/api/reports/generate", json={"product_id": "P0001"})
    assert unauthenticated.status_code == 401
    assert _json(unauthenticated)["success"] is False

    login = client.post(
        "/api/auth/login",
        json={"email": "demo@viralpick.ai", "password": "ViralPick@2026"},
    )
    token = _json(login)["data"]["access_token"]
    authenticated = client.post(
        "/api/reports/generate",
        json={"product_id": "P0001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authenticated.status_code == 201
    assert _json(authenticated)["data"]["report_id"]


def test_api_404_remains_json(client):
    response = client.get("/api/not-a-real-endpoint")
    payload = _json(response)
    assert response.status_code == 404
    assert payload["success"] is False
    assert payload["error"] == "Not found"


def test_product_list_supports_pagination_sorting_and_filters(client):
    response = client.get("/api/products?page=1&page_size=5&sort=gmv&order=desc")
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    assert len(payload["data"]["items"]) <= 5
    assert payload["data"]["pagination"]["page"] == 1
    assert payload["data"]["pagination"]["page_size"] == 5
    assert payload["data"]["pagination"]["total"] >= len(payload["data"]["items"])
    item = payload["data"]["items"][0]
    assert item["platform"]
    assert item["shop_name"]
    assert item["image_url"].startswith("./assets/img/products/")
    assert "UCI Online Retail" not in item["source_dataset"]


def test_platform_authorization_flow(client):
    before = _json(client.get("/api/platforms/connections"))
    assert before["success"] is True
    target = next(item for item in before["data"]["items"] if item["platform_key"] == "shopify")
    assert target["status"] == "可授权"

    rejected_sync = client.post("/api/platforms/sync", json={"platform_key": "shopify"})
    rejected_payload = _json(rejected_sync)
    assert rejected_sync.status_code == 400
    assert rejected_payload["success"] is False

    authorize = client.post(
        "/api/platforms/authorize",
        json={
            "platform_key": "shopify",
            "app_id": "APP-SHOPIFY-001",
            "app_secret": "secret-for-test",
            "shop_name": "Shopify 测试店",
            "sync_mode": "增量同步",
        },
    )
    authorize_payload = _json(authorize)
    assert authorize.status_code == 201
    assert authorize_payload["success"] is True
    assert authorize_payload["data"]["metrics"]["product_count"] > 0

    after = _json(client.get("/api/platforms/connections"))
    connected = next(item for item in after["data"]["items"] if item["platform_key"] == "shopify")
    assert connected["status"] == "已连接"
    assert connected["shop_name"] == "Shopify 测试店"

    synced = client.post("/api/platforms/sync", json={"platform_key": "shopify"})
    synced_payload = _json(synced)
    assert synced.status_code == 200
    assert synced_payload["success"] is True
    assert synced_payload["data"]["platform"] == "Shopify"


def test_sales_analysis_and_price_bands(client):
    analysis = _json(client.get("/api/analysis/sales"))
    assert analysis["success"] is True
    assert analysis["data"]["summary"]["sales_quantity"] > 0
    assert analysis["data"]["rankings"]["gmv"]

    price_bands = _json(client.get("/api/analysis/price-bands"))
    assert price_bands["success"] is True
    assert price_bands["data"]["items"]


def test_hot_product_scoring_returns_component_scores(client):
    response = client.get("/api/hot-products/scoring?limit=5")
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    item = payload["data"]["items"][0]
    assert 0 <= item["total_score"] <= 100
    assert item["image_url"]
    assert item["platform"]
    assert "sales_growth" in item["scoring_components"]
    assert item["recommendation_actions"]


def test_comment_keywords_work_globally_and_by_product(client):
    global_payload = _json(client.get("/api/comments/keywords?top_n=5"))
    assert global_payload["success"] is True
    assert "positive_keywords" in global_payload["data"]
    assert "negative_keywords" in global_payload["data"]

    product_payload = _json(client.get("/api/comments/keywords?product_id=P0001&top_n=5"))
    assert product_payload["success"] is True
    assert product_payload["data"]["product_id"] == "P0001"
    product = _json(client.get("/api/products/P0001"))["data"]["product"]
    product_terms = {product["product_name"], product["brand"]}
    keyword_texts = [
        item["word"]
        for item in (
            product_payload["data"]["positive_keywords"]
            + product_payload["data"]["negative_keywords"]
        )
    ]
    pain_texts = [item["pain_point"] for item in product_payload["data"]["pain_points"]]
    assert not product_terms.intersection(keyword_texts)
    assert not product_terms.intersection(pain_texts)


def test_assistant_chat_returns_business_answer_and_redacts_llm_config(client):
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "分析当前商品的爆品机会",
            "product_id": "P0001",
            "page": "products",
            "use_llm": False,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    data = payload["data"]
    assert data["mode"] == "local"
    assert data["llm"]["requested"] is False
    assert data["llm"]["used"] is False
    assert "P0001" not in data["answer"]
    assert ("本地" + "数据库") not in data["answer"]
    assert "API" not in data["answer"]
    assert "--" not in data["answer"]
    assert "当前商品" in data["answer"] or "米家" in data["answer"]
    assert data["context"]["product_id"] == "P0001"
    serialized = str(payload)
    assert "APIPASSWORD" not in serialized
    assert "Authorization" not in serialized


def test_knowledge_base_search_returns_business_documents(client):
    status = _json(client.get("/api/knowledge/status"))
    assert status["success"] is True
    assert status["data"]["ready"] is True
    assert status["data"]["vector_ready"] is True
    assert status["data"]["index_type"] == "local_tfidf_char_ngram"
    assert status["data"]["document_count"] > 0

    response = client.get("/api/knowledge/search?q=商品增长 投放 库存&limit=3")
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["items"]
    assert payload["data"]["items"][0]["content"]


def test_knowledge_base_can_be_rebuilt_and_searched(client):
    rebuild = _json(client.post("/api/knowledge/rebuild"))
    assert rebuild["success"] is True
    assert rebuild["data"]["ready"] is True
    assert rebuild["data"]["vector_ready"] is True
    assert rebuild["data"]["index_type"] == "local_tfidf_char_ngram"
    assert rebuild["data"]["document_count"] > 0

    search = _json(client.get("/api/knowledge/search?q=ROI 库存 商品&limit=5"))
    assert search["success"] is True
    assert search["data"]["items"]
    assert search["data"]["status"]["vector_ready"] is True
    assert search["data"]["status"]["index_type"] == "local_tfidf_char_ngram"
    assert search["data"]["status"]["document_count"] == rebuild["data"]["document_count"]


def test_knowledge_base_rebuild_persists_sparse_vector_index(client):
    rebuild = _json(client.post("/api/knowledge/rebuild"))
    assert rebuild["success"] is True

    payload = json.loads(local_knowledge_service.KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    index = payload["index"]
    assert payload["version"] == 2
    assert index["type"] == "local_tfidf_char_ngram"
    assert index["document_count"] == len(payload["documents"])
    assert len(index["doc_ids"]) == len(payload["documents"])
    assert index["vocabulary"]
    assert index["idf"]
    assert index["vectors"]
    assert index["vectors"][0]["indices"]
    assert index["vectors"][0]["values"]


def test_knowledge_base_search_includes_competitor_documents(client):
    rebuild = _json(client.post("/api/knowledge/rebuild"))
    assert rebuild["success"] is True

    search = _json(client.get("/api/knowledge/search?q=竞品 价格差 主卖点 评分&limit=8"))
    assert search["success"] is True
    sources = {item["source"] for item in search["data"]["items"]}
    assert "竞品情报中心" in sources


def test_assistant_chat_handles_greeting_without_forcing_product_analysis(client):
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "你好",
            "product_id": "P0001",
            "page": "products",
            "use_llm": False,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    data = payload["data"]
    assert data["intent"] == "greeting"
    assert "你好" in data["answer"]
    assert "当前商品" not in data["answer"]
    assert "爆品综合分" not in data["answer"]


def test_assistant_chat_answers_identity_directly(client):
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "你能干什么",
            "product_id": "P0001",
            "page": "reports",
            "use_llm": True,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    data = payload["data"]
    assert data["intent"] == "identity"
    assert data["mode"] == "local"
    assert data["llm"]["used"] is False
    assert "ViralPick AI" in data["answer"]
    assert "通用问答" in data["answer"]
    assert "经营分析" in data["answer"]
    assert "补充具体背景" not in data["answer"]


def test_assistant_chat_handles_off_topic_question_directly(client):
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "Python 是什么？",
            "product_id": "P0001",
            "page": "products",
            "use_llm": False,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    data = payload["data"]
    assert data["intent"] == "off_topic"
    assert "当前商品" not in data["answer"]
    assert "Python" in data["answer"]
    assert "还可以问我" in data["answer"]
    assert "回到本项目" in data["answer"]
    assert "数据接入" in data["answer"]
    assert "选品判断" not in data["answer"]


def test_assistant_handles_common_knowledge_question_without_llm(client):
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "能不能介绍一下杜甫",
            "product_id": "P0001",
            "page": "reports",
            "use_llm": False,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    data = payload["data"]
    assert data["intent"] == "off_topic"
    assert "杜甫" in data["answer"]
    assert "唐代" in data["answer"]
    assert "诗圣" in data["answer"]
    assert "还可以问我" in data["answer"]
    assert "回到本项目" in data["answer"]
    assert "请补充具体对象" not in data["answer"]


def test_assistant_handles_platform_api_access_issue_as_data_access(client):
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "电商平台API无法接入怎么办？",
            "product_id": "P0001",
            "page": "data",
            "use_llm": False,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    data = payload["data"]
    assert data["intent"] == "data_access"
    assert "API" in data["answer"]
    assert "授权" in data["answer"]
    assert "同步" in data["answer"]
    assert "CSV" in data["answer"] or "Excel" in data["answer"]
    assert "通用问题" not in data["answer"]
    assert "竞品情报" not in data["answer"]
    assert "相关项目信息" not in data["answer"]


def test_assistant_off_topic_llm_answer_stays_direct(client, monkeypatch):
    from backend.services import llm_adapter

    def fake_generate_assistant_answer(**_kwargs):
        return {
            "status": "generated",
            "answer": "牛顿第一定律说明，物体在不受外力或合外力为零时，会保持静止或匀速直线运动状态。",
            "provider": "test",
            "model": "test",
            "endpoint_host": "example.test",
            "source": "test",
        }

    monkeypatch.setattr(llm_adapter, "generate_assistant_answer", fake_generate_assistant_answer)
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "牛顿第一定律是什么？",
            "product_id": "P0001",
            "page": "products",
            "use_llm": True,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    data = payload["data"]
    assert data["intent"] == "off_topic"
    assert data["llm"]["used"] is True
    assert "牛顿第一定律" in data["answer"]
    assert "还可以问我" in data["answer"]
    assert "回到本项目" in data["answer"]
    assert "数据接入" in data["answer"]
    assert "选品判断" not in data["answer"]


def test_assistant_passes_relevant_knowledge_to_llm(client, monkeypatch):
    from backend.services import llm_adapter

    captured = {}

    def fake_generate_assistant_answer(**kwargs):
        captured.update(kwargs)
        hits = kwargs["context"]["knowledge_hits"]
        return {
            "status": "generated",
            "answer": f"已结合知识库回答，命中 {len(hits)} 条资料。",
            "provider": "test",
            "model": "test",
            "endpoint_host": "example.test",
            "source": "test",
        }

    monkeypatch.setattr(llm_adapter, "generate_assistant_answer", fake_generate_assistant_answer)
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "蓝月亮洗衣凝珠家庭装的投放和口碑怎么优化？",
            "product_id": "P0001",
            "page": "products",
            "use_llm": True,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    assert payload["data"]["llm"]["used"] is True
    assert captured["context"]["knowledge_hits"]
    assert payload["data"]["context"]["knowledge_hit_count"] > 0


def test_assistant_chat_strips_markdown_placeholders(client, monkeypatch):
    from backend.services import llm_adapter

    def fake_generate_assistant_answer(**_kwargs):
        return {
            "status": "generated",
            "answer": "### 一、**短视频内容测试**\n- 围绕核心卖点优化短视频。",
            "provider": "test",
            "model": "test",
            "endpoint_host": "example.test",
            "source": "test",
        }

    monkeypatch.setattr(llm_adapter, "generate_assistant_answer", fake_generate_assistant_answer)
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "这个商品怎么优化？",
            "product_id": "P0001",
            "page": "products",
            "use_llm": True,
        },
    )
    payload = _json(response)
    assert response.status_code == 200
    answer = payload["data"]["answer"]
    assert "内容素材测试" in answer
    assert "**" not in answer
    assert "###" not in answer
    assert "- 围绕" not in answer


def test_competitor_summary_handles_missing_rows(client):
    response = client.get("/api/competitors/summary?product_id=P0120")
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    assert isinstance(payload["data"]["items"], list)
    if payload["data"]["items"]:
        item = payload["data"]["items"][0]
        assert item["product_image_url"]
        assert item["competitor_image_url"]
        assert item["competitor_platform"]
        assert item["competitor_shop_name"]


def test_forecast_validates_horizon_and_returns_prediction(client):
    response = client.get("/api/forecast/sales?days=7")
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    assert len(payload["data"]["forecast"]) == 7
    assert payload["data"]["summary"]["trend_direction"] in {"up", "down", "stable"}

    invalid = client.get("/api/forecast/sales?days=9")
    invalid_payload = _json(invalid)
    assert invalid.status_code == 400
    assert invalid_payload["success"] is False


def test_report_generation_and_lookup(client):
    response = client.post("/api/reports/generate", json={"product_id": "P0001"})
    payload = _json(response)
    assert response.status_code == 201
    assert payload["success"] is True
    report_id = payload["data"]["report_id"]
    assert payload["data"]["sections"]

    lookup = _json(client.get(f"/api/reports/{report_id}"))
    assert lookup["success"] is True
    assert lookup["data"]["report_id"] == report_id
