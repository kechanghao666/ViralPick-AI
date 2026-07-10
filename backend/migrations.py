from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Any

from backend.config import DATABASE_PATH


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    description: str
    apply: Callable[[sqlite3.Connection], None]

    @property
    def checksum(self) -> str:
        payload = f"{self.version}|{self.name}|{self.description}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_pending_migrations(
    db_path: Path | str = DATABASE_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    target = Path(db_path)
    if not target.exists():
        raise MigrationError(f"Database does not exist: {target}")

    if dry_run:
        status = get_migration_status(target)
        return {
            "database": str(target),
            "dry_run": True,
            "applied": [],
            "applied_migrations": status["applied"],
            "pending": status["pending"],
            "current_version": status["current_version"],
            "exists": status["exists"],
        }

    applied_now: list[dict[str, str]] = []
    connection = sqlite3.connect(target)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_schema_migrations_table(connection)
        applied = _applied_migrations(connection)
        _validate_applied_checksums(applied)

        for migration in MIGRATIONS:
            if migration.version in applied:
                continue
            try:
                migration.apply(connection)
                _record_migration(connection, migration)
                applied_now.append(_migration_payload(migration))
            except Exception as exc:
                connection.rollback()
                raise MigrationError(f"Migration {migration.version} failed: {exc}") from exc
        _apply_current_schema_maintenance(connection)
        connection.commit()
    finally:
        connection.close()

    status = get_migration_status(target)
    return {
        "database": str(target),
        "dry_run": False,
        "applied": applied_now,
        "applied_migrations": status["applied"],
        "pending": status["pending"],
        "current_version": status["current_version"],
        "exists": status["exists"],
    }


def get_migration_status(db_path: Path | str = DATABASE_PATH) -> dict[str, Any]:
    target = Path(db_path)
    if not target.exists():
        return {
            "database": str(target),
            "exists": False,
            "applied": [],
            "pending": [_migration_payload(migration) for migration in MIGRATIONS],
            "current_version": None,
        }

    connection = sqlite3.connect(target)
    try:
        connection.row_factory = sqlite3.Row
        if not _table_exists(connection, "schema_migrations"):
            applied: dict[str, dict[str, Any]] = {}
        else:
            applied = _applied_migrations(connection)
        _validate_applied_checksums(applied)
    finally:
        connection.close()

    pending = [
        _migration_payload(migration)
        for migration in MIGRATIONS
        if migration.version not in applied
    ]
    current_version = max(applied.keys()) if applied else None
    return {
        "database": str(target),
        "exists": True,
        "applied": list(applied.values()),
        "pending": pending,
        "current_version": current_version,
    }


def ensure_schema_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def mark_all_migrations_applied(connection: sqlite3.Connection) -> None:
    ensure_schema_migrations_table(connection)
    _apply_current_schema_maintenance(connection)
    applied = _applied_migrations(connection)
    _validate_applied_checksums(applied)
    for migration in MIGRATIONS:
        if migration.version not in applied:
            _record_migration(connection, migration)


