from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.permissions import has_permission
from backend.repositories import report_schedule_repository
from backend.services import product_service, report_delivery_service, report_service


FREQUENCIES = {"daily", "weekly", "monthly"}
FREQUENCY_LABELS = {
    "daily": "每日",
    "weekly": "每周",
    "monthly": "每月",
}
STATUSES = {"active", "paused"}
ARCHIVED_STATUS = "archived"
EXPORT_FORMATS = {"docx", "pdf", "html", "markdown"}
TIMEZONES = {
    "Asia/Shanghai": timezone(timedelta(hours=8), name="Asia/Shanghai"),
    "UTC": UTC,
}
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_RUN_TIME = "09:00"


class ReportScheduleError(Exception):
    status_code = 400


class PermissionDenied(ReportScheduleError):
    status_code = 403


class NotFound(ReportScheduleError):
    status_code = 404


def list_schedules(actor: dict[str, Any], limit: int = 50) -> dict[str, Any]:
    _require_schedule_access(actor)
    safe_limit = max(1, min(100, int(limit or 50)))
    rows = report_schedule_repository.list_schedules(actor["workspace_id"], limit=safe_limit)
    return {
        "workspace_id": actor["workspace_id"],
        "can_manage": True,
        "items": [_public_schedule(row) for row in rows],
    }


