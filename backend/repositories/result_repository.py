from __future__ import annotations

import json
from typing import Any

from backend.db import execute_script, execute_write, fetch_one


RESULT_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS analysis_reports (
    report_id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    product_id TEXT,
    category TEXT,
    title TEXT NOT NULL,
    report_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS forecast_results (
    forecast_id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    product_id TEXT,
    category TEXT,
    horizon_days INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    history_json TEXT NOT NULL,
    forecast_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

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
"""


def ensure_result_tables() -> None:
    execute_script(RESULT_TABLES_SQL)


def save_report(report: dict[str, Any]) -> None:
    ensure_result_tables()
    execute_write(
        """
        INSERT OR REPLACE INTO analysis_reports (
            report_id, scope_type, product_id, category, title, report_json, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            report["report_id"],
            report["scope_type"],
            report.get("product_id"),
            report.get("category"),
            report["title"],
            json.dumps(report, ensure_ascii=False),
            report["generated_at"],
        ],
    )


def get_report(report_id: str) -> dict[str, Any] | None:
    ensure_result_tables()
    row = fetch_one(
        "SELECT report_json FROM analysis_reports WHERE report_id = ?",
        [report_id],
    )
    if not row:
        return None
    return json.loads(row["report_json"])


def save_forecast(forecast: dict[str, Any]) -> None:
    ensure_result_tables()
    execute_write(
        """
        INSERT OR REPLACE INTO forecast_results (
            forecast_id, scope_type, product_id, category, horizon_days, model_name,
            history_json, forecast_json, summary_json, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            forecast["forecast_id"],
            forecast["scope"]["type"],
            forecast["scope"].get("product_id"),
            forecast["scope"].get("category"),
            forecast["horizon_days"],
            forecast["model_name"],
            json.dumps(forecast["history"], ensure_ascii=False),
            json.dumps(forecast["forecast"], ensure_ascii=False),
            json.dumps(forecast["summary"], ensure_ascii=False),
            forecast["generated_at"],
        ],
    )
