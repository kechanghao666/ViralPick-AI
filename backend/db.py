from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import DATABASE_PATH


def get_connection(db_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connection_scope(db_path: Path | str = DATABASE_PATH):
    connection = get_connection(db_path)
    try:
        yield connection
    finally:
        connection.close()


def fetch_all(
    query: str,
    params: Iterable[Any] | None = None,
    db_path: Path | str = DATABASE_PATH,
) -> list[dict[str, Any]]:
    with connection_scope(db_path) as connection:
        rows = connection.execute(query, tuple(params or [])).fetchall()
    return [dict(row) for row in rows]


def fetch_one(
    query: str,
    params: Iterable[Any] | None = None,
    db_path: Path | str = DATABASE_PATH,
) -> dict[str, Any] | None:
    with connection_scope(db_path) as connection:
        row = connection.execute(query, tuple(params or [])).fetchone()
    return dict(row) if row else None


def execute_write(
    query: str,
    params: Sequence[Any] | None = None,
    db_path: Path | str = DATABASE_PATH,
) -> int:
    with connection_scope(db_path) as connection:
        cursor = connection.execute(query, tuple(params or []))
        connection.commit()
        return cursor.rowcount


def execute_script(script: str, db_path: Path | str = DATABASE_PATH) -> None:
    with connection_scope(db_path) as connection:
        connection.executescript(script)
        connection.commit()
