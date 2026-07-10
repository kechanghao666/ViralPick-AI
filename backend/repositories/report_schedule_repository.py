from __future__ import annotations

from typing import Any

from backend.db import execute_script, execute_write, fetch_all, fetch_one


REPORT_SCHEDULE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_schedules (
    schedule_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    schedule_name TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    product_id TEXT,
    frequency TEXT NOT NULL,
    run_time TEXT NOT NULL,
    weekday INTEGER,
    monthday INTEGER,
    timezone TEXT NOT NULL,
    use_llm INTEGER NOT NULL DEFAULT 0,
    export_format TEXT NOT NULL DEFAULT 'docx',
    delivery_channel TEXT NOT NULL DEFAULT 'none',
    recipients_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    next_run_at TEXT NOT NULL,
    last_run_at TEXT,
    last_report_id TEXT,
    last_error TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (last_report_id) REFERENCES analysis_reports(report_id)
);

CREATE INDEX IF NOT EXISTS idx_report_schedules_workspace
    ON report_schedules(workspace_id, status, next_run_at);

CREATE INDEX IF NOT EXISTS idx_report_schedules_due
    ON report_schedules(status, next_run_at);

CREATE TABLE IF NOT EXISTS report_deliveries (
    delivery_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipients_json TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    message TEXT,
    share_id TEXT,
    export_format TEXT,
    attachment_filename TEXT,
    retry_of_delivery_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (schedule_id) REFERENCES report_schedules(schedule_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (report_id) REFERENCES analysis_reports(report_id),
    FOREIGN KEY (share_id) REFERENCES report_shares(share_id),
    FOREIGN KEY (retry_of_delivery_id) REFERENCES report_deliveries(delivery_id)
);

CREATE INDEX IF NOT EXISTS idx_report_deliveries_schedule
    ON report_deliveries(schedule_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_report_deliveries_workspace
    ON report_deliveries(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS report_delivery_retry_jobs (
    job_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    original_delivery_id TEXT NOT NULL,
    latest_delivery_id TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TEXT NOT NULL,
    last_attempt_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (schedule_id) REFERENCES report_schedules(schedule_id),
    FOREIGN KEY (original_delivery_id) REFERENCES report_deliveries(delivery_id),
    FOREIGN KEY (latest_delivery_id) REFERENCES report_deliveries(delivery_id)
);

CREATE INDEX IF NOT EXISTS idx_report_delivery_retry_jobs_due
    ON report_delivery_retry_jobs(workspace_id, status, next_attempt_at);

CREATE INDEX IF NOT EXISTS idx_report_delivery_retry_jobs_delivery
    ON report_delivery_retry_jobs(workspace_id, original_delivery_id);
"""


def ensure_report_schedule_table() -> None:
    execute_script(REPORT_SCHEDULE_TABLE_SQL)


def create_schedule(schedule: dict[str, Any]) -> None:
    ensure_report_schedule_table()
    execute_write(
        """
        INSERT INTO report_schedules (
            schedule_id, workspace_id, created_by, schedule_name, scope_type, product_id,
            frequency, run_time, weekday, monthday, timezone, use_llm, export_format,
            delivery_channel, recipients_json, status, next_run_at, last_run_at, last_report_id, last_error, run_count,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            schedule["schedule_id"],
            schedule["workspace_id"],
            schedule["created_by"],
            schedule["schedule_name"],
            schedule["scope_type"],
            schedule.get("product_id"),
            schedule["frequency"],
            schedule["run_time"],
            schedule.get("weekday"),
            schedule.get("monthday"),
            schedule["timezone"],
            1 if schedule.get("use_llm") else 0,
            schedule["export_format"],
            schedule.get("delivery_channel", "none"),
            schedule.get("recipients_json", "[]"),
            schedule["status"],
            schedule["next_run_at"],
            schedule.get("last_run_at"),
            schedule.get("last_report_id"),
            schedule.get("last_error"),
            int(schedule.get("run_count") or 0),
            schedule["created_at"],
            schedule["updated_at"],
        ],
    )


def list_schedules(workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_report_schedule_table()
    return fetch_all(
        """
        SELECT
            s.*,
            p.product_name,
            u.display_name AS created_by_name,
            d.delivery_id AS latest_delivery_id,
            d.status AS latest_delivery_status,
            d.reason AS latest_delivery_reason,
            d.message AS latest_delivery_message,
            d.created_at AS latest_delivery_at
        FROM report_schedules s
        LEFT JOIN products p ON p.product_id = s.product_id
        LEFT JOIN users u ON u.user_id = s.created_by
        LEFT JOIN report_deliveries d ON d.delivery_id = (
            SELECT delivery_id
            FROM report_deliveries
            WHERE schedule_id = s.schedule_id
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
        )
        WHERE s.workspace_id = ?
        ORDER BY
            CASE s.status WHEN 'active' THEN 1 WHEN 'paused' THEN 2 ELSE 3 END,
            s.next_run_at ASC,
            s.created_at DESC
        LIMIT ?
        """,
        [workspace_id, limit],
    )


def get_schedule(workspace_id: str, schedule_id: str) -> dict[str, Any] | None:
    ensure_report_schedule_table()
    return fetch_one(
        """
        SELECT
            s.*,
            p.product_name,
            u.display_name AS created_by_name,
            d.delivery_id AS latest_delivery_id,
            d.status AS latest_delivery_status,
            d.reason AS latest_delivery_reason,
            d.message AS latest_delivery_message,
            d.created_at AS latest_delivery_at
        FROM report_schedules s
        LEFT JOIN products p ON p.product_id = s.product_id
        LEFT JOIN users u ON u.user_id = s.created_by
        LEFT JOIN report_deliveries d ON d.delivery_id = (
            SELECT delivery_id
            FROM report_deliveries
            WHERE schedule_id = s.schedule_id
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
        )
        WHERE s.workspace_id = ? AND s.schedule_id = ?
        """,
        [workspace_id, schedule_id],
    )


def list_due_schedules(workspace_id: str, now_iso: str, limit: int = 20) -> list[dict[str, Any]]:
    ensure_report_schedule_table()
    return fetch_all(
        """
        SELECT
            s.*,
            p.product_name,
            u.display_name AS created_by_name,
            d.delivery_id AS latest_delivery_id,
            d.status AS latest_delivery_status,
            d.reason AS latest_delivery_reason,
            d.message AS latest_delivery_message,
            d.created_at AS latest_delivery_at
        FROM report_schedules s
        LEFT JOIN products p ON p.product_id = s.product_id
        LEFT JOIN users u ON u.user_id = s.created_by
        LEFT JOIN report_deliveries d ON d.delivery_id = (
            SELECT delivery_id
            FROM report_deliveries
            WHERE schedule_id = s.schedule_id
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
        )
        WHERE s.workspace_id = ?
          AND s.status = 'active'
          AND s.next_run_at <= ?
        ORDER BY s.next_run_at ASC
        LIMIT ?
        """,
        [workspace_id, now_iso, limit],
    )


def update_schedule(workspace_id: str, schedule_id: str, fields: dict[str, Any]) -> int:
    ensure_report_schedule_table()
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    if not assignments:
        return 0
    params.extend([workspace_id, schedule_id])
    return execute_write(
        f"""
        UPDATE report_schedules
        SET {", ".join(assignments)}
        WHERE workspace_id = ? AND schedule_id = ?
        """,
        params,
    )


def create_delivery(delivery: dict[str, Any]) -> None:
    ensure_report_schedule_table()
    execute_write(
        """
        INSERT INTO report_deliveries (
            delivery_id, schedule_id, workspace_id, report_id, channel, recipients_json,
            status, reason, message, share_id, export_format, attachment_filename, retry_of_delivery_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            delivery["delivery_id"],
            delivery["schedule_id"],
            delivery["workspace_id"],
            delivery["report_id"],
            delivery["channel"],
            delivery["recipients_json"],
            delivery["status"],
            delivery.get("reason"),
            delivery.get("message"),
            delivery.get("share_id"),
            delivery.get("export_format"),
            delivery.get("attachment_filename"),
            delivery.get("retry_of_delivery_id"),
            delivery["created_at"],
        ],
    )


def get_delivery(workspace_id: str, delivery_id: str) -> dict[str, Any] | None:
    ensure_report_schedule_table()
    return fetch_one(
        """
        SELECT *
        FROM report_deliveries
        WHERE workspace_id = ? AND delivery_id = ?
        """,
        [workspace_id, delivery_id],
    )


def list_deliveries(workspace_id: str, schedule_id: str, limit: int = 20) -> list[dict[str, Any]]:
    ensure_report_schedule_table()
    return fetch_all(
        """
        SELECT *
        FROM report_deliveries
        WHERE workspace_id = ? AND schedule_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?
        """,
        [workspace_id, schedule_id, limit],
    )


def create_retry_job(job: dict[str, Any]) -> None:
    ensure_report_schedule_table()
    execute_write(
        """
        INSERT INTO report_delivery_retry_jobs (
            job_id, workspace_id, schedule_id, original_delivery_id, latest_delivery_id,
            status, reason, attempts, max_attempts, next_attempt_at, last_attempt_at,
            last_error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            job["job_id"],
            job["workspace_id"],
            job["schedule_id"],
            job["original_delivery_id"],
            job.get("latest_delivery_id"),
            job["status"],
            job.get("reason"),
            int(job.get("attempts") or 0),
            int(job.get("max_attempts") or 0),
            job["next_attempt_at"],
            job.get("last_attempt_at"),
            job.get("last_error"),
            job["created_at"],
            job["updated_at"],
        ],
    )


def get_retry_job(workspace_id: str, job_id: str) -> dict[str, Any] | None:
    ensure_report_schedule_table()
    return fetch_one(
        """
        SELECT j.*, s.schedule_name, s.export_format, d.report_id AS original_report_id
        FROM report_delivery_retry_jobs j
        LEFT JOIN report_schedules s ON s.schedule_id = j.schedule_id
        LEFT JOIN report_deliveries d ON d.delivery_id = j.original_delivery_id
        WHERE j.workspace_id = ? AND j.job_id = ?
        """,
        [workspace_id, job_id],
    )


def get_open_retry_job_for_delivery(workspace_id: str, delivery_id: str) -> dict[str, Any] | None:
    ensure_report_schedule_table()
    return fetch_one(
        """
        SELECT *
        FROM report_delivery_retry_jobs
        WHERE workspace_id = ?
          AND original_delivery_id = ?
          AND status IN ('pending', 'running')
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        [workspace_id, delivery_id],
    )


def list_retry_jobs(workspace_id: str, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_report_schedule_table()
    params: list[Any] = [workspace_id]
    where = "j.workspace_id = ?"
    if status:
        where += " AND j.status = ?"
        params.append(status)
    params.append(limit)
    return fetch_all(
        f"""
        SELECT
            j.*,
            s.schedule_name,
            s.export_format,
            d.report_id AS original_report_id,
            latest.status AS latest_delivery_status,
            latest.reason AS latest_delivery_reason
        FROM report_delivery_retry_jobs j
        LEFT JOIN report_schedules s ON s.schedule_id = j.schedule_id
        LEFT JOIN report_deliveries d ON d.delivery_id = j.original_delivery_id
        LEFT JOIN report_deliveries latest ON latest.delivery_id = j.latest_delivery_id
        WHERE {where}
        ORDER BY
            CASE j.status WHEN 'pending' THEN 1 WHEN 'running' THEN 2 WHEN 'succeeded' THEN 3 ELSE 4 END,
            j.next_attempt_at ASC,
            j.updated_at DESC
        LIMIT ?
        """,
        params,
    )


def list_due_retry_jobs(workspace_id: str, now_iso: str, limit: int = 20) -> list[dict[str, Any]]:
    ensure_report_schedule_table()
    return fetch_all(
        """
        SELECT *
        FROM report_delivery_retry_jobs
        WHERE workspace_id = ?
          AND status = 'pending'
          AND next_attempt_at <= ?
        ORDER BY next_attempt_at ASC, created_at ASC
        LIMIT ?
        """,
        [workspace_id, now_iso, limit],
    )


def update_retry_job(workspace_id: str, job_id: str, fields: dict[str, Any]) -> int:
    ensure_report_schedule_table()
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    if not assignments:
        return 0
    params.extend([workspace_id, job_id])
    return execute_write(
        f"""
        UPDATE report_delivery_retry_jobs
        SET {", ".join(assignments)}
        WHERE workspace_id = ? AND job_id = ?
        """,
        params,
    )
