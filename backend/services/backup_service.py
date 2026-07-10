from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend import migrations as db_migrations
from backend.config import BACKUP_DIR, DATABASE_PATH


CORE_TABLES = [
    "products",
    "sales_daily",
    "comments",
    "users",
    "schema_migrations",
]


class BackupError(Exception):
    pass


def backup_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    checksum_path = path.with_suffix(".sha256")
    checksum = ""
    if checksum_path.exists():
        checksum = checksum_path.read_text(encoding="utf-8").split()[0]
    return {
        "filename": path.name,
        "path": str(path),
        "size_bytes": stat.st_size,
        "size_label": _format_bytes(stat.st_size),
        "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sha256": checksum,
    }


def validate_backup(
    backup_path: Path | str,
    require_checksum: bool = True,
) -> dict[str, Any]:
    source = Path(backup_path)
    if not source.exists() or not source.is_file():
        raise BackupError(f"Backup file does not exist: {source}")
    if source.suffix.lower() != ".db":
        raise BackupError("Backup file must be a .db SQLite file")

    checksum = sha256(source)
    checksum_path = source.with_suffix(".sha256")
    expected_checksum = _read_checksum(checksum_path)
    if require_checksum and not expected_checksum:
        raise BackupError(f"Backup checksum file is missing: {checksum_path}")
    if expected_checksum and expected_checksum != checksum:
        raise BackupError("Backup checksum mismatch")

    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise BackupError(f"Backup integrity check failed: {integrity}")
        table_counts = _table_counts(connection)
    finally:
        connection.close()

    migration_status = db_migrations.get_migration_status(source)
    return {
        "valid": True,
        "filename": source.name,
        "path": str(source),
        "size_bytes": source.stat().st_size,
        "size_label": _format_bytes(source.stat().st_size),
        "sha256": checksum,
        "checksum_file": str(checksum_path) if checksum_path.exists() else None,
        "checksum_valid": bool(expected_checksum and expected_checksum == checksum),
        "integrity_check": integrity,
        "table_counts": table_counts,
        "migration_status": {
            "current_version": migration_status["current_version"],
            "pending": migration_status["pending"],
        },
    }


def restore_database(
    backup_path: Path | str,
    target_path: Path | str = DATABASE_PATH,
    backup_dir: Path | str = BACKUP_DIR,
    require_checksum: bool = True,
    create_pre_restore_backup: bool = True,
    apply_migrations: bool = True,
) -> dict[str, Any]:
    source = Path(backup_path).resolve()
    target = Path(target_path).resolve()
    backup_directory = Path(backup_dir).resolve()

    validation = validate_backup(source, require_checksum=require_checksum)
    target.parent.mkdir(parents=True, exist_ok=True)
    pre_restore_backup = None
    if create_pre_restore_backup and target.exists():
        pre_restore_backup = create_database_backup(
            source_db=target,
            backup_dir=backup_directory,
            prefix="pre-restore",
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    temp_target = target.with_name(f".{target.name}.restore-{timestamp}.tmp.db")
    shutil.copy2(source, temp_target)
    try:
        if apply_migrations:
            migration_result = db_migrations.apply_pending_migrations(temp_target)
        else:
            migration_status = db_migrations.get_migration_status(temp_target)
            migration_result = {
                "applied": [],
                "pending": migration_status["pending"],
                "current_version": migration_status["current_version"],
            }
        final_validation = validate_backup(temp_target, require_checksum=False)
        if apply_migrations and final_validation["migration_status"]["pending"]:
            pending = ", ".join(item["version"] for item in final_validation["migration_status"]["pending"])
            raise BackupError(f"Restored database still has pending migrations: {pending}")
        _replace_with_retry(temp_target, target)
    except Exception:
        _unlink_with_retry(temp_target)
        raise

    return {
        "restored": True,
        "source": validation,
        "target": str(target),
        "target_sha256": sha256(target),
        "pre_restore_backup": pre_restore_backup,
        "migration": {
            "applied": migration_result.get("applied", []),
            "pending": migration_result.get("pending", []),
            "current_version": migration_result.get("current_version"),
        },
        "restored_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def create_database_backup(
    source_db: Path | str = DATABASE_PATH,
    backup_dir: Path | str = BACKUP_DIR,
    prefix: str = "viralpick",
) -> dict[str, Any]:
    source = Path(source_db)
    if not source.exists():
        raise BackupError(f"Database does not exist: {source}")
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"{prefix}-{timestamp}.db"
    counter = 1
    while target.exists():
        counter += 1
        target = target_dir / f"{prefix}-{timestamp}-{counter}.db"
    source_connection = sqlite3.connect(source)
    destination = sqlite3.connect(target)
    try:
        source_connection.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source_connection.close()
    checksum = sha256(target)
    target.with_suffix(".sha256").write_text(f"{checksum}  {target.name}\n", encoding="utf-8")
    return backup_metadata(target)


def resolve_backup_file(filename: str, backup_dir: Path | str = BACKUP_DIR) -> Path:
    if not filename or "/" in filename or "\\" in filename:
        raise BackupError("Invalid backup filename")
    backup_root = Path(backup_dir).resolve()
    candidate = (backup_root / filename).resolve()
    if candidate.parent != backup_root:
        raise BackupError("Backup filename escapes backup directory")
    return candidate


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_counts(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    counts: list[dict[str, Any]] = []
    for table in CORE_TABLES:
        try:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            counts.append({"table": table, "count": int(row["count"] or 0)})
        except sqlite3.Error:
            counts.append({"table": table, "count": None})
    return counts


def _read_checksum(path: Path) -> str | None:
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    return content.split()[0].lstrip("\ufeff")


def _replace_with_retry(source: Path, target: Path) -> None:
    last_error: PermissionError | None = None
    for _attempt in range(10):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.2)
    if last_error:
        raise last_error


def _unlink_with_retry(path: Path) -> None:
    for _attempt in range(10):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.2)


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ["B", "KB", "MB", "GB"]:
        if amount < 1024 or unit == "GB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} GB"
