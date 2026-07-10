from __future__ import annotations

from typing import Any


ROLE_ORDER = ["owner", "admin", "analyst", "viewer"]

ROLE_LABELS = {
    "owner": "所有者",
    "admin": "管理员",
    "analyst": "分析师",
    "viewer": "只读成员",
}

PERMISSION_LABELS = {
    "analytics.read": "查看分析看板",
    "products.read": "查看商品数据",
    "reports.view": "查看报告",
    "reports.export": "导出报告",
    "reports.generate": "生成报告",
    "reports.share": "管理报告分享",
    "reports.schedule": "管理定时报告",
    "imports.manage": "导入和校验数据",
    "scoring.view": "查看评分模型",
    "scoring.manage": "管理评分模型",
    "brand.view": "查看品牌设置",
    "brand.manage": "管理品牌设置",
    "team.view": "查看团队成员",
    "team.manage": "管理团队成员",
    "audit.view": "查看审计日志",
    "ops.view": "查看运维状态",
    "ops.manage": "管理备份与运维操作",
    "alerts.manage": "发送监控告警",
}

ROLE_PERMISSIONS = {
    "owner": set(PERMISSION_LABELS),
    "admin": {
        "analytics.read",
        "products.read",
        "reports.view",
        "reports.export",
        "reports.generate",
        "reports.share",
        "reports.schedule",
        "imports.manage",
        "scoring.view",
        "scoring.manage",
        "brand.view",
        "brand.manage",
        "team.view",
        "team.manage",
        "audit.view",
        "ops.view",
        "ops.manage",
        "alerts.manage",
    },
    "analyst": {
        "analytics.read",
        "products.read",
        "reports.view",
        "reports.export",
        "reports.generate",
        "reports.share",
        "reports.schedule",
        "imports.manage",
        "scoring.view",
        "brand.view",
        "team.view",
    },
    "viewer": {
        "analytics.read",
        "products.read",
        "reports.view",
        "reports.export",
        "scoring.view",
        "brand.view",
        "team.view",
    },
}


def permissions_for_role(role: str | None) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(str(role or "").strip().lower(), set()))


def has_permission(user: dict[str, Any] | None, permission: str) -> bool:
    if not user:
        return False
    return permission in ROLE_PERMISSIONS.get(str(user.get("role") or "").strip().lower(), set())


def role_capabilities(role: str | None) -> list[str]:
    return [PERMISSION_LABELS[key] for key in permissions_for_role(role)]


def role_matrix() -> list[dict[str, Any]]:
    return [
        {
            "role": role,
            "label": ROLE_LABELS[role],
            "permissions": permissions_for_role(role),
            "capabilities": role_capabilities(role),
        }
        for role in ROLE_ORDER
    ]


def permission_summary(user: dict[str, Any] | None) -> dict[str, Any]:
    role = str((user or {}).get("role") or "").strip().lower()
    permissions = permissions_for_role(role)
    return {
        "role": role or None,
        "role_label": ROLE_LABELS.get(role),
        "permissions": permissions,
        "capabilities": [PERMISSION_LABELS[key] for key in permissions],
        "matrix": role_matrix(),
    }
