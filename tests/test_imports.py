from __future__ import annotations

from io import BytesIO


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


def test_import_jobs_require_authentication(client):
    response = client.get("/api/imports")
    payload = _json(response)
    assert response.status_code == 401
    assert payload["success"] is False


def test_import_csv_validate_mode_records_job(client):
    token = _login(client)
    csv_text = (
        "comment_id,product_id,mapped_product_category,review_text,sentiment,"
        "sentiment_label,rating,category_source,data_source\n"
        "TEST-C-1,P0001,餐厨用品,包装完整，适合直播间主推,positive,1,5,manual,merchant authorized sample\n"
    )
    response = client.post(
        "/api/imports",
        data={
            "dataset_type": "comments",
            "mode": "validate",
            "file": (BytesIO(csv_text.encode("utf-8-sig")), "comments.csv"),
        },
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )
    payload = _json(response)
    assert response.status_code == 201
    assert payload["success"] is True
    assert payload["data"]["status"] == "validated"
    assert payload["data"]["row_count"] == 1
    assert payload["data"]["summary"]["preview"][0]["product_id"] == "P0001"

    jobs = client.get("/api/imports?limit=5", headers={"Authorization": f"Bearer {token}"})
    jobs_payload = _json(jobs)
    assert jobs.status_code == 200
    assert jobs_payload["data"]["items"][0]["job_id"] == payload["data"]["job_id"]
    assert jobs_payload["data"]["supported_datasets"]


def test_import_template_download_requires_auth_and_returns_csv(client):
    unauthenticated = client.get("/api/imports/templates/comments")
    assert unauthenticated.status_code == 401

    token = _login(client)
    response = client.get(
        "/api/imports/templates/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment;")
    csv_text = response.data.decode("utf-8-sig")
    assert "comment_id,product_id,mapped_product_category" in csv_text
    assert "merchant authorized sample" in csv_text


def test_failed_import_error_report_can_be_downloaded(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    csv_text = (
        "comment_id,product_id,mapped_product_category,review_text,sentiment,"
        "sentiment_label,category_source,data_source\n"
        "BAD-C-1,P0001,餐厨用品,缺少评分字段,negative,0,manual,merchant authorized sample\n"
    )
    response = client.post(
        "/api/imports",
        data={
            "dataset_type": "comments",
            "mode": "validate",
            "file": (BytesIO(csv_text.encode("utf-8-sig")), "bad-comments.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    payload = _json(response)
    assert response.status_code == 400
    assert payload["success"] is False

    jobs = _json(client.get("/api/imports?limit=20", headers=headers))["data"]["items"]
    job = next(item for item in jobs if item["filename"] == "bad-comments.csv")
    assert job["status"] == "failed"
    assert job["summary"]["error_details"]

    report = client.get(f"/api/imports/{job['job_id']}/errors", headers=headers)
    assert report.status_code == 200
    assert report.headers["Content-Disposition"].startswith("attachment;")
    csv_report = report.data.decode("utf-8-sig")
    assert "job_id,dataset_type,filename,line_number,field,severity,message,value" in csv_report
    assert "缺少必需字段" in csv_report
    assert "rating" in csv_report


def test_import_rejects_unknown_dataset(client):
    token = _login(client)
    response = client.post(
        "/api/imports",
        data={
            "dataset_type": "unknown",
            "mode": "validate",
            "file": (BytesIO(b"a,b\n1,2\n"), "unknown.csv"),
        },
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )
    payload = _json(response)
    assert response.status_code == 400
    assert payload["success"] is False


def test_import_commit_refreshes_knowledge_base(client):
    csv_text = (
        "comment_id,product_id,review_text,sentiment,sentiment_label,rating,category_source,data_source\n"
        "TEST-KB-1,P0001,洗后香味自然，适合家庭囤货复购,positive,1,5,manual,merchant authorized sample\n"
    )
    preview_response = client.post(
        "/api/imports/preview",
        data={
            "dataset_type": "comments",
            "file": (BytesIO(csv_text.encode("utf-8-sig")), "knowledge-comments.csv"),
        },
        content_type="multipart/form-data",
    )
    preview_payload = _json(preview_response)
    assert preview_response.status_code == 201
    assert preview_payload["success"] is True

    preview = preview_payload["data"]
    commit_response = client.post(
        "/api/imports/commit",
        json={
            "preview_id": preview["preview_id"],
            "dataset_type": preview["dataset_type"],
            "field_mapping": preview["field_mapping"],
            "mode": "append",
        },
    )
    commit_payload = _json(commit_response)
    assert commit_response.status_code == 201
    assert commit_payload["success"] is True
    summary = commit_payload["data"]["summary"]
    assert summary["knowledge_base"]["ready"] is True
    assert summary["knowledge_base"]["document_count"] > 0

    search_payload = _json(client.get("/api/knowledge/search?q=香味 自然 囤货&product_id=P0001"))
    assert search_payload["success"] is True
    assert search_payload["data"]["items"]
