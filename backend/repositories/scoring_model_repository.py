from __future__ import annotations

from typing import Any

from backend.db import execute_script, execute_write, fetch_all, fetch_one


SCORING_MODEL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scoring_models (
    model_id TEXT PRIMARY KEY,
    workspace_id TEXT,
    model_name TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    activated_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_scoring_models_status
    ON scoring_models(workspace_id, status, activated_at);
"""


def ensure_scoring_model_table() -> None:
    execute_script(SCORING_MODEL_TABLE_SQL)


def get_active_model(workspace_id: str | None = None) -> dict[str, Any] | None:
    ensure_scoring_model_table()
    if workspace_id:
        row = fetch_one(
            """
            SELECT *
            FROM scoring_models
            WHERE workspace_id = ? AND status = 'active'
            ORDER BY activated_at DESC
            LIMIT 1
            """,
            [workspace_id],
        )
        if row:
            return row
    return fetch_one(
        """
        SELECT *
        FROM scoring_models
        WHERE status = 'active'
        ORDER BY activated_at DESC
        LIMIT 1
        """
    )


def list_models(workspace_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    ensure_scoring_model_table()
    if workspace_id:
        return fetch_all(
            """
            SELECT *
            FROM scoring_models
            WHERE workspace_id = ?
            ORDER BY activated_at DESC
            LIMIT ?
            """,
            [workspace_id, limit],
        )
    return fetch_all(
        """
        SELECT *
        FROM scoring_models
        ORDER BY activated_at DESC
        LIMIT ?
        """,
        [limit],
    )


def archive_active_models(workspace_id: str | None, activated_at: str) -> None:
    ensure_scoring_model_table()
    if workspace_id:
        execute_write(
            """
            UPDATE scoring_models
            SET status = 'archived'
            WHERE workspace_id = ? AND status = 'active'
            """,
            [workspace_id],
        )
        return
    execute_write(
        """
        UPDATE scoring_models
        SET status = 'archived'
        WHERE status = 'active' AND activated_at <= ?
        """,
        [activated_at],
    )


def create_model(model: dict[str, Any]) -> None:
    ensure_scoring_model_table()
    execute_write(
        """
        INSERT INTO scoring_models (
            model_id, workspace_id, model_name, weights_json, status, note,
            created_by, created_at, activated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            model["model_id"],
            model.get("workspace_id"),
            model["model_name"],
            model["weights_json"],
            model.get("status", "active"),
            model.get("note"),
            model.get("created_by"),
            model["created_at"],
            model["activated_at"],
        ],
    )
