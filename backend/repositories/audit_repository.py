from __future__ import annotations

from typing import Any

from backend.db import fetch_all, fetch_one


def list_audit_logs(
    workspace_id: str,
    action: str | None = None,
    resource_type: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    filters = ["a.workspace_id = ?"]
    params: list[Any] = [workspace_id]
    if action:
        filters.append("a.action = ?")
        params.append(action)
    if resource_type:
        filters.append("a.resource_type = ?")
        params.append(resource_type)
    if user_id:
        filters.append("a.user_id = ?")
        params.append(user_id)

    where_sql = f"WHERE {' AND '.join(filters)}"
    total_row = fetch_one(
        f"""
        SELECT COUNT(*) AS total
        FROM audit_logs a
        {where_sql}
        """,
        params,
    )
    offset = (page - 1) * page_size
    items = fetch_all(
        f"""
        SELECT
            a.audit_id,
            a.workspace_id,
            a.user_id,
            u.email,
            u.display_name,
            a.action,
            a.resource_type,
            a.resource_id,
            a.metadata_json,
            a.ip_address,
            a.created_at
        FROM audit_logs a
        LEFT JOIN users u ON u.user_id = a.user_id
        {where_sql}
        ORDER BY a.created_at DESC, a.audit_id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    )
    total = int((total_row or {}).get("total", 0))
    return {
        "items": items,
        "total": total,
    }


def summarize_audit_logs(workspace_id: str) -> dict[str, Any]:
    totals = fetch_one(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT user_id) AS actor_count,
            MAX(created_at) AS latest_at
        FROM audit_logs
        WHERE workspace_id = ?
        """,
        [workspace_id],
    ) or {}
    actions = fetch_all(
        """
        SELECT action, COUNT(*) AS count
        FROM audit_logs
        WHERE workspace_id = ?
        GROUP BY action
        ORDER BY count DESC, action ASC
        LIMIT 12
        """,
        [workspace_id],
    )
    resources = fetch_all(
        """
        SELECT resource_type, COUNT(*) AS count
        FROM audit_logs
        WHERE workspace_id = ?
        GROUP BY resource_type
        ORDER BY count DESC, resource_type ASC
        LIMIT 12
        """,
        [workspace_id],
    )
    return {
        "total": int(totals.get("total") or 0),
        "actor_count": int(totals.get("actor_count") or 0),
        "latest_at": totals.get("latest_at"),
        "actions": actions,
        "resources": resources,
    }


def distinct_filters(workspace_id: str) -> dict[str, list[dict[str, Any]]]:
    actions = fetch_all(
        """
        SELECT action, COUNT(*) AS count
        FROM audit_logs
        WHERE workspace_id = ?
        GROUP BY action
        ORDER BY action ASC
        """,
        [workspace_id],
    )
    resources = fetch_all(
        """
        SELECT resource_type, COUNT(*) AS count
        FROM audit_logs
        WHERE workspace_id = ?
        GROUP BY resource_type
        ORDER BY resource_type ASC
        """,
        [workspace_id],
    )
    actors = fetch_all(
        """
        SELECT
            a.user_id,
            COALESCE(u.display_name, a.user_id, 'system') AS display_name,
            COALESCE(u.email, '') AS email,
            COUNT(*) AS count
        FROM audit_logs a
        LEFT JOIN users u ON u.user_id = a.user_id
        WHERE a.workspace_id = ?
        GROUP BY a.user_id, u.display_name, u.email
        ORDER BY count DESC, display_name ASC
        """,
        [workspace_id],
    )
    return {
        "actions": actions,
        "resources": resources,
        "actors": actors,
    }
