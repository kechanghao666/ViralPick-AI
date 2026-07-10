from __future__ import annotations

import argparse
import os
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from werkzeug.security import generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import migrations as db_migrations

PROCESSED_DIR = ROOT_DIR / "data" / "processed"
DATABASE_DIR = ROOT_DIR / "data" / "database"
DATABASE_PATH = DATABASE_DIR / "viralpick.db"


CSV_TABLES = {
    "products": PROCESSED_DIR / "products.csv",
    "sales_daily": PROCESSED_DIR / "sales_daily.csv",
    "comments": PROCESSED_DIR / "comments.csv",
    "video_metrics": PROCESSED_DIR / "video_metrics.csv",
    "competitors": PROCESSED_DIR / "competitors.csv",
    "orders_daily": PROCESSED_DIR / "orders_daily.csv",
    "inventory_daily": PROCESSED_DIR / "inventory_daily.csv",
    "after_sales": PROCESSED_DIR / "after_sales.csv",
    "ad_metrics": PROCESSED_DIR / "ad_metrics.csv",
    "traffic_metrics": PROCESSED_DIR / "traffic_metrics.csv",
    "content_metrics": PROCESSED_DIR / "content_metrics.csv",
}


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_category_summary;
DROP VIEW IF EXISTS v_product_performance;
DROP TABLE IF EXISTS report_share_access_logs;
DROP TABLE IF EXISTS report_delivery_retry_jobs;
DROP TABLE IF EXISTS report_deliveries;
DROP TABLE IF EXISTS report_shares;
DROP TABLE IF EXISTS automation_runs;
DROP TABLE IF EXISTS forecast_results;
DROP TABLE IF EXISTS report_schedules;
DROP TABLE IF EXISTS analysis_reports;
DROP TABLE IF EXISTS scoring_models;
DROP TABLE IF EXISTS import_jobs;
DROP TABLE IF EXISTS import_previews;
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS api_tokens;
DROP TABLE IF EXISTS brand_settings;
DROP TABLE IF EXISTS team_invitations;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS workspaces;
DROP TABLE IF EXISTS dataset_metadata;
DROP TABLE IF EXISTS content_metrics;
DROP TABLE IF EXISTS traffic_metrics;
DROP TABLE IF EXISTS ad_metrics;
DROP TABLE IF EXISTS after_sales;
DROP TABLE IF EXISTS inventory_daily;
DROP TABLE IF EXISTS orders_daily;
DROP TABLE IF EXISTS competitors;
DROP TABLE IF EXISTS video_metrics;
DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS sales_daily;
DROP TABLE IF EXISTS products;

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    stock_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    shop_name TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    selling_points TEXT NOT NULL DEFAULT '',
    source_dataset TEXT NOT NULL DEFAULT '',
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

