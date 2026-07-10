from __future__ import annotations

from typing import Any

from backend.db import connection_scope, execute_write, fetch_one


def get_user_by_email(email: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT
            u.user_id,
            u.workspace_id,
            w.workspace_name,
            w.plan,
            u.email,
            u.password_hash,
            u.display_name,
            u.role,
            u.status,
            u.failed_login_count,
            u.locked_until
        FROM users u
        JOIN workspaces w ON w.workspace_id = u.workspace_id
        WHERE lower(u.email) = lower(?)
        """,
        [email],
    )


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT
            u.user_id,
            u.workspace_id,
            w.workspace_name,
            w.plan,
            u.email,
            u.display_name,
            u.role,
            u.status
        FROM users u
        JOIN workspaces w ON w.workspace_id = u.workspace_id
        WHERE u.user_id = ?
        """,
        [user_id],
    )


def create_workspace_with_owner(
    workspace_id: str,
    workspace_name: str,
    user_id: str,
    email: str,
    password_hash: str,
    display_name: str,
    plan: str,
    created_at: str,
) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO workspaces (workspace_id, workspace_name, plan, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [workspace_id, workspace_name, plan, "active", created_at],
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
                user_id,
                workspace_id,
                email,
                password_hash,
                display_name,
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
                workspace_id,
                workspace_name,
                "店铺经营分析报告",
                "",
                "#00a99d",
                "#f0a51b",
                "signal-grid",
                user_id,
                created_at,
                created_at,
            ],
        )
        connection.commit()


def create_token(
    token_id: str,
    user_id: str,
    token_hash: str,
    token_name: str,
    created_at: str,
    expires_at: str,
) -> None:
    execute_write(
        """
        INSERT INTO api_tokens (
            token_id, user_id, token_hash, token_name, created_at, expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [token_id, user_id, token_hash, token_name, created_at, expires_at],
    )


def get_token_user(token_hash: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT
            t.token_id,
            t.expires_at,
            t.revoked_at,
            u.user_id,
            u.workspace_id,
            w.workspace_name,
            w.plan,
            u.email,
            u.display_name,
            u.role,
            u.status
        FROM api_tokens t
        JOIN users u ON u.user_id = t.user_id
        JOIN workspaces w ON w.workspace_id = u.workspace_id
        WHERE t.token_hash = ?
        """,
        [token_hash],
    )


def touch_login(user_id: str, timestamp: str) -> None:
    execute_write(
        "UPDATE users SET last_login_at = ? WHERE user_id = ?",
        [timestamp, user_id],
    )


def record_failed_login(user_id: str, failed_login_count: int, locked_until: str | None) -> None:
    execute_write(
        """
        UPDATE users
        SET failed_login_count = ?, locked_until = ?
        WHERE user_id = ?
        """,
        [failed_login_count, locked_until, user_id],
    )


def reset_failed_logins(user_id: str) -> None:
    execute_write(
        """
        UPDATE users
        SET failed_login_count = 0, locked_until = NULL
        WHERE user_id = ?
        """,
        [user_id],
    )


def touch_token(token_id: str, timestamp: str) -> None:
    execute_write(
        "UPDATE api_tokens SET last_used_at = ? WHERE token_id = ?",
        [timestamp, token_id],
    )


def revoke_token(token_hash: str, timestamp: str) -> int:
    return execute_write(
        """
        UPDATE api_tokens
        SET revoked_at = ?
        WHERE token_hash = ? AND revoked_at IS NULL
        """,
        [timestamp, token_hash],
    )


def insert_audit_log(
    audit_id: str,
    workspace_id: str | None,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata_json: str,
    ip_address: str | None,
    created_at: str,
) -> None:
    execute_write(
        """
        INSERT INTO audit_logs (
            audit_id, workspace_id, user_id, action, resource_type,
            resource_id, metadata_json, ip_address, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            audit_id,
            workspace_id,
            user_id,
            action,
            resource_type,
            resource_id,
            metadata_json,
            ip_address,
            created_at,
        ],
    )
