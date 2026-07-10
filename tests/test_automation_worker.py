from __future__ import annotations

import json
import subprocess
import sys
from uuid import uuid4

from backend.db import execute_write, fetch_one
from backend.services import automation_service


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def _login(client, email: str = "demo@viralpick.ai", password: str = "ViralPick@2026") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return _json(response)["data"]["access_token"]


def test_automation_service_runs_due_schedules_and_records_run(client):
    token = _login(client)
    created = client.post(
        "/api/reports/schedules",
        json={
            "schedule_name": f"Worker due report {uuid4().hex[:6]}",
            "product_id": "",
            "frequency": "daily",
            "run_time": "09:00",
            "timezone": "Asia/Shanghai",
            "use_llm": False,
            "export_format": "markdown",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201
    schedule = _json(created)["data"]
    execute_write(
        """
        UPDATE report_schedules
        SET next_run_at = ?
        WHERE schedule_id = ?
        """,
        ["2026-01-01T00:00:00Z", schedule["schedule_id"]],
    )

    result = automation_service.run_once(workspace_id="W-DEMO", trigger="test-worker", schedule_limit=5, retry_limit=5)

    assert result["status"] == "ok"
    assert result["workspace_count"] == 1
    assert result["totals"]["schedules_due"] >= 1
    assert result["totals"]["schedules_executed"] >= 1
    run = result["items"][0]["run"]
    assert run["trigger"] == "test-worker"
    assert run["workspace_id"] == "W-DEMO"
    assert run["schedules_executed"] >= 1

    persisted = fetch_one("SELECT * FROM automation_runs WHERE run_id = ?", [run["run_id"]])
    assert persisted is not None
    assert persisted["trigger"] == "test-worker"
    updated = fetch_one("SELECT last_report_id, run_count FROM report_schedules WHERE schedule_id = ?", [schedule["schedule_id"]])
    assert updated["last_report_id"]
    assert updated["run_count"] == 1


def test_automation_worker_cli_once_json(initialized_database):
    completed = subprocess.run(
        [sys.executable, "scripts/run_automation_worker.py", "--once", "--json"],
        cwd=".",
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["trigger"] == "worker"
    assert "totals" in payload
    assert payload["workspace_count"] >= 1
