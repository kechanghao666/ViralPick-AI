from __future__ import annotations

from uuid import uuid4

from backend.db import execute_write


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def _login(client, email: str = "demo@viralpick.ai", password: str = "ViralPick@2026") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return _json(response)["data"]["access_token"]


def _create_schedule(client, token: str, **overrides):
    payload = {
        "schedule_name": f"周度单品复盘-{uuid4().hex[:6]}",
        "product_id": "P0001",
        "frequency": "weekly",
        "weekday": 1,
        "run_time": "09:30",
        "timezone": "Asia/Shanghai",
        "use_llm": False,
        "export_format": "docx",
        **overrides,
    }
    return client.post(
        "/api/reports/schedules",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_report_schedule_lifecycle(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    unauthenticated = client.get("/api/reports/schedules")
    assert unauthenticated.status_code == 401

    created = _create_schedule(client, token)
    created_payload = _json(created)
    assert created.status_code == 201
    schedule = created_payload["data"]
    assert schedule["status"] == "active"
    assert schedule["scope_type"] == "product"
    assert schedule["product_id"] == "P0001"
    assert schedule["frequency"] == "weekly"
    assert schedule["next_run_at"].endswith("Z")

    listed = client.get("/api/reports/schedules", headers=headers)
    listed_payload = _json(listed)
    assert listed.status_code == 200
    assert any(item["schedule_id"] == schedule["schedule_id"] for item in listed_payload["data"]["items"])

    run = client.post(f"/api/reports/schedules/{schedule['schedule_id']}/run", headers=headers)
    run_payload = _json(run)
    assert run.status_code == 201
    assert run_payload["data"]["report"]["report_id"]
    assert run_payload["data"]["delivery"]["status"] == "skipped"
    assert run_payload["data"]["delivery"]["reason"] == "no_recipients"
    assert run_payload["data"]["schedule"]["run_count"] == 1
    assert run_payload["data"]["schedule"]["last_report_id"] == run_payload["data"]["report"]["report_id"]

    patched = client.patch(
        f"/api/reports/schedules/{schedule['schedule_id']}",
        json={"status": "paused", "frequency": "monthly", "monthday": 6, "run_time": "08:15"},
        headers=headers,
    )
    patched_payload = _json(patched)
    assert patched.status_code == 200
    assert patched_payload["data"]["status"] == "paused"
    assert patched_payload["data"]["frequency"] == "monthly"
    assert patched_payload["data"]["monthday"] == 6

    archived = client.delete(f"/api/reports/schedules/{schedule['schedule_id']}", headers=headers)
    archived_payload = _json(archived)
    assert archived.status_code == 200
    assert archived_payload["data"]["status"] == "archived"


def test_report_schedule_validation(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    invalid_time = _create_schedule(client, token, run_time="25:90")
    assert invalid_time.status_code == 400
    assert _json(invalid_time)["success"] is False

    invalid_frequency = _create_schedule(client, token, frequency="hourly")
    assert invalid_frequency.status_code == 400

    unknown_product = _create_schedule(client, token, product_id="P-NOT-EXISTS")
    assert unknown_product.status_code == 404

    invalid_delivery = _create_schedule(client, token, delivery_channel="email", recipient_emails="")
    assert invalid_delivery.status_code == 400

    invalid_update = client.patch(
        "/api/reports/schedules/RS-not-found",
        json={"status": "deleted"},
        headers=headers,
    )
    assert invalid_update.status_code == 404


def test_report_schedule_permission_denies_viewer(client):
    owner_token = _login(client)
    suffix = uuid4().hex[:8]
    email = f"schedule-viewer-{suffix}@example.com"
    password = f"Viewer{suffix}@2026"
    created = client.post(
        "/api/team/members",
        json={
            "email": email,
            "display_name": "Schedule Viewer",
            "password": password,
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201

    viewer_token = _login(client, email, password)
    response = client.get("/api/reports/schedules", headers={"Authorization": f"Bearer {viewer_token}"})
    assert response.status_code == 403


def test_run_due_report_schedules_executes_due_items(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    created = _create_schedule(client, token, schedule_name=f"到期执行测试-{uuid4().hex[:6]}", product_id="")
    schedule = _json(created)["data"]
    execute_write(
        """
        UPDATE report_schedules
        SET next_run_at = ?
        WHERE schedule_id = ?
        """,
        ["2026-01-01T00:00:00Z", schedule["schedule_id"]],
    )

    due = client.post("/api/reports/schedules/run-due?limit=5", headers=headers)
    due_payload = _json(due)
    assert due.status_code == 200
    assert due_payload["data"]["executed_count"] >= 1
    executed_ids = {item["schedule"]["schedule_id"] for item in due_payload["data"]["items"]}
    assert schedule["schedule_id"] in executed_ids
    executed = next(item for item in due_payload["data"]["items"] if item["schedule"]["schedule_id"] == schedule["schedule_id"])
    assert executed["report"]["report_id"]
    assert executed["schedule"]["last_report_id"] == executed["report"]["report_id"]


def test_report_schedule_delivery_outbox_when_smtp_not_enabled(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    created = _create_schedule(
        client,
        token,
        schedule_name=f"邮件交付测试-{uuid4().hex[:6]}",
        recipient_emails="ops@example.com, owner@example.com",
        delivery_channel="email",
        export_format="markdown",
    )
    payload = _json(created)
    assert created.status_code == 201
    schedule = payload["data"]
    assert schedule["delivery_channel"] == "email"
    assert schedule["recipients"] == ["ops@example.com", "owner@example.com"]

    status = client.get("/api/reports/delivery/status", headers=headers)
    status_payload = _json(status)
    assert status.status_code == 200
    assert status_payload["data"]["provider"] == "smtp"
    assert status_payload["data"]["enabled"] is False

    run = client.post(f"/api/reports/schedules/{schedule['schedule_id']}/run", headers=headers)
    run_payload = _json(run)
    assert run.status_code == 201
    delivery = run_payload["data"]["delivery"]
    assert delivery["status"] == "skipped"
    assert delivery["reason"] == "disabled"
    assert delivery["recipients"] == ["ops@example.com", "owner@example.com"]

    deliveries = client.get(f"/api/reports/schedules/{schedule['schedule_id']}/deliveries", headers=headers)
    deliveries_payload = _json(deliveries)
    assert deliveries.status_code == 200
    assert deliveries_payload["data"]["items"][0]["delivery_id"] == delivery["delivery_id"]
    assert deliveries_payload["data"]["items"][0]["status"] == "skipped"

    retry = client.post(f"/api/reports/deliveries/{delivery['delivery_id']}/retry", headers=headers)
    retry_payload = _json(retry)
    assert retry.status_code == 201
    retried = retry_payload["data"]["delivery"]
    assert retried["delivery_id"] != delivery["delivery_id"]
    assert retried["retry_of_delivery_id"] == delivery["delivery_id"]
    assert retried["status"] == "skipped"
    assert retried["reason"] == "disabled"

    refreshed = client.get(f"/api/reports/schedules/{schedule['schedule_id']}/deliveries", headers=headers)
    refreshed_payload = _json(refreshed)
    assert refreshed_payload["data"]["items"][0]["delivery_id"] == retried["delivery_id"]


def test_report_delivery_auto_retry_queue_handles_transient_failures(client, monkeypatch):
    from backend.services import report_delivery_service

    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(report_delivery_service, "REPORT_DELIVERY_ENABLED", True)
    monkeypatch.setattr(report_delivery_service, "REPORT_DELIVERY_AUTO_RETRY_ENABLED", True)
    monkeypatch.setattr(report_delivery_service, "REPORT_DELIVERY_MAX_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(report_delivery_service, "REPORT_DELIVERY_RETRY_BACKOFF_MINUTES", "0,0")
    monkeypatch.setattr(report_delivery_service, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(report_delivery_service, "SMTP_FROM_EMAIL", "reports@example.com")

    def failing_send(*args, **kwargs):
        raise RuntimeError("temporary smtp outage")

    monkeypatch.setattr(report_delivery_service, "_send_email", failing_send)
    created = _create_schedule(
        client,
        token,
        schedule_name=f"Auto retry delivery-{uuid4().hex[:6]}",
        recipient_emails="ops@example.com",
        delivery_channel="email",
        export_format="markdown",
    )
    assert created.status_code == 201
    schedule = _json(created)["data"]

    run = client.post(f"/api/reports/schedules/{schedule['schedule_id']}/run", headers=headers)
    run_payload = _json(run)
    assert run.status_code == 201
    delivery = run_payload["data"]["delivery"]
    assert delivery["status"] == "failed"
    assert delivery["reason"] == "smtp_error"
    assert delivery["retry_job"]["status"] == "pending"
    assert delivery["retry_job"]["attempts"] == 0

    jobs = client.get("/api/reports/delivery/retries?status=pending", headers=headers)
    jobs_payload = _json(jobs)
    assert jobs.status_code == 200
    job = jobs_payload["data"]["items"][0]
    assert job["original_delivery_id"] == delivery["delivery_id"]
    assert job["max_attempts"] == 2

    execute_write(
        """
        UPDATE report_delivery_retry_jobs
        SET next_attempt_at = ?
        WHERE job_id = ?
        """,
        ["2026-01-01T00:00:00Z", job["job_id"]],
    )
    first_retry = client.post("/api/reports/delivery/retries/run-due", headers=headers)
    first_retry_payload = _json(first_retry)
    assert first_retry.status_code == 200
    assert first_retry_payload["data"]["processed_count"] == 1
    first_job = first_retry_payload["data"]["items"][0]["job"]
    assert first_job["status"] == "pending"
    assert first_job["attempts"] == 1

    monkeypatch.setattr(report_delivery_service, "_send_email", lambda *args, **kwargs: None)
    execute_write(
        """
        UPDATE report_delivery_retry_jobs
        SET next_attempt_at = ?
        WHERE job_id = ?
        """,
        ["2026-01-01T00:00:00Z", job["job_id"]],
    )
    second_retry = client.post("/api/reports/delivery/retries/run-due", headers=headers)
    second_retry_payload = _json(second_retry)
    assert second_retry.status_code == 200
    assert second_retry_payload["data"]["processed_count"] == 1
    final = second_retry_payload["data"]["items"][0]
    assert final["job"]["status"] == "succeeded"
    assert final["job"]["attempts"] == 2
    assert final["delivery"]["status"] == "sent"
    assert final["delivery"]["retry_of_delivery_id"] == delivery["delivery_id"]
