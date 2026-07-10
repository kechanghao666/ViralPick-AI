from __future__ import annotations

from typing import Any

from backend.db import execute_script, execute_write, fetch_one


BRAND_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS brand_settings (
    workspace_id TEXT PRIMARY KEY,
    brand_name TEXT NOT NULL,
    report_label TEXT NOT NULL,
    logo_url TEXT,
    primary_color TEXT NOT NULL,
    accent_color TEXT NOT NULL,
    cover_style TEXT NOT NULL,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (updated_by) REFERENCES users(user_id)
);
"""


def ensure_brand_settings_table() -> None:
    execute_script(BRAND_SETTINGS_TABLE_SQL)


def get_brand_settings(workspace_id: str) -> dict[str, Any] | None:
    ensure_brand_settings_table()
    return fetch_one(
        """
        SELECT
            workspace_id,
            brand_name,
            report_label,
            logo_url,
            primary_color,
            accent_color,
            cover_style,
            updated_by,
            created_at,
            updated_at
        FROM brand_settings
        WHERE workspace_id = ?
        """,
        [workspace_id],
    )


def upsert_brand_settings(settings: dict[str, Any]) -> None:
    ensure_brand_settings_table()
    execute_write(
        """
        INSERT INTO brand_settings (
            workspace_id,
            brand_name,
            report_label,
            logo_url,
            primary_color,
            accent_color,
            cover_style,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id) DO UPDATE SET
            brand_name = excluded.brand_name,
            report_label = excluded.report_label,
            logo_url = excluded.logo_url,
            primary_color = excluded.primary_color,
            accent_color = excluded.accent_color,
            cover_style = excluded.cover_style,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
        """,
        [
            settings["workspace_id"],
            settings["brand_name"],
            settings["report_label"],
            settings.get("logo_url"),
            settings["primary_color"],
            settings["accent_color"],
            settings["cover_style"],
            settings.get("updated_by"),
            settings["created_at"],
            settings["updated_at"],
        ],
    )
