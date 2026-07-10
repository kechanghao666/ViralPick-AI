from __future__ import annotations

from typing import Any

from backend.db import execute_write, fetch_all, fetch_one


def create_job(job: dict[str, Any]) -> None:
    execute_write(
        """
        INSERT INTO import_jobs (
            job_id, workspace_id, user_id, dataset_type, filename, mode,
            status, row_count, error_message, summary_json, created_at, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            job["job_id"],
            job.get("workspace_id"),
            job.get("user_id"),
            job["dataset_type"],
            job["filename"],
            job["mode"],
            job["status"],
            job.get("row_count", 0),
            job.get("error_message"),
            job["summary_json"],
            job["created_at"],
            job.get("completed_at"),
        ],
    )


def update_job(
    job_id: str,
    status: str,
    row_count: int,
    summary_json: str,
    completed_at: str | None,
    error_message: str | None = None,
) -> None:
    execute_write(
        """
        UPDATE import_jobs
        SET status = ?,
            row_count = ?,
            error_message = ?,
            summary_json = ?,
            completed_at = ?
        WHERE job_id = ?
        """,
        [status, row_count, error_message, summary_json, completed_at, job_id],
    )


def list_jobs(workspace_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    if workspace_id:
        return fetch_all(
            """
            SELECT *
            FROM import_jobs
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [workspace_id, limit],
        )
    return fetch_all(
        """
        SELECT *
        FROM import_jobs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [limit],
    )


def get_job(job_id: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT *
        FROM import_jobs
        WHERE job_id = ?
        """,
        [job_id],
    )


def existing_product_ids(product_ids: list[str]) -> set[str]:
    if not product_ids:
        return set()
    placeholders = ",".join("?" for _ in product_ids)
    rows = fetch_all(
        f"SELECT product_id FROM products WHERE product_id IN ({placeholders})",
        product_ids,
    )
    return {str(row["product_id"]) for row in rows}
