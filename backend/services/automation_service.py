from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.repositories import automation_repository
from backend.services import report_delivery_service, report_schedule_service


class AutomationError(Exception):
    status_code = 400


def run_once(
    workspace_id: str | None = None,
    schedule_limit: int = 20,
    retry_limit: int = 20,
    trigger: str = "worker",
) -> dict[str, Any]:
    safe_schedule_limit = max(1, min(100, int(schedule_limit or 20)))
    safe_retry_limit = max(1, min(100, int(retry_limit or 20)))
    workspaces = automation_repository.list_active_workspaces(_clean_optional(workspace_id))
    if workspace_id and not workspaces:
        raise AutomationError(f"Workspace not found or inactive: {workspace_id}")

    items = [
        _run_workspace(
            workspace,
            schedule_limit=safe_schedule_limit,
            retry_limit=safe_retry_limit,
            trigger=trigger,
        )
        for workspace in workspaces
    ]
    return {
        "trigger": trigger,
        "workspace_count": len(workspaces),
        "run_count": len(items),
        "status": _aggregate_status(items),
        "totals": _totals(items),
        "items": items,
    }


def list_runs(workspace_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(200, int(limit or 50)))
    rows = automation_repository.list_runs(_clean_optional(workspace_id), safe_limit)
    return {"items": [_public_run(row) for row in rows]}


def _run_workspace(
    workspace: dict[str, Any],
    schedule_limit: int,
    retry_limit: int,
    trigger: str,
) -> dict[str, Any]:
    started_at = _now_iso()
    actor = _system_actor(workspace)
    schedules: dict[str, Any] = {
        "due_count": 0,
        "executed_count": 0,
        "failed_count": 0,
        "failed": [],
        "items": [],
    }
    retries: dict[str, Any] = {
        "due_count": 0,
        "processed_count": 0,
        "succeeded_count": 0,
        "exhausted_count": 0,
        "cancelled_count": 0,
        "items": [],
    }
    status = "ok"
    message = ""
    try:
        schedules = report_schedule_service.run_due_schedules(actor, limit=schedule_limit)
        retries = report_delivery_service.run_due_retries(actor, limit=retry_limit)
        if int(schedules.get("failed_count") or 0) or int(retries.get("exhausted_count") or 0) or int(retries.get("cancelled_count") or 0):
            status = "warn"
    except Exception as exc:
        status = "failed"
        message = str(exc)

    run = {
        "run_id": f"AR-{uuid4().hex[:14]}",
        "workspace_id": workspace.get("workspace_id"),
        "workspace_name": workspace.get("workspace_name"),
        "trigger": trigger,
        "status": status,
        "schedules_due": int(schedules.get("due_count") or 0),
        "schedules_executed": int(schedules.get("executed_count") or 0),
        "schedules_failed": int(schedules.get("failed_count") or 0),
        "retries_due": int(retries.get("due_count") or 0),
        "retries_processed": int(retries.get("processed_count") or 0),
        "retries_succeeded": int(retries.get("succeeded_count") or 0),
        "retries_exhausted": int(retries.get("exhausted_count") or 0),
        "retries_cancelled": int(retries.get("cancelled_count") or 0),
        "message": message,
        "started_at": started_at,
        "finished_at": _now_iso(),
    }
    automation_repository.create_run(run)
    return {
        "run": _public_run(run),
        "schedules": _compact_schedule_result(schedules),
        "retries": _compact_retry_result(retries),
    }


def _system_actor(workspace: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": "SYSTEM-AUTOMATION",
        "email": "automation@viralpick.local",
        "display_name": "ViralPick Automation",
        "role": "owner",
        "status": "active",
        "workspace_id": workspace["workspace_id"],
        "workspace_name": workspace.get("workspace_name") or workspace["workspace_id"],
    }


def _compact_schedule_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "checked_at": result.get("checked_at"),
        "due_count": int(result.get("due_count") or 0),
        "executed_count": int(result.get("executed_count") or 0),
        "failed_count": int(result.get("failed_count") or 0),
        "failed": result.get("failed") or [],
    }


def _compact_retry_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "due_count": int(result.get("due_count") or 0),
        "processed_count": int(result.get("processed_count") or 0),
        "succeeded_count": int(result.get("succeeded_count") or 0),
        "pending_count": int(result.get("pending_count") or 0),
        "exhausted_count": int(result.get("exhausted_count") or 0),
        "cancelled_count": int(result.get("cancelled_count") or 0),
    }


def _public_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row.get("run_id"),
        "workspace_id": row.get("workspace_id"),
        "workspace_name": row.get("workspace_name"),
        "trigger": row.get("trigger"),
        "status": row.get("status"),
        "schedules_due": int(row.get("schedules_due") or 0),
        "schedules_executed": int(row.get("schedules_executed") or 0),
        "schedules_failed": int(row.get("schedules_failed") or 0),
        "retries_due": int(row.get("retries_due") or 0),
        "retries_processed": int(row.get("retries_processed") or 0),
        "retries_succeeded": int(row.get("retries_succeeded") or 0),
        "retries_exhausted": int(row.get("retries_exhausted") or 0),
        "retries_cancelled": int(row.get("retries_cancelled") or 0),
        "message": row.get("message") or "",
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
    }


def _totals(items: list[dict[str, Any]]) -> dict[str, int]:
    runs = [item.get("run", {}) for item in items]
    return {
        "schedules_due": sum(int(run.get("schedules_due") or 0) for run in runs),
        "schedules_executed": sum(int(run.get("schedules_executed") or 0) for run in runs),
        "schedules_failed": sum(int(run.get("schedules_failed") or 0) for run in runs),
        "retries_due": sum(int(run.get("retries_due") or 0) for run in runs),
        "retries_processed": sum(int(run.get("retries_processed") or 0) for run in runs),
        "retries_succeeded": sum(int(run.get("retries_succeeded") or 0) for run in runs),
        "retries_exhausted": sum(int(run.get("retries_exhausted") or 0) for run in runs),
        "retries_cancelled": sum(int(run.get("retries_cancelled") or 0) for run in runs),
    }


def _aggregate_status(items: list[dict[str, Any]]) -> str:
    statuses = {item.get("run", {}).get("status") for item in items}
    if "failed" in statuses:
        return "failed"
    if "warn" in statuses:
        return "warn"
    return "ok"


def _clean_optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