CREATE TABLE sales_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    sales_quantity INTEGER NOT NULL,
    gmv REAL NOT NULL,
    order_count INTEGER NOT NULL,
    avg_unit_price REAL NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE comments (
    comment_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    mapped_product_category TEXT NOT NULL,
    review_text TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    sentiment_label INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    category_source TEXT NOT NULL,
    data_source TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE video_metrics (
    video_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    content_topic TEXT NOT NULL,
    views INTEGER NOT NULL,
    likes INTEGER NOT NULL,
    favorites INTEGER NOT NULL,
    shares INTEGER NOT NULL,
    conversion_rate REAL NOT NULL,
    data_type TEXT NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE competitors (
    competitor_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    competitor_name TEXT NOT NULL,
    competitor_platform TEXT NOT NULL DEFAULT '',
    competitor_shop_name TEXT NOT NULL DEFAULT '',
    competitor_image_url TEXT NOT NULL DEFAULT '',
    competitor_selling_point TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    competitor_price REAL NOT NULL,
    competitor_sales_quantity INTEGER NOT NULL,
    competitor_rating REAL NOT NULL,
    competitor_positive_rate REAL NOT NULL,
    main_selling_point TEXT NOT NULL,
    data_type TEXT NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE dataset_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    password_changed_at TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE TABLE api_tokens (
    token_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    token_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE brand_settings (
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

CREATE TABLE team_invitations (
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
);

CREATE TABLE audit_logs (
    audit_id TEXT PRIMARY KEY,
    workspace_id TEXT,
    user_id TEXT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    metadata_json TEXT NOT NULL,
    ip_address TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE import_jobs (
    job_id TEXT PRIMARY KEY,
    workspace_id TEXT,
    user_id TEXT,
    dataset_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE import_previews (
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

CREATE TABLE orders_daily (
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

CREATE TABLE inventory_daily (
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

CREATE TABLE after_sales (
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

CREATE TABLE ad_metrics (
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

CREATE TABLE traffic_metrics (
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

CREATE TABLE content_metrics (
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

CREATE TABLE scoring_models (
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

CREATE TABLE analysis_reports (
    report_id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    product_id TEXT,
    category TEXT,
    title TEXT NOT NULL,
    report_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE forecast_results (
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

CREATE TABLE report_schedules (
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

CREATE TABLE report_deliveries (
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

CREATE TABLE report_delivery_retry_jobs (
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
    access_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (report_id) REFERENCES analysis_reports(report_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (created_by) REFERENCES users(user_id)
);

CREATE TABLE report_share_access_logs (
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

CREATE TABLE automation_runs (
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

CREATE INDEX idx_products_category_score
    ON products(category, hot_potential_score DESC);
CREATE INDEX idx_sales_daily_product_date
    ON sales_daily(product_id, date);
CREATE INDEX idx_sales_daily_date
    ON sales_daily(date);
CREATE INDEX idx_comments_product_sentiment
    ON comments(product_id, sentiment);
CREATE INDEX idx_video_metrics_product
    ON video_metrics(product_id);
CREATE INDEX idx_competitors_product
    ON competitors(product_id);
CREATE INDEX idx_analysis_reports_scope
    ON analysis_reports(scope_type, product_id, generated_at);
CREATE INDEX idx_forecast_results_scope
    ON forecast_results(scope_type, product_id, category, generated_at);
CREATE INDEX idx_report_schedules_workspace
    ON report_schedules(workspace_id, status, next_run_at);
CREATE INDEX idx_report_schedules_due
    ON report_schedules(status, next_run_at);
CREATE INDEX idx_report_deliveries_schedule
    ON report_deliveries(schedule_id, created_at DESC);
CREATE INDEX idx_report_deliveries_workspace
    ON report_deliveries(workspace_id, created_at DESC);
CREATE INDEX idx_report_delivery_retry_jobs_due
    ON report_delivery_retry_jobs(workspace_id, status, next_attempt_at);
CREATE INDEX idx_report_delivery_retry_jobs_delivery
    ON report_delivery_retry_jobs(workspace_id, original_delivery_id);
CREATE INDEX idx_report_shares_report
    ON report_shares(report_id, created_at);
CREATE INDEX idx_report_shares_workspace
    ON report_shares(workspace_id, created_at);
CREATE INDEX idx_report_share_access_share
    ON report_share_access_logs(share_id, accessed_at DESC);
CREATE INDEX idx_report_share_access_workspace
    ON report_share_access_logs(workspace_id, accessed_at DESC);
CREATE INDEX idx_automation_runs_workspace
    ON automation_runs(workspace_id, started_at DESC);
CREATE INDEX idx_automation_runs_status
    ON automation_runs(status, started_at DESC);
CREATE INDEX idx_users_workspace
    ON users(workspace_id, role);
CREATE INDEX idx_team_invitations_workspace
    ON team_invitations(workspace_id, created_at DESC);
CREATE INDEX idx_team_invitations_email
    ON team_invitations(email, workspace_id, created_at DESC);
CREATE INDEX idx_api_tokens_hash
    ON api_tokens(token_hash);
CREATE INDEX idx_audit_logs_workspace_time
    ON audit_logs(workspace_id, created_at);
CREATE INDEX idx_import_jobs_workspace_time
    ON import_jobs(workspace_id, created_at);
CREATE INDEX idx_import_previews_time
    ON import_previews(created_at);
CREATE INDEX idx_orders_daily_product_date
    ON orders_daily(product_id, date);
CREATE INDEX idx_inventory_daily_product_date
    ON inventory_daily(product_id, date);
CREATE INDEX idx_after_sales_product
    ON after_sales(product_id, date);
CREATE INDEX idx_ad_metrics_product_date
    ON ad_metrics(product_id, date);
CREATE INDEX idx_traffic_metrics_product_date
    ON traffic_metrics(product_id, date);
CREATE INDEX idx_content_metrics_product_date
    ON content_metrics(product_id, date);
CREATE INDEX idx_scoring_models_status
    ON scoring_models(workspace_id, status, activated_at);

CREATE VIEW v_product_performance AS
SELECT
    p.product_id,
    p.product_name,
    p.platform,
    p.brand,
    p.shop_name,
    p.image_url,
    p.selling_points,
    p.source_dataset,
    p.category,
    p.avg_price,
    p.total_sales_quantity,
    p.total_gmv,
    p.rating,
    p.positive_rate,
    p.comment_count,
    p.sales_growth_rate,
    p.gmv_growth_rate,
    p.price_competitiveness,
    p.hot_potential_score,
    p.risk_level,
    COALESCE(v.views, 0) AS video_views,
    COALESCE(v.likes, 0) AS video_likes,
    COALESCE(v.favorites, 0) AS video_favorites,
    COALESCE(v.shares, 0) AS video_shares,
    COALESCE(v.conversion_rate, 0) AS video_conversion_rate
FROM products p
LEFT JOIN video_metrics v ON p.product_id = v.product_id;

CREATE VIEW v_category_summary AS
SELECT
    category,
    COUNT(*) AS product_count,
    SUM(total_sales_quantity) AS sales_quantity,
    ROUND(SUM(total_gmv), 2) AS gmv,
    ROUND(AVG(avg_price), 2) AS avg_price,
    ROUND(AVG(rating), 2) AS avg_rating,
    ROUND(AVG(positive_rate), 4) AS avg_positive_rate,
    ROUND(AVG(hot_potential_score), 2) AS avg_hot_potential_score
FROM products
GROUP BY category;
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the ViralPick AI SQLite database.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the existing generated SQLite database.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DATABASE_PATH,
        help="Target SQLite database path.",
    )
    return parser.parse_args()


def validate_inputs() -> None:
    missing = [str(path) for path in CSV_TABLES.values() if not path.exists()]
    if missing:
        missing_text = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Processed CSV files are missing. Run `python scripts/prepare_datasets.py` first.\n"
            f"{missing_text}"
        )


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def load_tables(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name, csv_path in CSV_TABLES.items():
        frame = read_csv(csv_path)
        frame.to_sql(table_name, connection, if_exists="append", index=False)
        counts[table_name] = len(frame)
    return counts


def load_metadata(connection: sqlite3.Connection, counts: dict[str, int]) -> None:
    summary_path = PROCESSED_DIR / "dataset_summary.json"
    metadata = {
        "generated_database": str(DATABASE_PATH),
        "table_counts": counts,
    }
    if summary_path.exists():
        metadata["dataset_summary"] = json.loads(summary_path.read_text(encoding="utf-8"))

    rows = [(key, json.dumps(value, ensure_ascii=False)) for key, value in metadata.items()]
    connection.executemany(
        "INSERT INTO dataset_metadata (key, value) VALUES (?, ?)",
        rows,
    )


def load_identity_seed(connection: sqlite3.Connection) -> None:
    admin_email = os.getenv("VIRALPICK_DEFAULT_ADMIN_EMAIL", "demo@viralpick.ai")
    admin_password = os.getenv("VIRALPICK_DEFAULT_ADMIN_PASSWORD", "ViralPick@2026")
    created_at = pd.Timestamp.now(tz="UTC").isoformat()
    connection.execute(
        """
        INSERT INTO workspaces (workspace_id, workspace_name, plan, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ["W-DEMO", "ViralPick Demo Workspace", "business-trial", "active", created_at],
    )
    connection.execute(
        """
        INSERT INTO users (
            user_id, workspace_id, email, password_hash, display_name, role, status,
            created_at, password_changed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "U-DEMO-ADMIN",
            "W-DEMO",
            admin_email,
            generate_password_hash(admin_password),
            "Demo Admin",
            "owner",
            "active",
            created_at,
            created_at,
        ],
    )
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "W-DEMO",
            "ViralPick AI",
            "店铺经营分析报告",
            "",
            "#00a99d",
            "#f0a51b",
            "signal-grid",
            "U-DEMO-ADMIN",
            created_at,
            created_at,
        ],
    )
    connection.execute(
        """
        INSERT INTO scoring_models (
            model_id, workspace_id, model_name, weights_json, status, note,
            created_by, created_at, activated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "SM-DEFAULT",
            "W-DEMO",
            "多平台电商增长评分模型",
            json.dumps(
                {
                    "sales_growth": 0.20,
                    "gmv_growth": 0.20,
                    "positive_rate": 0.15,
                    "comment_heat": 0.10,
                    "price_competitiveness": 0.15,
                    "video_interaction": 0.15,
                    "conversion_rate": 0.05,
                },
                ensure_ascii=False,
            ),
            "active",
            "系统默认模型，用于商品增长和经营优先级分析。",
            "U-DEMO-ADMIN",
            created_at,
            created_at,
        ],
    )


def main() -> None:
    args = parse_args()
    validate_inputs()

    db_path = args.db_path.resolve()
    if db_path.exists() and not args.force:
        raise FileExistsError(
            f"Database already exists: {db_path}\n"
            "Use `python scripts/init_database.py --force` to rebuild it."
        )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        counts = load_tables(connection)
        load_identity_seed(connection)
        load_metadata(connection, counts)
        db_migrations.mark_all_migrations_applied(connection)
        connection.commit()

    print(f"SQLite database initialized: {db_path}")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()
