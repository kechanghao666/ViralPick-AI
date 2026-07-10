from __future__ import annotations

from pathlib import Path
import time

import pytest

from backend.config import BACKUP_DIR


def _json(response):
    payload = response.get_json()
    assert payload is not None
    return payload


def _login(client, email: str = "demo@viralpick.ai", password: str = "ViralPick@2026") -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    payload = _json(response)
    assert response.status_code == 200
    return payload["data"]["access_token"]


def _backup_files() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return list(BACKUP_DIR.glob("viralpick-*.db")) + list(BACKUP_DIR.glob("viralpick-*.sha256"))


def _remove_backup_file(path: Path) -> None:
    for _attempt in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.2)


@pytest.fixture(autouse=True)
def clean_generated_backups():
    for path in _backup_files():
        _remove_backup_file(path)
    yield
    for path in _backup_files():
        _remove_backup_file(path)


def test_ops_endpoints_require_authentication(client):
    response = client.get("/api/ops/status")
    payload = _json(response)
    assert response.status_code == 401
    assert payload["success"] is False


def test_owner_can_view_status_and_create_backup(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    status = client.get("/api/ops/status", headers=headers)
    status_payload = _json(status)
    assert status.status_code == 200
    assert status_payload["success"] is True
    assert status_payload["data"]["database"]["exists"] is True
    assert status_payload["data"]["database"]["table_counts"]

    created = client.post("/api/ops/backups", headers=headers)
    created_payload = _json(created)
    assert created.status_code == 201
    assert created_payload["success"] is True
    backup = created_payload["data"]
    assert backup["filename"].startswith("viralpick-")
    assert backup["filename"].endswith(".db")
    assert len(backup["sha256"]) == 64
    assert (BACKUP_DIR / backup["filename"]).exists()
    assert (BACKUP_DIR / backup["filename"]).with_suffix(".sha256").exists()

    backups = client.get("/api/ops/backups", headers=headers)
    backups_payload = _json(backups)
    assert backups.status_code == 200
    assert backups_payload["success"] is True
    assert any(item["filename"] == backup["filename"] for item in backups_payload["data"]["items"])

    verified = client.get(f"/api/ops/backups/{backup['filename']}/verify", headers=headers)
    verified_payload = _json(verified)
    assert verified.status_code == 200
    assert verified_payload["success"] is True
    assert verified_payload["data"]["valid"] is True
    assert verified_payload["data"]["integrity_check"] == "ok"
    assert verified_payload["data"]["sha256"] == backup["sha256"]


def test_owner_can_view_monitoring_alerts(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    monitoring = client.get("/api/ops/monitoring", headers=headers)
    payload = _json(monitoring)
    assert monitoring.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["health_state"] in {"healthy", "warn", "critical"}
    assert payload["data"]["metrics"]
    assert payload["data"]["alerts"]
    backup_metric = next(item for item in payload["data"]["metrics"] if item["key"] == "backup_count")
    if int(backup_metric["value"]) == 0:
        assert any(item["code"] == "backup_missing" for item in payload["data"]["alerts"])

    created = client.post("/api/ops/backups", headers=headers)
    assert created.status_code == 201
    refreshed = _json(client.get("/api/ops/monitoring", headers=headers))["data"]
    assert not any(item["code"] == "backup_missing" for item in refreshed["alerts"])


def test_owner_can_run_automation_once_and_view_runs(client):
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    run = client.post("/api/ops/automation/run-once", headers=headers)
    run_payload = _json(run)
    assert run.status_code == 200
    assert run_payload["success"] is True
    assert run_payload["data"]["workspace_count"] == 1
    assert run_payload["data"]["items"][0]["run"]["trigger"] == "ops-api"

    runs = client.get("/api/ops/automation/runs", headers=headers)
    runs_payload = _json(runs)
    assert runs.status_code == 200
    assert runs_payload["success"] is True
    assert any(item["run_id"] == run_payload["data"]["items"][0]["run"]["run_id"] for item in runs_payload["data"]["items"])


def test_non_admin_cannot_access_ops_tools(client):
    owner_token = _login(client)
    created = client.post(
        "/api/team/members",
        json={
            "email": "ops-analyst@example.com",
            "display_name": "Ops Analyst",
            "password": "Ops@2026",
            "role": "analyst",
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201

    analyst_token = _login(client, "ops-analyst@example.com", "Ops@2026")
    response = client.get("/api/ops/status", headers={"Authorization": f"Bearer {analyst_token}"})
    payload = _json(response)
    assert response.status_code == 403
    assert payload["success"] is False

    monitoring = client.get("/api/ops/monitoring", headers={"Authorization": f"Bearer {analyst_token}"})
    monitoring_payload = _json(monitoring)
    assert monitoring.status_code == 403
    assert monitoring_payload["success"] is False

    automation = client.post("/api/ops/automation/run-once", headers={"Authorization": f"Bearer {analyst_token}"})
    automation_payload = _json(automation)
    assert automation.status_code == 403
    assert automation_payload["success"] is False
