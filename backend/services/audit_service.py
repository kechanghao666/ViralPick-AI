from __future__ import annotations

import json
from typing import Any

from backend.permissions import has_permission
from backend.repositories import audit_repository


class AuditError(Exception):
    status_code = 400


class PermissionDenied(AuditError):
    status_code = 403


def list_logs(
    actor: dict[str, Any],
    action: str | None = None,
    resource_type: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _require_audit_access(actor)
    rows = audit_repository.list_audit_logs(
        workspace_id=actor["workspace_id"],
        action=_clean_filter(action),
        resource_type=_clean_filter(resource_type),
        user_id=_clean_filter(user_id),
        page=page,
        page_size=page_size,
    )
    summary = audit_repository.summarize_audit_logs(actor["workspace_id"])
    filters = audit_repository.distinct_filters(actor["workspace_id"])
    total = rows["total"]
    return {
        "items": [_public_log(row) for row in rows["items"]],
        "summary": summary,
        "filters": filters,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "can_view": True,
    }


def _require_audit_access(actor: dict[str, Any]) -> None:
    if not has_permission(actor, "audit.view"):
        raise PermissionDenied("Permission denied")


def _clean_filter(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _public_log(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {}
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        metadata = {"raw": row.get("metadata_json")}
    return {
        "audit_id": row.get("audit_id"),
        "workspace_id": row.get("workspace_id"),
        "user_id": row.get("user_id"),
        "actor": {
            "user_id": row.get("user_id"),
            "email": row.get("email"),
            "display_name": row.get("display_name") or row.get("email") or "system",
        },
        "action": row.get("action"),
        "action_label": _action_label(row.get("action")),
        "resource_type": row.get("resource_type"),
        "resource_label": _resource_label(row.get("resource_type")),
        "resource_id": row.get("resource_id"),
        "metadata": metadata,
        "ip_address": row.get("ip_address"),
        "created_at": row.get("created_at"),
    }


def _action_label(action: str | None) -> str:
    labels = {
        "auth.register": "注册账号",
        "auth.login": "登录",
        "auth.login_failed": "登录失败",
        "auth.login_locked": "登录受限",
        "auth.logout": "退出登录",
        "brand.settings.update": "更新品牌设置",
        "data_import.create": "创建导入任务",
        "data_import.errors.download": "下载导入错误报告",
        "ops.alert.dispatch": "发送运行告警",
        "ops.backup.create": "创建数据库备份",
        "ops.automation.run_once": "执行后台自动化",
        "report.generate": "生成报告",
        "report.export": "导出报告",
        "report.schedule.create": "创建定时报告",
        "report.schedule.update": "更新定时报告",
        "report.schedule.run": "执行定时报告",
        "report.schedule.run_due": "执行到期报告",
        "report.schedule.archive": "归档定时报告",
        "report.delivery.retry": "重试报告交付",
        "report.delivery.retry_due": "执行报告交付重试队列",
        "report.share.create": "创建报告分享",
        "report.share.revoke": "撤销报告分享",
        "scoring.model.create": "创建评分模型",
        "team.invitation.create": "发送成员邀请",
        "team.invitation.accept": "接受成员邀请",
        "team.invitation.revoke": "撤销成员邀请",
        "team.member.create": "创建团队成员",
        "team.member.update": "更新团队成员",
    }
    return labels.get(str(action or ""), str(action or "未知操作"))


def _resource_label(resource_type: str | None) -> str:
    labels = {
        "automation_run": "后台任务",
        "backup": "数据库备份",
        "brand_settings": "品牌设置",
        "data_import": "数据导入",
        "database_backup": "数据库备份",
        "import_job": "数据导入",
        "monitoring_alert": "运行告警",
        "ops_automation": "后台任务",
        "ops_alert": "运行告警",
        "report": "经营报告",
        "report_delivery": "报告交付",
        "report_delivery_retry_job": "报告交付重试",
        "report_schedule": "定时报告",
        "report_share": "报告分享",
        "scoring_model": "评分模型",
        "session": "登录会话",
        "team_invitation": "团队邀请",
        "team_member": "团队成员",
        "user": "用户账号",
        "workspace": "工作空间",
    }
    return labels.get(str(resource_type or ""), str(resource_type or "系统"))
