from __future__ import annotations

from typing import Any

from backend.db import execute_script, execute_write, fetch_all, fetch_one


AUTOMATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS automation_runs (
    run_id TEXT PRIMARY KEY,
    workspace_id TEXT,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    schedules_due INTEGER NOT NULL DEFAULT 0,
    schedules_executed INTEGER NOT NULL DEFAULT 0,
    schedules_failed INTEGER NOT NULL DEFAULT 0,
    retries_due INTEGER NOT NULL DEFAULT 0,
    retries_processed INTEGER NOT NULL DEFAULT 0,
    retries_succeeded INTEGER NOT NULL DEFAULT 0,
    retries_exhausted INTEGER NOT NULL DEFAULT 0,
    retries_cancelled INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_automation_runs_workspace
    ON automation_runs(workspace_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_automation_runs_status
    ON automation_runs(status, started_at DESC);
"""


def ensure_automation_table() -> None:
    execute_script(AUTOMATION_TABLE_SQL)


def list_active_workspaces(workspace_id: str | None = None) -> list[dict[str, Any]]:
    ensure_automation_table()
    params: list[Any] = []
    where = "status = 'active'"
    if workspace_id:
        where += " AND workspace_id = ?"
        params.append(workspace_id)
    return fetch_all(
        f"""
        SELECT workspace_id, workspace_name, plan, status
        FROM workspaces
        WHERE {where}
        ORDER BY created_at ASC
        """,
        params,
    )


def create_run(run: dict[str, Any]) -> None:
    ensure_automation_table()
    execute_write(
        """
        INSERT INTO automation_runs (
            run_id, workspace_id, trigger, status,
            schedules_due, schedules_executed, schedules_failed,
            retries_due, retries_processed, retries_succeeded, retries_exhausted, retries_cancelled,
            message, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run["run_id"],
            run.get("workspace_id"),
            run["trigger"],
            run["status"],
            int(run.get("schedules_due") or 0),
            int(run.get("schedules_executed") or 0),
            int(run.get("schedules_failed") or 0),
            int(run.get("retries_due") or 0),
            int(run.get("retries_processed") or 0),
            int(run.get("retries_succeeded") or 0),
            int(run.get("retries_exhausted") or 0),
            int(run.get("retries_cancelled") or 0),
            run.get("message"),
            run["started_at"],
            run["finished_at"],
        ],
    )


def list_runs(workspace_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_automation_table()
    params: list[Any] = []
    where = "1 = 1"
    if workspace_id:
        where += " AND r.workspace_id = ?"
        params.append(workspace_id)
    params.append(limit)
    return fetch_all(
        f"""
        SELECT r.*, w.workspace_name
        FROM automation_runs r
        LEFT JOIN workspaces w ON w.workspace_id = r.workspace_id
        WHERE {where}
        ORDER BY r.started_at DESC
        LIMIT ?
        """,
        params,
    )


def get_run(run_id: str) -> dict[str, Any] | None:
    ensure_automation_table()
    return fetch_one(
        """
        SELECT r.*, w.workspace_name
        FROM automation_runs r
        LEFT JOIN workspaces w ON w.workspace_id = r.workspace_id
        WHERE r.run_id = ?
        """,
        [run_id],
    )
