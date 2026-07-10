from __future__ import annotations

import sqlite3
from pathlib import Path

from backend import migrations
from backend.config import DATABASE_PATH


def _columns(db_path: Path, table_name: str) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()]


LEGACY_PRODUCT_TABLES_SQL = """
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    stock_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    avg_price REAL NOT NULL,
    total_sales_quantity INTEGER NOT NULL,
    total_gmv REAL NOT NULL,
    order_count INTEGER NOT NULL,
    active_days INTEGER NOT NULL,
    first_sale_date TEXT NOT NULL,
    last_sale_date TEXT NOT NULL,
    country_count INTEGER NOT NULL,
    buyer_count INTEGER NOT NULL,
    comment_count INTEGER NOT NULL,
    rating REAL NOT NULL,
    positive_rate REAL NOT NULL,
    sales_growth_rate REAL NOT NULL,
    gmv_growth_rate REAL NOT NULL,
    price_competitiveness REAL NOT NULL,
    hot_potential_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    data_source TEXT NOT NULL
);
CREATE TABLE competitors (
    competitor_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    competitor_name TEXT NOT NULL,
    category TEXT NOT NULL,
    competitor_price REAL NOT NULL,
    competitor_sales_quantity INTEGER NOT NULL,
    competitor_rating REAL NOT NULL,
    competitor_positive_rate REAL NOT NULL,
    main_selling_point TEXT NOT NULL,
    data_type TEXT NOT NULL,
    note TEXT NOT NULL
);
"""


def test_migrate_database_adds_auth_lockout_fields_to_legacy_users_table(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE workspaces (
                workspace_id TEXT PRIMARY KEY,
                workspace_name TEXT NOT NULL,
                plan TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
            );
            CREATE TABLE report_shares (
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
                access_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE analysis_reports (
                report_id TEXT PRIMARY KEY,
                scope_type TEXT NOT NULL,
                product_id TEXT,
                category TEXT,
                title TEXT NOT NULL,
                report_json TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );
            """ + LEGACY_PRODUCT_TABLES_SQL + """
            INSERT INTO workspaces VALUES ('W-LEGACY', 'Legacy', 'trial', 'active', '2026-06-01T00:00:00Z');
            INSERT INTO users (
                user_id, workspace_id, email, password_hash, display_name, role, status, created_at
            ) VALUES (
                'U-LEGACY', 'W-LEGACY', 'legacy@example.com', 'hash', 'Legacy User',
                'owner', 'active', '2026-06-01T00:00:00Z'
            );
            """
        )

    result = migrations.apply_pending_migrations(db_path)
    assert [item["version"] for item in result["applied"]] == [
        "20260629_001",
        "20260630_001",
        "20260630_002",
        "20260630_003",
        "20260630_004",
        "20260630_005",
        "20260630_006",
        "20260701_001",
        "20260701_002",
        "20260701_003",
    ]
    assert result["pending"] == []

    columns = _columns(db_path, "users")
    assert "failed_login_count" in columns
    assert "locked_until" in columns
    assert "password_changed_at" in columns

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT failed_login_count, locked_until, password_changed_at
            FROM users
            WHERE user_id = 'U-LEGACY'
            """
        ).fetchone()
    assert row == (0, None, "2026-06-01T00:00:00Z")
    assert "workspace_id" in _columns(db_path, "brand_settings")
    assert "visitor_hash" in _columns(db_path, "report_share_access_logs")
    assert "token_hash" in _columns(db_path, "team_invitations")
    assert "next_run_at" in _columns(db_path, "report_schedules")
    assert "recipients_json" in _columns(db_path, "report_schedules")
    assert "delivery_id" in _columns(db_path, "report_deliveries")
    assert "retry_of_delivery_id" in _columns(db_path, "report_deliveries")
    assert "job_id" in _columns(db_path, "report_delivery_retry_jobs")
    assert "next_attempt_at" in _columns(db_path, "report_delivery_retry_jobs")
    assert "run_id" in _columns(db_path, "automation_runs")
    assert "schedules_executed" in _columns(db_path, "automation_runs")
    assert "platform" in _columns(db_path, "products")
    assert "image_url" in _columns(db_path, "products")
    assert "competitor_platform" in _columns(db_path, "competitors")

    with sqlite3.connect(db_path) as connection:
        brand = connection.execute(
            """
            SELECT brand_name, report_label, primary_color, accent_color, cover_style
            FROM brand_settings
            WHERE workspace_id = 'W-LEGACY'
            """
        ).fetchone()
    assert brand == ("ViralPick AI", "店铺经营分析报告", "#00a99d", "#f0a51b", "signal-grid")


def test_migrate_database_is_idempotent(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE workspaces (
                workspace_id TEXT PRIMARY KEY,
                workspace_name TEXT NOT NULL,
                plan TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE report_shares (
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
                access_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE analysis_reports (
                report_id TEXT PRIMARY KEY,
                scope_type TEXT NOT NULL,
                product_id TEXT,
                category TEXT,
                title TEXT NOT NULL,
                report_json TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );
            """ + LEGACY_PRODUCT_TABLES_SQL + """
            INSERT INTO workspaces VALUES ('W-LEGACY', 'Legacy', 'trial', 'active', '2026-06-01T00:00:00Z');
            """
        )

    first = migrations.apply_pending_migrations(db_path)
    second = migrations.apply_pending_migrations(db_path)

    assert len(first["applied"]) == 10
    assert second["applied"] == []
    assert second["pending"] == []


def test_initialized_database_records_current_schema_migration(initialized_database):
    status = migrations.get_migration_status(DATABASE_PATH)
    assert status["pending"] == []
    assert status["current_version"] == migrations.MIGRATIONS[-1].version
