from __future__ import annotations

from typing import Any

from backend.db import execute_script, execute_write, fetch_all, fetch_one


REPORT_SHARE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_shares (
    share_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    workspace_id TEXT,
    created_by TEXT,
    token_hash TEXT NOT NULL UNIQUE,
    token_preview TEXT NOT NULL,
    permission TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (report_id) REFERENCES analysis_reports(report_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_report_shares_report
    ON report_shares(report_id, created_at);

CREATE INDEX IF NOT EXISTS idx_report_shares_workspace
    ON report_shares(workspace_id, created_at);

CREATE TABLE IF NOT EXISTS report_share_access_logs (
    access_id TEXT PRIMARY KEY,
    share_id TEXT NOT NULL,
    workspace_id TEXT,
    accessed_at TEXT NOT NULL,
    visitor_hash TEXT NOT NULL,
    user_agent TEXT,
    referrer TEXT,
    FOREIGN KEY (share_id) REFERENCES report_shares(share_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_report_share_access_share
    ON report_share_access_logs(share_id, accessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_report_share_access_workspace
    ON report_share_access_logs(workspace_id, accessed_at DESC);
"""


def ensure_report_share_table() -> None:
    execute_script(REPORT_SHARE_TABLE_SQL)


def create_share(share: dict[str, Any]) -> None:
    ensure_report_share_table()
    execute_write(
        """
        INSERT INTO report_shares (
            share_id, report_id, workspace_id, created_by, token_hash, token_preview,
            permission, expires_at, revoked_at, created_at, last_accessed_at, access_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            share["share_id"],
            share["report_id"],
            share.get("workspace_id"),
            share.get("created_by"),
            share["token_hash"],
            share["token_preview"],
            share.get("permission", "view"),
            share["expires_at"],
            share.get("revoked_at"),
            share["created_at"],
            share.get("last_accessed_at"),
            share.get("access_count", 0),
        ],
    )


def get_share(share_id: str) -> dict[str, Any] | None:
    ensure_report_share_table()
    return fetch_one("SELECT * FROM report_shares WHERE share_id = ?", [share_id])


def get_share_by_token_hash(token_hash: str) -> dict[str, Any] | None:
    ensure_report_share_table()
    return fetch_one("SELECT * FROM report_shares WHERE token_hash = ?", [token_hash])


def list_shares(report_id: str, workspace_id: str | None = None) -> list[dict[str, Any]]:
    ensure_report_share_table()
    if workspace_id:
        return fetch_all(
            """
            SELECT *
            FROM report_shares
            WHERE report_id = ? AND workspace_id = ?
            ORDER BY created_at DESC
            """,
            [report_id, workspace_id],
        )
    return fetch_all(
        """
        SELECT *
        FROM report_shares
        WHERE report_id = ?
        ORDER BY created_at DESC
        """,
        [report_id],
    )


def revoke_share(share_id: str, revoked_at: str) -> None:
    ensure_report_share_table()
    execute_write(
        """
        UPDATE report_shares
        SET revoked_at = ?
        WHERE share_id = ? AND revoked_at IS NULL
        """,
        [revoked_at, share_id],
    )


def record_access(share_id: str, accessed_at: str) -> None:
    ensure_report_share_table()
    execute_write(
        """
        UPDATE report_shares
        SET last_accessed_at = ?,
            access_count = access_count + 1
        WHERE share_id = ?
        """,
        [accessed_at, share_id],
    )


def record_access_event(event: dict[str, Any]) -> None:
    ensure_report_share_table()
    execute_write(
        """
        INSERT INTO report_share_access_logs (
            access_id, share_id, workspace_id, accessed_at, visitor_hash, user_agent, referrer
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            event["access_id"],
            event["share_id"],
            event.get("workspace_id"),
            event["accessed_at"],
            event["visitor_hash"],
            event.get("user_agent"),
            event.get("referrer"),
        ],
    )


def list_access_logs(
    share_id: str,
    workspace_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    ensure_report_share_table()
    if workspace_id:
        return fetch_all(
            """
            SELECT *
            FROM report_share_access_logs
            WHERE share_id = ? AND workspace_id = ?
            ORDER BY accessed_at DESC
            LIMIT ? OFFSET ?
            """,
            [share_id, workspace_id, limit, offset],
        )
    return fetch_all(
        """
        SELECT *
        FROM report_share_access_logs
        WHERE share_id = ?
        ORDER BY accessed_at DESC
        LIMIT ? OFFSET ?
        """,
        [share_id, limit, offset],
    )


def access_summary(share_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    ensure_report_share_table()
    if workspace_id:
        return fetch_one(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(DISTINCT visitor_hash) AS unique_visitors,
                MAX(accessed_at) AS latest_accessed_at
            FROM report_share_access_logs
            WHERE share_id = ? AND workspace_id = ?
            """,
            [share_id, workspace_id],
        ) or {}
    return fetch_one(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT visitor_hash) AS unique_visitors,
            MAX(accessed_at) AS latest_accessed_at
        FROM report_share_access_logs
        WHERE share_id = ?
        """,
        [share_id],
    ) or {}
