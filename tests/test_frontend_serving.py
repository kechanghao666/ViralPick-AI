from __future__ import annotations

import importlib
import re


def test_optional_frontend_serving(monkeypatch, initialized_database):
    monkeypatch.setenv("VIRALPICK_SERVE_FRONTEND", "1")

    import backend.config
    import backend.app

    importlib.reload(backend.config)
    importlib.reload(backend.app)

    app = backend.app.create_app()
    app.config.update(TESTING=True, AUTH_REQUIRED=False)
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "ViralPick AI" in html
    assert "demo@viralpick.ai" not in html
    assert "ViralPick@2026" not in html
    auth_html = re.search(r'<section class="auth-screen".*?</section>', html, re.S).group(0)
    for forbidden in ["数据", "销售", "GMV", "订单", "转化率", "CSV / Excel", "星河家居旗舰店"]:
        assert forbidden not in auth_html
    assert 'id="loginEmail" type="email" placeholder="name@example.com"' in html
    assert 'id="loginPassword" type="password" placeholder=' in html
    assert 'class="panel span-4 dashboard-actions-panel"' in html
    assert "data-upload-panel" in html
    assert "marketing-metrics-panel" in html
    assert "forecast-chart-panel" in html
    assert 'class="report-layout"' in html
    assert 'class="assistant-widget"' in html

    api_response = client.get("/api/not-a-real-endpoint")
    assert api_response.status_code == 404
    assert api_response.get_json()["success"] is False
