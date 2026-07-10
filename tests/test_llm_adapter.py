from __future__ import annotations

from backend.services import llm_adapter


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def test_llm_status_does_not_expose_credentials(client):
    response = client.get("/api/llm/status")
    payload = _json(response)
    assert response.status_code == 200
    assert payload["success"] is True
    assert "supports_report_generation" in payload["data"]
    assert "api_password" not in payload["data"]
    assert "api_key" not in payload["data"]


def test_llm_adapter_reads_spark_api_file_without_exposing_credentials(monkeypatch, tmp_path):
    config_file = tmp_path / "API.txt"
    config_file.write_text(
        "\n".join(
            [
                "HTTP服务：",
                "APIPASSWORD：local-secret:pass_2026",
                "服务名称：Spark X",
                "X2: https://spark-api-open.xf-yun.com/x2/chat/completions",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VIRALPICK_LLM_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("VIRALPICK_LLM_ENDPOINT", raising=False)
    monkeypatch.delenv("VIRALPICK_LLM_API_PASSWORD", raising=False)

    status = llm_adapter.get_status()

    assert status["configured"] is True
    assert status["endpoint_host"] == "spark-api-open.xf-yun.com"
    assert status["source"] == "local_config_file"
    assert "local-secret" not in str(status)


def test_llm_failure_message_redacts_credentials(monkeypatch):
    def fake_post(url, headers, json, timeout):
        raise RuntimeError(f"Authorization: {headers['Authorization']} failed")

    monkeypatch.setenv("VIRALPICK_LLM_ENDPOINT", "https://example.test/chat/completions")
    monkeypatch.setenv("VIRALPICK_LLM_API_PASSWORD", "test-secret")
    monkeypatch.setattr(llm_adapter.requests, "post", fake_post)

    result = llm_adapter.generate_report_markdown(
        title="测试报告",
        sections=[],
        context={},
        use_llm=True,
    )

    assert result["status"] == "fallback"
    assert "test-secret" not in result["message"]
    assert "Bearer [redacted]" in result["message"]


def test_report_generation_can_use_configured_llm(monkeypatch, client):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "# 智能增强报告\n\n## 商品表现总结\n已基于结构化数据生成增强版报告。"
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        assert url == "https://example.test/chat/completions"
        assert headers["Authorization"] == "Bearer test-secret"
        assert json["model"] == "spark-test"
        assert timeout == 3
        return FakeResponse()

    monkeypatch.setenv("VIRALPICK_LLM_ENDPOINT", "https://example.test/chat/completions")
    monkeypatch.setenv("VIRALPICK_LLM_API_PASSWORD", "test-secret")
    monkeypatch.setenv("VIRALPICK_LLM_MODEL", "spark-test")
    monkeypatch.setenv("VIRALPICK_LLM_TIMEOUT_SECONDS", "3")
    monkeypatch.setattr(llm_adapter.requests, "post", fake_post)

    response = client.post("/api/reports/generate", json={"product_id": "P0001", "use_llm": True})
    payload = _json(response)
    assert response.status_code == 201
    assert payload["success"] is True
    assert payload["data"]["ai_generation"]["status"] == "generated"
    assert payload["data"]["enhanced_markdown"].startswith("# 智能增强报告")
    assert payload["data"]["markdown"].startswith("# 《店铺经营分析报告》")
    assert "核心指标" in payload["data"]["markdown"]
    assert "test-secret" not in str(payload["data"])
