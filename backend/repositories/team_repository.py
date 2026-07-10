from __future__ import annotations

from typing import Any

from backend.db import execute_script, execute_write, fetch_all, fetch_one


TEAM_INVITATIONS_TABLE_SQL = """
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
);

CREATE INDEX IF NOT EXISTS idx_team_invitations_workspace
    ON team_invitations(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_team_invitations_email
    ON team_invitations(email, workspace_id, created_at DESC);
"""


def ensure_team_invitations_table() -> None:
    execute_script(TEAM_INVITATIONS_TABLE_SQL)


def list_workspace_members(workspace_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            user_id,
            workspace_id,
            email,
            display_name,
            role,
            status,
            created_at,
            last_login_at
        FROM users
        WHERE workspace_id = ?
        ORDER BY
            CASE role
                WHEN 'owner' THEN 1
                WHEN 'admin' THEN 2
                WHEN 'analyst' THEN 3
                WHEN 'viewer' THEN 4
                ELSE 9
            END,
            created_at ASC
        """,
        [workspace_id],
    )


def get_member(workspace_id: str, user_id: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT
            user_id,
            workspace_id,
            email,
            display_name,
            role,
            status,
            created_at,
            last_login_at
        FROM users
        WHERE workspace_id = ? AND user_id = ?
        """,
        [workspace_id, user_id],
    )


def get_member_by_email(email: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT user_id, workspace_id, email, display_name, role, status
        FROM users
        WHERE lower(email) = lower(?)
        """,
        [email],
    )


def create_member(
    user_id: str,
    workspace_id: str,
    email: str,
    password_hash: str,
    display_name: str,
    role: str,
    status: str,
    created_at: str,
) -> None:
    execute_write(
        """
        INSERT INTO users (
            user_id, workspace_id, email, password_hash, display_name,
            role, status, created_at, password_changed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            user_id,
            workspace_id,
            email,
            password_hash,
            display_name,
            role,
            status,
            created_at,
            created_at,
        ],
    )


def create_invitation(invitation: dict[str, Any]) -> None:
    ensure_team_invitations_table()
    execute_write(
        """
        INSERT INTO team_invitations (
            invitation_id, workspace_id, email, display_name, role, token_hash, token_preview,
            invited_by, created_at, expires_at, accepted_at, revoked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            invitation["invitation_id"],
            invitation["workspace_id"],
            invitation["email"],
            invitation["display_name"],
            invitation["role"],
            invitation["token_hash"],
            invitation["token_preview"],
            invitation["invited_by"],
            invitation["created_at"],
            invitation["expires_at"],
            invitation.get("accepted_at"),
            invitation.get("revoked_at"),
        ],
    )


def list_invitations(workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_team_invitations_table()
    return fetch_all(
        """
        SELECT
            invitation_id,
            workspace_id,
            email,
            display_name,
            role,
            token_preview,
            invited_by,
            created_at,
            expires_at,
            accepted_at,
            revoked_at
        FROM team_invitations
        WHERE workspace_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        [workspace_id, limit],
    )


def get_invitation(workspace_id: str, invitation_id: str) -> dict[str, Any] | None:
    ensure_team_invitations_table()
    return fetch_one(
        """
        SELECT *
        FROM team_invitations
        WHERE workspace_id = ? AND invitation_id = ?
        """,
        [workspace_id, invitation_id],
    )


def get_invitation_by_token_hash(token_hash: str) -> dict[str, Any] | None:
    ensure_team_invitations_table()
    return fetch_one(
        """
        SELECT
            i.*,
            w.workspace_name,
            w.plan,
            w.status AS workspace_status
        FROM team_invitations i
        JOIN workspaces w ON w.workspace_id = i.workspace_id
        WHERE i.token_hash = ?
        """,
        [token_hash],
    )


def revoke_invitation(workspace_id: str, invitation_id: str, revoked_at: str) -> int:
    ensure_team_invitations_table()
    return execute_write(
        """
        UPDATE team_invitations
        SET revoked_at = ?
        WHERE workspace_id = ? AND invitation_id = ? AND accepted_at IS NULL AND revoked_at IS NULL
        """,
        [revoked_at, workspace_id, invitation_id],
    )


def mark_invitation_accepted(invitation_id: str, accepted_at: str) -> int:
    ensure_team_invitations_table()
    return execute_write(
        """
        UPDATE team_invitations
        SET accepted_at = ?
        WHERE invitation_id = ? AND accepted_at IS NULL AND revoked_at IS NULL
        """,
        [accepted_at, invitation_id],
    )


def update_member(
    workspace_id: str,
    user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    status: str | None = None,
) -> int:
    fields: list[str] = []
    params: list[Any] = []
    if display_name is not None:
        fields.append("display_name = ?")
        params.append(display_name)
    if role is not None:
        fields.append("role = ?")
        params.append(role)
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if not fields:
        return 0
    params.extend([workspace_id, user_id])
    return execute_write(
        f"""
        UPDATE users
        SET {", ".join(fields)}
        WHERE workspace_id = ? AND user_id = ?
        """,
        params,
    )
