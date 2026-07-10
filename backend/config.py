from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
APP_NAME = "ViralPick AI"
APP_VERSION = os.getenv("VIRALPICK_VERSION", "0.2.0")
APP_ENV = os.getenv("VIRALPICK_ENV", "development")
LOG_LEVEL = os.getenv("VIRALPICK_LOG_LEVEL", "INFO").upper()
API_HOST = os.getenv("VIRALPICK_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("VIRALPICK_API_PORT", "5000"))
DEBUG = os.getenv("VIRALPICK_DEBUG", "0") == "1"
SERVE_FRONTEND = os.getenv(
    "VIRALPICK_SERVE_FRONTEND",
    "0" if APP_ENV == "production" else "1",
) == "1"
AUTH_REQUIRED = os.getenv(
    "VIRALPICK_AUTH_REQUIRED",
    "1" if APP_ENV == "production" else "0",
) == "1"
AUTH_TOKEN_TTL_HOURS = int(os.getenv("VIRALPICK_AUTH_TOKEN_TTL_HOURS", "168"))
AUTH_MAX_FAILED_ATTEMPTS = int(os.getenv("VIRALPICK_AUTH_MAX_FAILED_ATTEMPTS", "5"))
AUTH_LOCKOUT_MINUTES = int(os.getenv("VIRALPICK_AUTH_LOCKOUT_MINUTES", "15"))
DEFAULT_ADMIN_EMAIL = os.getenv("VIRALPICK_DEFAULT_ADMIN_EMAIL", "demo@viralpick.ai")
DEFAULT_ADMIN_PASSWORD = os.getenv("VIRALPICK_DEFAULT_ADMIN_PASSWORD", "ViralPick@2026")
MAX_UPLOAD_MB = int(os.getenv("VIRALPICK_MAX_UPLOAD_MB", "10"))
RATE_LIMIT_ENABLED = os.getenv(
    "VIRALPICK_RATE_LIMIT_ENABLED",
    "1" if APP_ENV == "production" else "0",
) == "1"
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("VIRALPICK_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_DEFAULT_PER_WINDOW = int(os.getenv("VIRALPICK_RATE_LIMIT_DEFAULT_PER_WINDOW", "300"))
RATE_LIMIT_AUTH_PER_WINDOW = int(os.getenv("VIRALPICK_RATE_LIMIT_AUTH_PER_WINDOW", "20"))
RATE_LIMIT_WRITE_PER_WINDOW = int(os.getenv("VIRALPICK_RATE_LIMIT_WRITE_PER_WINDOW", "120"))
BACKUP_DIR = Path(os.getenv("VIRALPICK_BACKUP_DIR", BASE_DIR / "data" / "backups"))
BACKUP_RETENTION = int(os.getenv("VIRALPICK_BACKUP_RETENTION", "10"))
ALERTS_ENABLED = os.getenv("VIRALPICK_ALERTS_ENABLED", "0") == "1"
ALERT_WEBHOOK_URL = os.getenv("VIRALPICK_ALERT_WEBHOOK_URL", "")
ALERT_MIN_SEVERITY = os.getenv("VIRALPICK_ALERT_MIN_SEVERITY", "warn").lower()
ALERT_TIMEOUT_SECONDS = int(os.getenv("VIRALPICK_ALERT_TIMEOUT_SECONDS", "8"))
PUBLIC_BASE_URL = os.getenv("VIRALPICK_PUBLIC_BASE_URL", "")
REPORT_DELIVERY_ENABLED = os.getenv("VIRALPICK_REPORT_DELIVERY_ENABLED", "0") == "1"
REPORT_DELIVERY_AUTO_RETRY_ENABLED = os.getenv("VIRALPICK_REPORT_DELIVERY_AUTO_RETRY_ENABLED", "1") == "1"
REPORT_DELIVERY_MAX_RETRY_ATTEMPTS = int(os.getenv("VIRALPICK_REPORT_DELIVERY_MAX_RETRY_ATTEMPTS", "3"))
REPORT_DELIVERY_RETRY_BACKOFF_MINUTES = os.getenv("VIRALPICK_REPORT_DELIVERY_RETRY_BACKOFF_MINUTES", "5,30,120")
SMTP_HOST = os.getenv("VIRALPICK_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("VIRALPICK_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("VIRALPICK_SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("VIRALPICK_SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("VIRALPICK_SMTP_FROM_EMAIL", SMTP_USERNAME or "reports@viralpick.local")
SMTP_USE_TLS = os.getenv("VIRALPICK_SMTP_USE_TLS", "1") == "1"
SMTP_USE_SSL = os.getenv("VIRALPICK_SMTP_USE_SSL", "0") == "1"
SMTP_TIMEOUT_SECONDS = int(os.getenv("VIRALPICK_SMTP_TIMEOUT_SECONDS", "10"))

PROCESSED_DATA_DIR = Path(
    os.getenv("VIRALPICK_PROCESSED_DATA_DIR", BASE_DIR / "data" / "processed")
)
DATABASE_PATH = Path(
    os.getenv("VIRALPICK_DB_PATH", BASE_DIR / "data" / "database" / "viralpick.db")
)
FRONTEND_DIR = Path(os.getenv("VIRALPICK_FRONTEND_DIR", BASE_DIR / "frontend"))


def cors_origins() -> list[str]:
    value = os.getenv("VIRALPICK_CORS_ORIGINS", "*")
    return [origin.strip() for origin in value.split(",") if origin.strip()]
