from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import APP_ENV, APP_NAME, APP_VERSION, BACKUP_DIR, BACKUP_RETENTION, DATABASE_PATH
from backend.db import fetch_all, fetch_one
from backend.permissions import has_permission
from backend.services import backup_service


TRACKED_TABLES = [
    "products",
    "sales_daily",
    "comments",
    "video_metrics",
    "competitors",
    "brand_settings",
    "scoring_models",
    "analysis_reports",
    "report_schedules",
    "report_deliveries",
    "report_delivery_retry_jobs",
    "automation_runs",
    "report_shares",
    "report_share_access_logs",
    "forecast_results",
    "import_jobs",
    "audit_logs",
    "users",
    "team_invitations",
]


class OpsError(Exception):
    status_code = 400


class PermissionDenied(OpsError):
    status_code = 403


def get_status(actor: dict[str, Any]) -> dict[str, Any]:
    _require_ops_access(actor)
    database_exists = DATABASE_PATH.exists()
    database_size = DATABASE_PATH.stat().st_size if database_exists else 0
    return {
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "environment": APP_ENV,
        },
        "database": {
            "path": str(DATABASE_PATH),
            "exists": database_exists,
            "size_bytes": database_size,
            "size_label": _format_bytes(database_size),
            "table_counts": _table_counts() if database_exists else [],
        },
        "backups": {
            "directory": str(BACKUP_DIR),
            "retention": BACKUP_RETENTION,
            "items": list_backups(actor)["items"],
        },
    }


def get_monitoring(actor: dict[str, Any]) -> dict[str, Any]:
    _require_ops_access(actor)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    database_exists = DATABASE_PATH.exists()
    database_size = DATABASE_PATH.stat().st_size if database_exists else 0
    table_counts = _table_counts() if database_exists else []
    count_map = {item["table"]: item["count"] for item in table_counts}
    backups = list_backups(actor)["items"] if database_exists else []
    latest_backup = backups[0] if backups else None
    import_summary = _import_summary(actor.get("workspace_id"))
    latest_audit_at = _latest_audit_at(actor.get("workspace_id"))

    metrics = [
        _metric("database_size", "数据库体积", database_size, _format_bytes(database_size)),
        _metric("product_count", "商品数", count_map.get("products") or 0, f"{count_map.get('products') or 0} 个"),
        _metric("sales_daily_count", "销售记录", count_map.get("sales_daily") or 0, f"{count_map.get('sales_daily') or 0} 条"),
        _metric("backup_count", "备份数量", len(backups), f"{len(backups)} 份"),
        _metric("failed_imports", "失败导入", import_summary["failed"], f"{import_summary['failed']} 个"),
        _metric("latest_audit_at", "最近审计", latest_audit_at or "", latest_audit_at or "暂无"),
    ]
    alerts: list[dict[str, Any]] = []
    if not database_exists:
        alerts.append(_alert("database_missing", "critical", "数据库文件缺失", "请先运行初始化脚本或挂载正确的数据卷。"))
    if database_exists and (count_map.get("products") or 0) <= 0:
        alerts.append(_alert("products_empty", "critical", "商品主表为空", "商品分析、评分和报告无法形成有效闭环。"))
    if database_exists and (count_map.get("sales_daily") or 0) <= 0:
        alerts.append(_alert("sales_empty", "critical", "销售事实表为空", "趋势分析和预测能力不可用。"))
    if database_exists and not backups:
        alerts.append(_alert("backup_missing", "warn", "尚未创建数据库备份", "建议在导入数据、演示或部署前创建至少一份备份。"))
    if latest_backup and _hours_since(latest_backup.get("created_at")) > 72:
        alerts.append(_alert("backup_stale", "warn", "最近备份超过 72 小时", "建议创建新的 SQLite 快照并保留校验值。"))
    if import_summary["failed"] > 0:
        alerts.append(_alert("import_failures", "warn", "存在失败导入任务", "请在数据链路页下载错误报告并修正 CSV。", {"failed": import_summary["failed"]}))
    if (count_map.get("scoring_models") or 0) <= 0:
        alerts.append(_alert("scoring_model_missing", "warn", "缺少评分模型版本记录", "建议初始化或创建激活评分模型，保证爆品评分可追溯。"))
    if not alerts:
        alerts.append(_alert("all_clear", "info", "核心运行状态正常", "数据库、业务表、模型和导入任务未发现阻塞告警。"))

    severity_order = {"critical": 3, "warn": 2, "info": 1}
    worst = max(alerts, key=lambda item: severity_order.get(item["severity"], 0))["severity"]
    health_state = "critical" if worst == "critical" else "warn" if worst == "warn" else "healthy"
    return {
        "generated_at": generated_at,
        "health_state": health_state,
        "summary": {
            "critical": sum(1 for item in alerts if item["severity"] == "critical"),
            "warn": sum(1 for item in alerts if item["severity"] == "warn"),
            "info": sum(1 for item in alerts if item["severity"] == "info"),
            "latest_backup_at": latest_backup.get("created_at") if latest_backup else None,
        },
        "metrics": metrics,
        "alerts": alerts,
    }