def create_schedule(actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    _require_schedule_access(actor)
    parsed = _parse_schedule_payload(payload)
    product_id = parsed.get("product_id")
    if product_id and not product_service.get_product(product_id):
        raise NotFound(f"Product not found: {product_id}")

    now = _now()
    schedule = {
        "schedule_id": f"RS-{uuid4().hex[:14]}",
        "workspace_id": actor["workspace_id"],
        "created_by": actor["user_id"],
        "schedule_name": parsed["schedule_name"],
        "scope_type": "product" if product_id else "global",
        "product_id": product_id,
        "frequency": parsed["frequency"],
        "run_time": parsed["run_time"],
        "weekday": parsed.get("weekday"),
        "monthday": parsed.get("monthday"),
        "timezone": parsed["timezone"],
        "use_llm": parsed["use_llm"],
        "export_format": parsed["export_format"],
        "delivery_channel": parsed["delivery_channel"],
        "recipients_json": report_delivery_service.recipients_json(parsed["recipients"]),
        "status": "active",
        "next_run_at": _compute_next_run_at(
            frequency=parsed["frequency"],
            run_time=parsed["run_time"],
            tz_name=parsed["timezone"],
            weekday=parsed.get("weekday"),
            monthday=parsed.get("monthday"),
            now_utc=now,
        ),
        "last_run_at": None,
        "last_report_id": None,
        "last_error": None,
        "run_count": 0,
        "created_at": _to_iso(now),
        "updated_at": _to_iso(now),
    }
    report_schedule_repository.create_schedule(schedule)
    created = report_schedule_repository.get_schedule(actor["workspace_id"], schedule["schedule_id"]) or schedule
    return _public_schedule(created)


def update_schedule(actor: dict[str, Any], schedule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _require_schedule_access(actor)
    existing = _get_schedule_or_raise(actor, schedule_id)
    if existing.get("status") == ARCHIVED_STATUS:
        raise ReportScheduleError("Schedule has been archived")

    fields: dict[str, Any] = {}
    schedule_keys = {"frequency", "run_time", "weekday", "monthday", "timezone"}
    delivery_keys = {"delivery_channel", "recipients", "recipient_emails"}

    if "schedule_name" in payload:
        fields["schedule_name"] = _validate_name(payload.get("schedule_name"))
    if "status" in payload:
        fields["status"] = _validate_status(payload.get("status"))
    if "use_llm" in payload:
        fields["use_llm"] = 1 if _parse_bool(payload.get("use_llm")) else 0
    if "export_format" in payload:
        fields["export_format"] = _validate_export_format(payload.get("export_format"))
    if delivery_keys.intersection(payload):
        recipients = report_delivery_service.parse_recipients(
            payload.get("recipients") if "recipients" in payload else payload.get("recipient_emails")
        )
        delivery_channel = _validate_delivery_channel(
            payload.get("delivery_channel") or ("email" if recipients else "none"),
            recipients,
        )
        fields["delivery_channel"] = delivery_channel
        fields["recipients_json"] = report_delivery_service.recipients_json(recipients)

    if schedule_keys.intersection(payload):
        merged = {
            "schedule_name": existing["schedule_name"],
            "product_id": existing.get("product_id"),
            "frequency": payload.get("frequency", existing["frequency"]),
            "run_time": payload.get("run_time", existing["run_time"]),
            "weekday": payload.get("weekday", existing.get("weekday")),
            "monthday": payload.get("monthday", existing.get("monthday")),
            "timezone": payload.get("timezone", existing["timezone"]),
            "use_llm": bool(existing.get("use_llm")),
            "export_format": existing["export_format"],
        }
        parsed = _parse_schedule_payload(merged, require_name=False)
        fields.update(
            {
                "frequency": parsed["frequency"],
                "run_time": parsed["run_time"],
                "weekday": parsed.get("weekday"),
                "monthday": parsed.get("monthday"),
                "timezone": parsed["timezone"],
                "next_run_at": _compute_next_run_at(
                    frequency=parsed["frequency"],
                    run_time=parsed["run_time"],
                    tz_name=parsed["timezone"],
                    weekday=parsed.get("weekday"),
                    monthday=parsed.get("monthday"),
                    now_utc=_now(),
                ),
            }
        )

    if not fields:
        return _public_schedule(existing)
    fields["updated_at"] = _now_iso()
    report_schedule_repository.update_schedule(actor["workspace_id"], schedule_id, fields)
    updated = report_schedule_repository.get_schedule(actor["workspace_id"], schedule_id) or existing
    return _public_schedule(updated)


def get_schedule_for_actor(actor: dict[str, Any], schedule_id: str) -> dict[str, Any]:
    _require_schedule_access(actor)
    return _get_schedule_or_raise(actor, schedule_id)


def archive_schedule(actor: dict[str, Any], schedule_id: str) -> dict[str, Any]:
    _require_schedule_access(actor)
    existing = _get_schedule_or_raise(actor, schedule_id)
    if existing.get("status") != ARCHIVED_STATUS:
        report_schedule_repository.update_schedule(
            actor["workspace_id"],
            schedule_id,
            {"status": ARCHIVED_STATUS, "updated_at": _now_iso()},
        )
    updated = report_schedule_repository.get_schedule(actor["workspace_id"], schedule_id) or existing
    return _public_schedule(updated)


def run_schedule(actor: dict[str, Any], schedule_id: str) -> dict[str, Any]:
    _require_schedule_access(actor)
    schedule = _get_schedule_or_raise(actor, schedule_id)
    if schedule.get("status") == ARCHIVED_STATUS:
        raise ReportScheduleError("Schedule has been archived")
    return _execute_schedule(schedule)


def run_due_schedules(actor: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    _require_schedule_access(actor)
    safe_limit = max(1, min(50, int(limit or 20)))
    due = report_schedule_repository.list_due_schedules(
        workspace_id=actor["workspace_id"],
        now_iso=_now_iso(),
        limit=safe_limit,
    )
    executed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for schedule in due:
        try:
            executed.append(_execute_schedule(schedule))
        except ReportScheduleError as exc:
            failed.append(
                {
                    "schedule": _public_schedule(schedule),
                    "error": str(exc),
                }
            )
    return {
        "checked_at": _now_iso(),
        "due_count": len(due),
        "executed_count": len(executed),
        "failed_count": len(failed),
        "items": executed,
        "failed": failed,
    }


def _execute_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    try:
        report = report_service.generate_report(
            product_id=schedule.get("product_id"),
            use_llm=bool(schedule.get("use_llm")),
        )
        if not report:
            raise ReportScheduleError("Report generation returned no result")
    except Exception as exc:
        report_schedule_repository.update_schedule(
            schedule["workspace_id"],
            schedule["schedule_id"],
            {
                "last_run_at": _to_iso(now),
                "last_error": str(exc),
                "next_run_at": _compute_next_run_at_from_schedule(schedule, now),
                "updated_at": _to_iso(now),
            },
        )
        raise ReportScheduleError(f"Scheduled report failed: {exc}") from exc

    report_schedule_repository.update_schedule(
        schedule["workspace_id"],
        schedule["schedule_id"],
        {
            "last_run_at": _to_iso(now),
            "last_report_id": report["report_id"],
            "last_error": None,
            "run_count": int(schedule.get("run_count") or 0) + 1,
            "next_run_at": _compute_next_run_at_from_schedule(schedule, now),
            "updated_at": _to_iso(now),
        },
    )
    updated = report_schedule_repository.get_schedule(schedule["workspace_id"], schedule["schedule_id"]) or schedule
    delivery = report_delivery_service.deliver_scheduled_report(updated, report)
    updated = report_schedule_repository.get_schedule(schedule["workspace_id"], schedule["schedule_id"]) or updated
    return {
        "schedule": _public_schedule(updated),
        "report": {
            "report_id": report["report_id"],
            "title": report["title"],
            "generated_at": report["generated_at"],
            "scope_type": report["scope_type"],
            "product_id": report.get("product_id"),
        },
        "delivery": delivery,
    }


def _parse_schedule_payload(payload: dict[str, Any], require_name: bool = True) -> dict[str, Any]:
    frequency = _validate_frequency(payload.get("frequency") or "weekly")
    run_time = _validate_run_time(payload.get("run_time") or DEFAULT_RUN_TIME)
    tz_name = _validate_timezone(payload.get("timezone") or DEFAULT_TIMEZONE)
    parsed: dict[str, Any] = {
        "schedule_name": _validate_name(payload.get("schedule_name")) if require_name else str(payload.get("schedule_name") or ""),
        "product_id": _clean_optional(payload.get("product_id")),
        "frequency": frequency,
        "run_time": run_time,
        "timezone": tz_name,
        "use_llm": _parse_bool(payload.get("use_llm")),
        "export_format": _validate_export_format(payload.get("export_format") or "docx"),
    }
    recipients = report_delivery_service.parse_recipients(
        payload.get("recipients") if "recipients" in payload else payload.get("recipient_emails")
    )
    parsed["recipients"] = recipients
    parsed["delivery_channel"] = _validate_delivery_channel(
        payload.get("delivery_channel") or ("email" if recipients else "none"),
        recipients,
    )
    if frequency == "weekly":
        parsed["weekday"] = _validate_weekday(payload.get("weekday"))
        parsed["monthday"] = None
    elif frequency == "monthly":
        parsed["weekday"] = None
        parsed["monthday"] = _validate_monthday(payload.get("monthday"))
    else:
        parsed["weekday"] = None
        parsed["monthday"] = None
    return parsed


def _get_schedule_or_raise(actor: dict[str, Any], schedule_id: str) -> dict[str, Any]:
    schedule = report_schedule_repository.get_schedule(actor["workspace_id"], str(schedule_id or "").strip())
    if not schedule:
        raise NotFound(f"Report schedule not found: {schedule_id}")
    return schedule


def _require_schedule_access(actor: dict[str, Any]) -> None:
    if not has_permission(actor, "reports.schedule"):
        raise PermissionDenied("Missing reports.schedule permission")


def _validate_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise ReportScheduleError("schedule_name is required")
    if len(name) > 80:
        raise ReportScheduleError("schedule_name must be 80 characters or fewer")
    return name


def _validate_frequency(value: Any) -> str:
    frequency = str(value or "").strip().lower()
    if frequency not in FREQUENCIES:
        raise ReportScheduleError("frequency must be daily, weekly, or monthly")
    return frequency


def _validate_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status not in STATUSES:
        raise ReportScheduleError("status must be active or paused")
    return status


def _validate_export_format(value: Any) -> str:
    export_format = str(value or "").strip().lower()
    if export_format not in EXPORT_FORMATS:
        raise ReportScheduleError("export_format must be one of docx, pdf, html, or markdown")
    return export_format


def _validate_delivery_channel(value: Any, recipients: list[str]) -> str:
    channel = str(value or "none").strip().lower()
    if channel not in {"none", "email"}:
        raise ReportScheduleError("delivery_channel must be none or email")
    if channel == "email" and not recipients:
        raise ReportScheduleError("recipient_emails are required when delivery_channel is email")
    return channel


def _validate_run_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d{2}:\d{2}", raw):
        raise ReportScheduleError("run_time must use HH:MM format")
    hour, minute = [int(part) for part in raw.split(":")]
    if hour > 23 or minute > 59:
        raise ReportScheduleError("run_time must be a valid 24-hour time")
    return f"{hour:02d}:{minute:02d}"


def _validate_weekday(value: Any) -> int:
    if value in {None, ""}:
        return 1
    try:
        weekday = int(value)
    except (TypeError, ValueError) as exc:
        raise ReportScheduleError("weekday must be an integer from 1 to 7") from exc
    if weekday < 1 or weekday > 7:
        raise ReportScheduleError("weekday must be between 1 and 7")
    return weekday


def _validate_monthday(value: Any) -> int:
    if value in {None, ""}:
        return 1
    try:
        monthday = int(value)
    except (TypeError, ValueError) as exc:
        raise ReportScheduleError("monthday must be an integer from 1 to 28") from exc
    if monthday < 1 or monthday > 28:
        raise ReportScheduleError("monthday must be between 1 and 28")
    return monthday


def _validate_timezone(value: Any) -> str:
    tz_name = str(value or "").strip()
    if tz_name not in TIMEZONES:
        raise ReportScheduleError("timezone must be Asia/Shanghai or UTC")
    return tz_name


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _compute_next_run_at_from_schedule(schedule: dict[str, Any], now_utc: datetime) -> str:
    return _compute_next_run_at(
        frequency=schedule["frequency"],
        run_time=schedule["run_time"],
        tz_name=schedule["timezone"],
        weekday=schedule.get("weekday"),
        monthday=schedule.get("monthday"),
        now_utc=now_utc,
    )


def _compute_next_run_at(
    frequency: str,
    run_time: str,
    tz_name: str,
    weekday: int | None = None,
    monthday: int | None = None,
    now_utc: datetime | None = None,
) -> str:
    now = now_utc or _now()
    tz = TIMEZONES[tz_name]
    local_now = now.astimezone(tz)
    local_time = _time_from_string(run_time)

    if frequency == "daily":
        candidate = datetime.combine(local_now.date(), local_time, tz)
        if candidate <= local_now:
            candidate += timedelta(days=1)
    elif frequency == "weekly":
        target_weekday = int(weekday or 1)
        days_ahead = (target_weekday - local_now.isoweekday()) % 7
        candidate = datetime.combine(local_now.date() + timedelta(days=days_ahead), local_time, tz)
        if candidate <= local_now:
            candidate += timedelta(days=7)
    else:
        target_day = int(monthday or 1)
        candidate = datetime.combine(local_now.date().replace(day=target_day), local_time, tz)
        if candidate <= local_now:
            candidate = _next_month_candidate(local_now, target_day, local_time, tz)

    return _to_iso(candidate.astimezone(UTC))


def _next_month_candidate(local_now: datetime, target_day: int, local_time: time, tz: timezone) -> datetime:
    year = local_now.year + (1 if local_now.month == 12 else 0)
    month = 1 if local_now.month == 12 else local_now.month + 1
    return datetime(year, month, target_day, local_time.hour, local_time.minute, tzinfo=tz)


def _time_from_string(value: str) -> time:
    hour, minute = [int(part) for part in value.split(":")]
    return time(hour=hour, minute=minute)


def _public_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    use_llm = bool(schedule.get("use_llm"))
    scope_type = schedule.get("scope_type") or ("product" if schedule.get("product_id") else "global")
    product_name = schedule.get("product_name")
    if scope_type == "product":
        scope_label = product_name or schedule.get("product_id") or "单品报告"
    else:
        scope_label = "全局经营报告"
    return {
        "schedule_id": schedule.get("schedule_id"),
        "workspace_id": schedule.get("workspace_id"),
        "schedule_name": schedule.get("schedule_name"),
        "scope_type": scope_type,
        "scope_label": scope_label,
        "product_id": schedule.get("product_id"),
        "product_name": product_name,
        "frequency": schedule.get("frequency"),
        "frequency_label": FREQUENCY_LABELS.get(schedule.get("frequency"), schedule.get("frequency")),
        "run_time": schedule.get("run_time"),
        "weekday": schedule.get("weekday"),
        "monthday": schedule.get("monthday"),
        "timezone": schedule.get("timezone"),
        "use_llm": use_llm,
        "generation_mode": "智能增强" if use_llm else "规则模板",
        "export_format": schedule.get("export_format"),
        "delivery_channel": schedule.get("delivery_channel") or "none",
        "recipients": report_delivery_service.parse_recipients(schedule.get("recipients_json")),
        "latest_delivery": _latest_delivery_summary(schedule),
        "status": schedule.get("status"),
        "next_run_at": schedule.get("next_run_at"),
        "last_run_at": schedule.get("last_run_at"),
        "last_report_id": schedule.get("last_report_id"),
        "last_error": schedule.get("last_error"),
        "run_count": int(schedule.get("run_count") or 0),
        "created_by": schedule.get("created_by"),
        "created_by_name": schedule.get("created_by_name"),
        "created_at": schedule.get("created_at"),
        "updated_at": schedule.get("updated_at"),
    }


def _latest_delivery_summary(schedule: dict[str, Any]) -> dict[str, Any] | None:
    if not schedule.get("latest_delivery_id"):
        return None
    return {
        "delivery_id": schedule.get("latest_delivery_id"),
        "status": schedule.get("latest_delivery_status"),
        "reason": schedule.get("latest_delivery_reason"),
        "message": schedule.get("latest_delivery_message"),
        "created_at": schedule.get("latest_delivery_at"),
    }


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _to_iso(_now())


def _to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
