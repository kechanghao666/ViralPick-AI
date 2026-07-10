from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import DATABASE_PATH
from backend.migrations import get_migration_status
from backend.services import automation_service


STOP_REQUESTED = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ViralPick AI background automation worker.")
    parser.add_argument("--once", action="store_true", help="Run one automation cycle and exit.")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Loop interval when --once is not set.")
    parser.add_argument("--max-iterations", type=int, default=0, help="Optional loop cap for tests or supervised jobs.")
    parser.add_argument("--workspace-id", default="", help="Limit automation to one workspace.")
    parser.add_argument("--schedule-limit", type=int, default=20, help="Maximum due report schedules per workspace per cycle.")
    parser.add_argument("--retry-limit", type=int, default=20, help="Maximum due delivery retry jobs per workspace per cycle.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON lines.")
    args = parser.parse_args()

    _verify_ready()
    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    iteration = 0
    while not STOP_REQUESTED:
        iteration += 1
        result = automation_service.run_once(
            workspace_id=args.workspace_id or None,
            schedule_limit=args.schedule_limit,
            retry_limit=args.retry_limit,
            trigger="worker",
        )
        _emit(result, as_json=args.json)
        if args.once or (args.max_iterations and iteration >= args.max_iterations):
            break
        time.sleep(max(5, int(args.interval_seconds or 300)))
    return 0


def _verify_ready() -> None:
    status = get_migration_status(DATABASE_PATH)
    if not status.get("exists"):
        raise SystemExit(f"Database does not exist: {DATABASE_PATH}")
    if status.get("pending"):
        pending = ", ".join(item["version"] for item in status["pending"])
        raise SystemExit(f"Database has pending migrations: {pending}")


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=True))
        return
    totals = result.get("totals", {})
    print(
        "automation status={status} workspaces={workspaces} "
        "schedules={schedules_executed}/{schedules_due} retries={retries_processed}/{retries_due}".format(
            status=result.get("status"),
            workspaces=result.get("workspace_count"),
            schedules_executed=totals.get("schedules_executed", 0),
            schedules_due=totals.get("schedules_due", 0),
            retries_processed=totals.get("retries_processed", 0),
            retries_due=totals.get("retries_due", 0),
        )
    )


def _request_stop(_signum, _frame) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


if __name__ == "__main__":
    raise SystemExit(main())
