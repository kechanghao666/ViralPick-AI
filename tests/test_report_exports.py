from __future__ import annotations

import html
from io import BytesIO
from zipfile import ZipFile


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def _create_report_payload(client) -> dict:
    response = client.post("/api/reports/generate", json={"product_id": "P0001", "use_llm": False})
    payload = _json(response)
    assert response.status_code == 201
    return payload["data"]


def _create_report(client) -> str:
    return _create_report_payload(client)["report_id"]


def test_report_export_formats(client):
    report_id = _create_report(client)

    markdown = client.get(f"/api/reports/{report_id}/export?format=markdown")
    assert markdown.status_code == 200
    assert markdown.headers["Content-Type"].startswith("text/markdown")
    assert "店铺经营分析报告" in markdown.data.decode("utf-8-sig")

    html = client.get(f"/api/reports/{report_id}/export?format=html")
    assert html.status_code == 200
    assert html.headers["Content-Type"].startswith("text/html")
    assert b"<!doctype html>" in html.data
    html_text = html.data.decode("utf-8")
    assert 'class="kpis"' in html_text
    assert 'class="visuals"' in html_text
    assert "执行安排" in html_text

    docx = client.get(f"/api/reports/{report_id}/export?format=docx")
    assert docx.status_code == 200
    assert docx.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert docx.data[:2] == b"PK"
    with ZipFile(BytesIO(docx.data)) as archive:
        names = archive.namelist()
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert any(name.startswith("word/media/") for name in names)
    assert "宋体" in document_xml
    assert "报告摘要" in document_xml
    assert "核心指标" in document_xml
    assert "收入趋势图" in document_xml
    assert "证据数据" in document_xml
    assert "商品销售额排行图" in document_xml
    assert "未来销量趋势图" in document_xml
    assert "经营概览" in document_xml

    pdf = client.get(f"/api/reports/{report_id}/export?format=pdf")
    assert pdf.status_code == 200
    assert pdf.headers["Content-Type"].startswith("application/pdf")
    assert pdf.data[:4] == b"%PDF"
    assert len(pdf.data) > 500


def test_report_export_html_matches_generated_report_structure(client):
    report = _create_report_payload(client)
    response = client.get(f"/api/reports/{report['report_id']}/export?format=html")
    assert response.status_code == 200
    html_text = response.data.decode("utf-8")

    assert "智能增强" not in html_text
    assert "大模型" not in html_text
    assert html.escape(report["report_id"]) in html_text
    assert "报告编号" in html_text

    for item in report["visuals"]["kpis"]:
        assert html.escape(str(item["label"])) in html_text
        assert html.escape(str(item["value"])) in html_text

    for section in report["sections"]:
        assert html.escape(str(section["heading"])) in html_text
        assert html.escape(str(section["content"])) in html_text

    for item in report["visuals"]["actions"]:
        assert html.escape(str(item["title"])) in html_text
        assert html.escape(str(item["content"])) in html_text


def test_report_export_validates_format(client):
    report_id = _create_report(client)
    response = client.get(f"/api/reports/{report_id}/export?format=xlsx")
    payload = _json(response)
    assert response.status_code == 400
    assert payload["success"] is False


def test_report_export_respects_auth_required(client):
    report_id = _create_report(client)
    client.application.config["AUTH_REQUIRED"] = True
    response = client.get(f"/api/reports/{report_id}/export?format=docx")
    payload = _json(response)
    assert response.status_code == 401
    assert payload["success"] is False