def list_backups(actor: dict[str, Any]) -> dict[str, Any]:
    _require_ops_access(actor)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    items = [
        backup_service.backup_metadata(path)
        for path in sorted(BACKUP_DIR.glob("viralpick-*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    ]
    return {
        "items": items,
        "retention": BACKUP_RETENTION,
        "directory": str(BACKUP_DIR),
    }


def create_backup(actor: dict[str, Any]) -> dict[str, Any]:
    _require_ops_manage(actor)
    if not DATABASE_PATH.exists():
        raise OpsError("Database does not exist")
    metadata = backup_service.create_database_backup(DATABASE_PATH, BACKUP_DIR)
    _enforce_retention()
    return metadata


def verify_backup(actor: dict[str, Any], filename: str) -> dict[str, Any]:
    _require_ops_manage(actor)
    try:
        path = backup_service.resolve_backup_file(filename, BACKUP_DIR)
        return backup_service.validate_backup(path)
    except backup_service.BackupError as exc:
        raise OpsError(str(exc)) from exc


def _require_ops_access(actor: dict[str, Any]) -> None:
    if not has_permission(actor, "ops.view"):
        raise PermissionDenied("Permission denied")


def _require_ops_manage(actor: dict[str, Any]) -> None:
    if not has_permission(actor, "ops.manage"):
        raise PermissionDenied("Permission denied")


def require_ops_access(actor: dict[str, Any]) -> None:
    _require_ops_access(actor)


def _table_counts() -> list[dict[str, Any]]:
    counts: list[dict[str, Any]] = []
    for table in TRACKED_TABLES:
        try:
            row = fetch_one(f"SELECT COUNT(*) AS count FROM {table}") or {"count": 0}
            counts.append({"table": table, "count": int(row.get("count") or 0)})
        except sqlite3.Error:
            counts.append({"table": table, "count": None})
    return counts


def _enforce_retention() -> None:
    backups = sorted(BACKUP_DIR.glob("viralpick-*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in backups[max(0, BACKUP_RETENTION) :]:
        checksum = stale.with_suffix(".sha256")
        stale.unlink(missing_ok=True)
        checksum.unlink(missing_ok=True)

def _import_summary(workspace_id: str | None) -> dict[str, int]:
    if workspace_id:
        rows = fetch_all(
            """
            SELECT status, COUNT(*) AS count
            FROM import_jobs
            WHERE workspace_id = ?
            GROUP BY status
            """,
            [workspace_id],
        )
    else:
        rows = fetch_all(
            """
            SELECT status, COUNT(*) AS count
            FROM import_jobs
            GROUP BY status
            """
        )
    counts = {row["status"]: int(row["count"] or 0) for row in rows}
    return {
        "failed": counts.get("failed", 0),
        "completed": counts.get("completed", 0),
        "validated": counts.get("validated", 0),
        "running": counts.get("running", 0),
    }


def _latest_audit_at(workspace_id: str | None) -> str | None:
    if workspace_id:
        row = fetch_one("SELECT MAX(created_at) AS latest_at FROM audit_logs WHERE workspace_id = ?", [workspace_id])
    else:
        row = fetch_one("SELECT MAX(created_at) AS latest_at FROM audit_logs")
    return (row or {}).get("latest_at")


def _metric(key: str, label: str, value: Any, display_value: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "display_value": display_value,
    }


def _alert(code: str, severity: str, title: str, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "message": message,
        "metadata": metadata or {},
    }


def _hours_since(value: str | None) -> float:
    if not value:
        return 0
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return (datetime.now(UTC) - timestamp).total_seconds() / 3600


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ["B", "KB", "MB", "GB"]:
        if amount < 1024 or unit == "GB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} GB"
