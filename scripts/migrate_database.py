from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import DATABASE_PATH
from backend.migrations import MigrationError, apply_pending_migrations, get_migration_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply ViralPick AI SQLite database migrations.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DATABASE_PATH,
        help="Target SQLite database path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pending migrations without applying them.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = (
            apply_pending_migrations(args.db_path, dry_run=True)
            if args.dry_run
            else apply_pending_migrations(args.db_path)
        )
    except MigrationError as exc:
        status = get_migration_status(args.db_path)
        if args.json:
            print(json.dumps({"success": False, "error": str(exc), "status": status}, ensure_ascii=False, indent=2))
        else:
            print(f"Migration failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"success": True, **result}, ensure_ascii=False, indent=2))
        return 0

    pending_count = len(result.get("pending", []))
    applied = result.get("applied", [])
    print(f"Database: {result['database']}")
    if args.dry_run:
        print(f"Pending migrations: {pending_count}")
    elif applied:
        print(f"Applied migrations: {len(applied)}")
        for migration in applied:
            print(f"- {migration['version']} {migration['name']}")
    else:
        print("Database schema is up to date.")
    if pending_count:
        for migration in result["pending"]:
            print(f"pending: {migration['version']} {migration['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
