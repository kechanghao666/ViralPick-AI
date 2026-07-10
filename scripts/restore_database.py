from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import BACKUP_DIR, DATABASE_PATH
from backend.services.backup_service import BackupError, restore_database, validate_backup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and restore a ViralPick AI SQLite backup.")
    parser.add_argument("--backup", type=Path, required=True, help="Backup .db file to restore.")
    parser.add_argument("--target", type=Path, default=DATABASE_PATH, help="Target database path.")
    parser.add_argument("--backup-dir", type=Path, default=BACKUP_DIR, help="Directory for pre-restore backup.")
    parser.add_argument("--allow-missing-checksum", action="store_true", help="Allow restore when .sha256 is missing.")
    parser.add_argument("--skip-migrate", action="store_true", help="Do not apply pending schema migrations after restore.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the restore plan without replacing files.")
    parser.add_argument("--yes", action="store_true", help="Confirm the restore. Required unless --dry-run is used.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_checksum = not args.allow_missing_checksum

    if not args.dry_run and not args.yes:
        message = "Restore is destructive. Re-run with --yes after taking or verifying a backup."
        if args.json:
            print(json.dumps({"success": False, "error": message}, ensure_ascii=False, indent=2))
        else:
            print(message, file=sys.stderr)
        return 2

    try:
        if args.dry_run:
            validation = validate_backup(args.backup, require_checksum=require_checksum)
            result = {
                "success": True,
                "dry_run": True,
                "backup": validation,
                "target": str(args.target.resolve()),
                "pre_restore_backup_dir": str(args.backup_dir.resolve()),
                "will_apply_migrations": not args.skip_migrate,
                "will_create_pre_restore_backup": args.target.exists(),
            }
        else:
            restored = restore_database(
                backup_path=args.backup,
                target_path=args.target,
                backup_dir=args.backup_dir,
                require_checksum=require_checksum,
                create_pre_restore_backup=True,
                apply_migrations=not args.skip_migrate,
            )
            result = {"success": True, "dry_run": False, **restored}
    except BackupError as exc:
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"Restore failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.dry_run:
        print(f"Backup valid: {result['backup']['filename']}")
        print(f"Target: {result['target']}")
        print(f"Will apply migrations: {result['will_apply_migrations']}")
        print(f"Will create pre-restore backup: {result['will_create_pre_restore_backup']}")
    else:
        print(f"Restored: {result['target']}")
        if result.get("pre_restore_backup"):
            print(f"Pre-restore backup: {result['pre_restore_backup']['filename']}")
        print(f"Target SHA-256: {result['target_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