def _migrate_auth_lockout_fields(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "users"):
        raise MigrationError("users table is missing; initialize the database before migrating")
    _add_column_if_missing(connection, "users", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(connection, "users", "locked_until", "TEXT")
    _add_column_if_missing(connection, "users", "password_changed_at", "TEXT")
    connection.execute(
        """
        UPDATE users
        SET failed_login_count = COALESCE(failed_login_count, 0),
            password_changed_at = COALESCE(password_changed_at, created_at)
        """
    )


def _migrate_brand_settings_table(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "workspaces") or not _table_exists(connection, "users"):
        raise MigrationError("workspace identity tables are missing; initialize the database before migrating")
    connection.execute(
        """
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
        )
        """
    )
    now = _now_iso()
    connection.execute(
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
        SELECT
            workspace_id,
            'ViralPick AI',
            '店铺经营分析报告',
            '',
            '#00a99d',
            '#f0a51b',
            'signal-grid',
            NULL,
            ?,
            ?
        FROM workspaces
        WHERE NOT EXISTS (
            SELECT 1 FROM brand_settings WHERE brand_settings.workspace_id = workspaces.workspace_id
        )
        """,
        [now, now],
    )


def _migrate_report_share_access_logs(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "report_shares"):
        raise MigrationError("report_shares table is missing; initialize the database before migrating")
    connection.execute(
        """
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
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_share_access_share
        ON report_share_access_logs(share_id, accessed_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_share_access_workspace
        ON report_share_access_logs(workspace_id, accessed_at DESC)
        """
    )


def _migrate_team_invitations(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "workspaces") or not _table_exists(connection, "users"):
        raise MigrationError("workspace identity tables are missing; initialize the database before migrating")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS team_invitations (
            invitation_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            email TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            token_preview TEXT NOT NULL,
            invited_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            accepted_at TEXT,
            revoked_at TEXT,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
            FOREIGN KEY (invited_by) REFERENCES users(user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_team_invitations_workspace
        ON team_invitations(workspace_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_team_invitations_email
        ON team_invitations(email, workspace_id, created_at DESC)
        """
    )


def _migrate_report_schedules(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "workspaces") or not _table_exists(connection, "users"):
        raise MigrationError("workspace identity tables are missing; initialize the database before migrating")
    if not _table_exists(connection, "analysis_reports"):
        raise MigrationError("analysis_reports table is missing; initialize the database before migrating")
    connection.execute(
        """
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
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_schedules_workspace
        ON report_schedules(workspace_id, status, next_run_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_schedules_due
        ON report_schedules(status, next_run_at)
        """
    )


def _migrate_report_deliveries(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "report_schedules"):
        raise MigrationError("report_schedules table is missing; apply report_schedules migration first")
    _add_column_if_missing(connection, "report_schedules", "delivery_channel", "TEXT NOT NULL DEFAULT 'none'")
    _add_column_if_missing(connection, "report_schedules", "recipients_json", "TEXT NOT NULL DEFAULT '[]'")
    connection.execute(
        """
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
            created_at TEXT NOT NULL,
            FOREIGN KEY (schedule_id) REFERENCES report_schedules(schedule_id),
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
            FOREIGN KEY (report_id) REFERENCES analysis_reports(report_id),
            FOREIGN KEY (share_id) REFERENCES report_shares(share_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_deliveries_schedule
        ON report_deliveries(schedule_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_deliveries_workspace
        ON report_deliveries(workspace_id, created_at DESC)
        """
    )


def _migrate_report_delivery_retries(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "report_deliveries"):
        raise MigrationError("report_deliveries table is missing; apply report_delivery_outbox migration first")
    _add_column_if_missing(connection, "report_deliveries", "retry_of_delivery_id", "TEXT")


def _migrate_report_delivery_retry_jobs(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "report_deliveries") or not _table_exists(connection, "report_schedules"):
        raise MigrationError("report delivery tables are missing; apply report delivery migrations first")
    connection.execute(
        """
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
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_delivery_retry_jobs_due
        ON report_delivery_retry_jobs(workspace_id, status, next_attempt_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_report_delivery_retry_jobs_delivery
        ON report_delivery_retry_jobs(workspace_id, original_delivery_id)
        """
    )


def _migrate_automation_runs(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "workspaces"):
        raise MigrationError("workspaces table is missing; initialize the database before migrating")
    connection.execute(
        """
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
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_runs_workspace
        ON automation_runs(workspace_id, started_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_runs_status
        ON automation_runs(status, started_at DESC)
        """
    )


def _migrate_domestic_ecommerce_fields(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "products") or not _table_exists(connection, "competitors"):
        raise MigrationError("product and competitor tables are required before adding domestic ecommerce fields")
    product_columns = {
        "platform": "TEXT NOT NULL DEFAULT ''",
        "brand": "TEXT NOT NULL DEFAULT ''",
        "shop_name": "TEXT NOT NULL DEFAULT ''",
        "image_url": "TEXT NOT NULL DEFAULT ''",
        "selling_points": "TEXT NOT NULL DEFAULT ''",
        "source_dataset": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in product_columns.items():
        _add_column_if_missing(connection, "products", column, definition)

    competitor_columns = {
        "competitor_platform": "TEXT NOT NULL DEFAULT ''",
        "competitor_shop_name": "TEXT NOT NULL DEFAULT ''",
        "competitor_image_url": "TEXT NOT NULL DEFAULT ''",
        "competitor_selling_point": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in competitor_columns.items():
        _add_column_if_missing(connection, "competitors", column, definition)


def _migrate_business_center_tables(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "products"):
        raise MigrationError("products table is required before adding business center tables")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS import_previews (
            preview_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            dataset_type TEXT NOT NULL,
            source_columns_json TEXT NOT NULL,
            field_mapping_json TEXT NOT NULL,
            preview_rows_json TEXT NOT NULL,
            raw_rows_json TEXT NOT NULL,
            quality_json TEXT NOT NULL,
            status TEXT NOT NULL,
            committed_job_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (committed_job_id) REFERENCES import_jobs(job_id)
        );

        CREATE TABLE IF NOT EXISTS orders_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT '',
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            order_count INTEGER NOT NULL DEFAULT 0,
            paid_amount REAL NOT NULL DEFAULT 0,
            customer_unit_price REAL NOT NULL DEFAULT 0,
            refund_amount REAL NOT NULL DEFAULT 0,
            conversion_rate REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS inventory_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            available_stock INTEGER NOT NULL DEFAULT 0,
            replenishment_threshold INTEGER NOT NULL DEFAULT 0,
            stockout_risk TEXT NOT NULL DEFAULT '',
            slow_moving_days INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS after_sales (
            after_sale_id TEXT PRIMARY KEY,
            date TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            refund_amount REAL NOT NULL DEFAULT 0,
            refund_count INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS ad_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT '',
            campaign_name TEXT NOT NULL DEFAULT '',
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            spend REAL NOT NULL DEFAULT 0,
            impressions INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            conversions INTEGER NOT NULL DEFAULT 0,
            revenue REAL NOT NULL DEFAULT 0,
            roi REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS traffic_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT '',
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            visitors INTEGER NOT NULL DEFAULT 0,
            page_views INTEGER NOT NULL DEFAULT 0,
            cart_adds INTEGER NOT NULL DEFAULT 0,
            favorites INTEGER NOT NULL DEFAULT 0,
            payment_conversion_rate REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS content_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT '',
            content_type TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL DEFAULT '',
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            impressions INTEGER NOT NULL DEFAULT 0,
            interactions INTEGER NOT NULL DEFAULT 0,
            guided_revenue REAL NOT NULL DEFAULT 0,
            effect_score REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE INDEX IF NOT EXISTS idx_import_previews_time
            ON import_previews(created_at);
        CREATE INDEX IF NOT EXISTS idx_orders_daily_product_date
            ON orders_daily(product_id, date);
        CREATE INDEX IF NOT EXISTS idx_inventory_daily_product_date
            ON inventory_daily(product_id, date);
        CREATE INDEX IF NOT EXISTS idx_after_sales_product
            ON after_sales(product_id, date);
        CREATE INDEX IF NOT EXISTS idx_ad_metrics_product_date
            ON ad_metrics(product_id, date);
        CREATE INDEX IF NOT EXISTS idx_traffic_metrics_product_date
            ON traffic_metrics(product_id, date);
        CREATE INDEX IF NOT EXISTS idx_content_metrics_product_date
            ON content_metrics(product_id, date);
        """
    )


def _apply_current_schema_maintenance(connection: sqlite3.Connection) -> None:
    if _table_exists(connection, "products"):
        _migrate_business_center_tables(connection)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version="20260629_001",
        name="auth_lockout_fields",
        description="Add failed login lockout columns and password change timestamp to users.",
        apply=_migrate_auth_lockout_fields,
    ),
    Migration(
        version="20260630_001",
        name="brand_settings_table",
        description="Add workspace brand settings for public report presentation templates.",
        apply=_migrate_brand_settings_table,
    ),
    Migration(
        version="20260630_002",
        name="report_share_access_logs",
        description="Add privacy-friendly access logs for public report share links.",
        apply=_migrate_report_share_access_logs,
    ),
    Migration(
        version="20260630_003",
        name="team_invitations",
        description="Add one-time team invitation tokens for member self-onboarding.",
        apply=_migrate_team_invitations,
    ),
    Migration(
        version="20260630_004",
        name="report_schedules",
        description="Add managed schedules for recurring operation report generation.",
        apply=_migrate_report_schedules,
    ),
    Migration(
        version="20260630_005",
        name="report_delivery_outbox",
        description="Add recipients and delivery outbox records for scheduled reports.",
        apply=_migrate_report_deliveries,
    ),
    Migration(
        version="20260630_006",
        name="report_delivery_retries",
        description="Track manual retry attempts for scheduled report deliveries.",
        apply=_migrate_report_delivery_retries,
    ),
    Migration(
        version="20260701_001",
        name="report_delivery_retry_jobs",
        description="Add retry queue jobs for automatic scheduled report delivery retries.",
        apply=_migrate_report_delivery_retry_jobs,
    ),
    Migration(
        version="20260701_002",
        name="automation_runs",
        description="Track background automation worker runs for schedules and delivery retries.",
        apply=_migrate_automation_runs,
    ),
    Migration(
        version="20260701_003",
        name="domestic_ecommerce_fields",
        description="Add domestic ecommerce product and competitor presentation fields.",
        apply=_migrate_domestic_ecommerce_fields,
    ),
)


def _applied_migrations(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT version, name, checksum, applied_at
        FROM schema_migrations
        ORDER BY version
        """
    ).fetchall()
    return {row["version"]: dict(row) for row in rows}


def _validate_applied_checksums(applied: dict[str, dict[str, Any]]) -> None:
    known = {migration.version: migration for migration in MIGRATIONS}
    for version, row in applied.items():
        migration = known.get(version)
        if migration and row.get("checksum") != migration.checksum:
            raise MigrationError(
                f"Migration checksum mismatch for {version}. "
                "Do not edit applied migrations; create a new migration instead."
            )


def _record_migration(connection: sqlite3.Connection, migration: Migration) -> None:
    connection.execute(
        """
        INSERT INTO schema_migrations (version, name, checksum, applied_at)
        VALUES (?, ?, ?, ?)
        """,
        [
            migration.version,
            migration.name,
            migration.checksum,
            _now_iso(),
        ],
    )


def _migration_payload(migration: Migration) -> dict[str, str]:
    return {
        "version": migration.version,
        "name": migration.name,
        "description": migration.description,
        "checksum": migration.checksum,
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table_name],
    ).fetchone()
    return bool(row)


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if _column_exists(connection, table_name, column_name):
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
