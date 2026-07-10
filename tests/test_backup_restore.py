from __future__ import annotations

import csv
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from backend.config import DATABASE_PATH
from backend.services import backup_service


ROOT_DIR = Path(__file__).resolve().parents[1]


def processed_product_count() -> int:
    with (ROOT_DIR / "data" / "processed" / "products.csv").open(encoding="utf-8-sig", newline="") as file:
        return sum(1 for _ in csv.DictReader(file))


def test_restore_database_cli_restores_valid_backup_to_target(tmp_path, initialized_database):
    backup_path = tmp_path / "viralpick-test.db"
    target_path = tmp_path / "target.db"
    pre_restore_dir = tmp_path / "pre-restore"
    shutil.copy2(DATABASE_PATH, backup_path)
    backup_path.with_suffix(".sha256").write_text(
        f"{backup_service.sha256(backup_path)}  {backup_path.name}\n",
        encoding="utf-8",
    )

    connection = sqlite3.connect(target_path)
    try:
        connection.execute("CREATE TABLE stale_marker (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO stale_marker (id) VALUES (1)")
        connection.commit()
    finally:
        connection.close()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/restore_database.py",
            "--backup",
            str(backup_path),
            "--target",
            str(target_path),
            "--backup-dir",
            str(pre_restore_dir),
            "--yes",
            "--json",
        ],
        cwd=ROOT_DIR,
        check=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert '"success": true' in result.stdout
    connection = sqlite3.connect(target_path)
    try:
        product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        migration_count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        stale_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'stale_marker'"
        ).fetchone()
    finally:
        connection.close()

    assert product_count == processed_product_count()
    assert migration_count >= 1
    assert stale_exists is None
    assert list(pre_restore_dir.glob("pre-restore-*.db"))
    assert list(pre_restore_dir.glob("pre-restore-*.sha256"))


def test_validate_backup_rejects_checksum_mismatch(tmp_path, initialized_database):
    backup_path = tmp_path / "viralpick-bad-checksum.db"
    shutil.copy2(DATABASE_PATH, backup_path)
    backup_path.with_suffix(".sha256").write_text("0" * 64 + f"  {backup_path.name}\n", encoding="utf-8")

    with pytest.raises(backup_service.BackupError, match="checksum mismatch"):
        backup_service.validate_backup(backup_path)
