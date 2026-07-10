from __future__ import annotations

import json
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from backend.config import (
    PUBLIC_BASE_URL,
    REPORT_DELIVERY_AUTO_RETRY_ENABLED,
    REPORT_DELIVERY_ENABLED,
    REPORT_DELIVERY_MAX_RETRY_ATTEMPTS,
    REPORT_DELIVERY_RETRY_BACKOFF_MINUTES,
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TIMEOUT_SECONDS,
    SMTP_USERNAME,
    SMTP_USE_SSL,
    SMTP_USE_TLS,
)
from backend.repositories import report_schedule_repository
from backend.services import report_export_service, report_service, report_share_service


RETRYABLE_FAILURE_REASONS = {"smtp_error", "export_error"}


class ReportDeliveryError(Exception):
    status_code = 400


class ReportDeliveryNotFound(ReportDeliveryError):
    status_code = 404


def get_status() -> dict[str, Any]:
    parsed = urlparse(PUBLIC_BASE_URL) if PUBLIC_BASE_URL else None
    return {
        "enabled": REPORT_DELIVERY_ENABLED,
        "configured": bool(SMTP_HOST and SMTP_FROM_EMAIL),
        "provider": "smtp",
        "smtp_host": SMTP_HOST,
        "smtp_port": SMTP_PORT,
        "from_email": SMTP_FROM_EMAIL,
        "public_base_host": parsed.netloc if parsed else "",
        "public_base_configured": bool(PUBLIC_BASE_URL),
        "timeout_seconds": SMTP_TIMEOUT_SECONDS,
        "auto_retry_enabled": REPORT_DELIVERY_AUTO_RETRY_ENABLED,
        "max_retry_attempts": _safe_max_retry_attempts(),
        "retry_backoff_minutes": _retry_backoff_minutes(),
    }


def deliver_scheduled_report(
    schedule: dict[str, Any],
    report: dict[str, Any],
    retry_of_delivery_id: str | None = None,
) -> dict[str, Any]:
    recipients = parse_recipients(schedule.get("recipients_json"))
    channel = str(schedule.get("delivery_channel") or "none").strip().lower()
    if channel == "none" or not recipients:
        return _record_delivery(
            schedule=schedule,
            report=report,
            recipients=recipients,
            channel=channel,
            status="skipped",
            reason="no_recipients",
            message="未配置收件人，已仅生成报告。",
            retry_of_delivery_id=retry_of_delivery_id,
        )

    status = get_status()
    if channel != "email":
        return _record_delivery(
            schedule=schedule,
            report=report,
            recipients=recipients,
            channel=channel,
            status="skipped",
            reason="unsupported_channel",
            message=f"暂不支持 {channel} 交付渠道。",
            retry_of_delivery_id=retry_of_delivery_id,
        )
    if not status["enabled"]:
        return _record_delivery(
            schedule=schedule,
            report=report,
            recipients=recipients,
            channel=channel,
            status="skipped",
            reason="disabled",
            message="报告邮件交付未启用，已记录待发送对象。",
            retry_of_delivery_id=retry_of_delivery_id,
        )
    if not status["configured"]:
        return _record_delivery(
            schedule=schedule,
            report=report,
            recipients=recipients,
            channel=channel,
            status="skipped",
            reason="not_configured",
            message="SMTP 未配置，无法发送报告邮件。",
            retry_of_delivery_id=retry_of_delivery_id,
        )

    try:
        exported = report_export_service.export_report(report["report_id"], schedule.get("export_format") or "docx")
    except report_export_service.ReportExportError as exc:
        return _record_delivery(
            schedule=schedule,
            report=report,
            recipients=recipients,
            channel=channel,
            status="failed",
            reason="export_error",
            message=f"报告导出失败：{exc}",
            retry_of_delivery_id=retry_of_delivery_id,
        )
    if not exported:
        return _record_delivery(
            schedule=schedule,
            report=report,
            recipients=recipients,
            channel=channel,
            status="failed",
            reason="report_not_found",
            message="报告导出失败，未找到报告。",
            retry_of_delivery_id=retry_of_delivery_id,
        )

    share = _create_optional_share(schedule, report)
    try:
        _send_email(schedule, report, recipients, exported, share)
    except Exception as exc:
        return _record_delivery(
            schedule=schedule,
            report=report,
            recipients=recipients,
            channel=channel,
            status="failed",
            reason="smtp_error",
            message=_truncate(f"SMTP 发送失败：{exc}", 500),
            share_id=(share or {}).get("share_id"),
            attachment_filename=exported.filename,
            export_format=exported.format,
            retry_of_delivery_id=retry_of_delivery_id,
        )

    return _record_delivery(
        schedule=schedule,
        report=report,
        recipients=recipients,
        channel=channel,
        status="sent",
        reason="sent",
        message=f"已发送给 {len(recipients)} 个收件人。",
        share_id=(share or {}).get("share_id"),
        attachment_filename=exported.filename,
        export_format=exported.format,
        retry_of_delivery_id=retry_of_delivery_id,
    )


def retry_delivery(actor: dict[str, Any], delivery_id: str) -> dict[str, Any]:
    delivery = report_schedule_repository.get_delivery(actor["workspace_id"], str(delivery_id or "").strip())
    if not delivery:
        raise ReportDeliveryNotFound(f"Report delivery not found: {delivery_id}")
    schedule = report_schedule_repository.get_schedule(actor["workspace_id"], delivery["schedule_id"])
    if not schedule:
        raise ReportDeliveryNotFound(f"Report schedule not found: {delivery['schedule_id']}")
    report = report_service.get_report(delivery["report_id"])
    if not report:
        raise ReportDeliveryNotFound(f"Report not found: {delivery['report_id']}")
    retry_schedule = _build_retry_schedule(schedule, delivery)
    retried = deliver_scheduled_report(retry_schedule, report, retry_of_delivery_id=delivery["delivery_id"])
    return {
        "original_delivery": _public_delivery(delivery),
        "delivery": retried,
    }


def list_retry_jobs(actor: dict[str, Any], status: str | None = None, limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(100, int(limit or 50)))
    safe_status = _validate_retry_job_status(status)
    rows = report_schedule_repository.list_retry_jobs(actor["workspace_id"], safe_status, safe_limit)
    return {
        "items": [_public_retry_job(row) for row in rows],
        "auto_retry_enabled": REPORT_DELIVERY_AUTO_RETRY_ENABLED,
        "retryable_reasons": sorted(RETRYABLE_FAILURE_REASONS),
    }


def run_due_retries(actor: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(100, int(limit or 20)))
    now = _now_iso()
    rows = report_schedule_repository.list_due_retry_jobs(actor["workspace_id"], now, safe_limit)
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(_execute_retry_job(actor, row))
    return {
        "due_count": len(rows),
        "processed_count": len(items),
        "succeeded_count": sum(1 for item in items if item.get("job", {}).get("status") == "succeeded"),
        "pending_count": sum(1 for item in items if item.get("job", {}).get("status") == "pending"),
        "exhausted_count": sum(1 for item in items if item.get("job", {}).get("status") == "exhausted"),
        "cancelled_count": sum(1 for item in items if item.get("job", {}).get("status") == "cancelled"),
        "items": items,
    }


def list_deliveries(actor: dict[str, Any], schedule: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(100, int(limit or 20)))
    rows = report_schedule_repository.list_deliveries(actor["workspace_id"], schedule["schedule_id"], safe_limit)
    return {
        "schedule_id": schedule["schedule_id"],
        "items": [_public_delivery(row) for row in rows],
    }


def _execute_retry_job(actor: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    report_schedule_repository.update_retry_job(
        actor["workspace_id"],
        job["job_id"],
        {"status": "running", "last_attempt_at": now, "updated_at": now},
    )
    original_delivery = report_schedule_repository.get_delivery(actor["workspace_id"], job["original_delivery_id"])
    if not original_delivery:
        return _finish_retry_job(actor, job, "cancelled", "Original delivery no longer exists")
    schedule = report_schedule_repository.get_schedule(actor["workspace_id"], original_delivery["schedule_id"])
    if not schedule:
        return _finish_retry_job(actor, job, "cancelled", "Report schedule no longer exists")
    report = report_service.get_report(original_delivery["report_id"])
    if not report:
        return _finish_retry_job(actor, job, "cancelled", "Report no longer exists")

    retry_schedule = _build_retry_schedule(schedule, original_delivery)
    retried = deliver_scheduled_report(
        retry_schedule,
        report,
        retry_of_delivery_id=original_delivery["delivery_id"],
    )
    attempts = int(job.get("attempts") or 0) + 1
    max_attempts = max(1, int(job.get("max_attempts") or _safe_max_retry_attempts() or 1))
    fields: dict[str, Any] = {
        "attempts": attempts,
        "latest_delivery_id": retried.get("delivery_id"),
        "last_attempt_at": now,
        "updated_at": _now_iso(),
    }
    if retried.get("status") == "sent":
        fields.update({"status": "succeeded", "last_error": None})
    elif _is_retryable_delivery(retried) and attempts < max_attempts:
        fields.update(
            {
                "status": "pending",
                "next_attempt_at": _future_iso(_retry_delay_for_attempt(attempts)),
                "last_error": retried.get("message") or retried.get("reason"),
            }
        )
    else:
        fields.update(
            {
                "status": "exhausted",
                "last_error": retried.get("message") or retried.get("reason") or "Retry attempts exhausted",
            }
        )
    report_schedule_repository.update_retry_job(actor["workspace_id"], job["job_id"], fields)
    refreshed = report_schedule_repository.get_retry_job(actor["workspace_id"], job["job_id"])
    return {
        "job": _public_retry_job(refreshed or {**job, **fields}),
        "delivery": retried,
    }


def _finish_retry_job(actor: dict[str, Any], job: dict[str, Any], status: str, message: str) -> dict[str, Any]:
    fields = {
        "status": status,
        "last_error": message,
        "updated_at": _now_iso(),
    }
    report_schedule_repository.update_retry_job(actor["workspace_id"], job["job_id"], fields)
    refreshed = report_schedule_repository.get_retry_job(actor["workspace_id"], job["job_id"])
    return {
        "job": _public_retry_job(refreshed or {**job, **fields}),
        "delivery": None,
    }


def _build_retry_schedule(schedule: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any]:
    return {
        **schedule,
        "delivery_channel": delivery.get("channel") or schedule.get("delivery_channel") or "none",
        "recipients_json": delivery.get("recipients_json") or schedule.get("recipients_json") or "[]",
        "export_format": delivery.get("export_format") or schedule.get("export_format") or "docx",
    }


def parse_recipients(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        candidates = value
    else:
        text = str(value or "").strip()
        try:
            loaded = json.loads(text)
            candidates = loaded if isinstance(loaded, list) else [text]
        except json.JSONDecodeError:
            candidates = text.replace(";", ",").split(",")
    recipients: list[str] = []
    for candidate in candidates:
        email = str(candidate or "").strip().lower()
        if not email:
            continue
        if "@" not in email or " " in email:
            raise ReportDeliveryError("recipient emails must be valid email addresses")
        if email not in recipients:
            recipients.append(email)
    if len(recipients) > 20:
        raise ReportDeliveryError("recipient email count must be 20 or fewer")
    return recipients


def recipients_json(recipients: list[str]) -> str:
    return json.dumps(recipients, ensure_ascii=False)


def _send_email(
    schedule: dict[str, Any],
    report: dict[str, Any],
    recipients: list[str],
    exported: report_export_service.ExportedReport,
    share: dict[str, Any] | None,
) -> None:
    message = EmailMessage()
    message["Subject"] = f"ViralPick AI 定时报告：{report.get('title') or report.get('report_id')}"
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = ", ".join(recipients)
    share_url = _share_url(share)
    body = [
        "ViralPick AI 已生成定时运营报告。",
        "",
        f"任务：{schedule.get('schedule_name')}",
        f"报告：{report.get('title')}",
        f"报告编号：{report.get('report_id')}",
        f"生成时间：{report.get('generated_at')}",
    ]
    if share_url:
        body.extend(["", f"公开只读链接：{share_url}"])
    body.extend(["", "附件为本次报告导出文件。"])
    message.set_content("\n".join(body))
    maintype, subtype = _split_mimetype(exported.mimetype)
    message.add_attachment(
        exported.content,
        maintype=maintype,
        subtype=subtype,
        filename=exported.filename,
    )

    if SMTP_USE_SSL:
        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    else:
        smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    try:
        if SMTP_USE_TLS and not SMTP_USE_SSL:
            smtp.starttls()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)
    finally:
        smtp.quit()


def _create_optional_share(schedule: dict[str, Any], report: dict[str, Any]) -> dict[str, Any] | None:
    if not PUBLIC_BASE_URL:
        return None
    return report_share_service.create_share(
        report_id=report["report_id"],
        actor={
            "workspace_id": schedule.get("workspace_id"),
            "user_id": schedule.get("created_by"),
        },
        expires_in_days=14,
    )


def _record_delivery(
    schedule: dict[str, Any],
    report: dict[str, Any],
    recipients: list[str],
    channel: str,
    status: str,
    reason: str,
    message: str,
    share_id: str | None = None,
    export_format: str | None = None,
    attachment_filename: str | None = None,
    retry_of_delivery_id: str | None = None,
) -> dict[str, Any]:
    delivery = {
        "delivery_id": f"D-{uuid4().hex[:14]}",
        "schedule_id": schedule["schedule_id"],
        "workspace_id": schedule["workspace_id"],
        "report_id": report["report_id"],
        "channel": channel or "none",
        "recipients_json": recipients_json(recipients),
        "status": status,
        "reason": reason,
        "message": _truncate(message, 500),
        "share_id": share_id,
        "export_format": export_format or schedule.get("export_format"),
        "attachment_filename": attachment_filename,
        "retry_of_delivery_id": retry_of_delivery_id,
        "created_at": _now_iso(),
    }
    report_schedule_repository.create_delivery(delivery)
    public = _public_delivery(delivery)
    retry_job = _maybe_enqueue_auto_retry(delivery, retry_of_delivery_id)
    if retry_job:
        public["retry_job"] = retry_job
    return public


def _public_delivery(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "delivery_id": row.get("delivery_id"),
        "schedule_id": row.get("schedule_id"),
        "report_id": row.get("report_id"),
        "channel": row.get("channel"),
        "recipients": parse_recipients(row.get("recipients_json")),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "message": row.get("message"),
        "share_id": row.get("share_id"),
        "export_format": row.get("export_format"),
        "attachment_filename": row.get("attachment_filename"),
        "retry_of_delivery_id": row.get("retry_of_delivery_id"),
        "created_at": row.get("created_at"),
    }


def _maybe_enqueue_auto_retry(delivery: dict[str, Any], retry_of_delivery_id: str | None) -> dict[str, Any] | None:
    if retry_of_delivery_id:
        return None
    if not REPORT_DELIVERY_AUTO_RETRY_ENABLED or not _is_retryable_delivery(delivery):
        return None
    max_attempts = _safe_max_retry_attempts()
    if max_attempts <= 0:
        return None
    existing = report_schedule_repository.get_open_retry_job_for_delivery(
        delivery["workspace_id"],
        delivery["delivery_id"],
    )
    if existing:
        return _public_retry_job(existing)
    now = _now_iso()
    job = {
        "job_id": f"RJ-{uuid4().hex[:14]}",
        "workspace_id": delivery["workspace_id"],
        "schedule_id": delivery["schedule_id"],
        "original_delivery_id": delivery["delivery_id"],
        "latest_delivery_id": delivery["delivery_id"],
        "status": "pending",
        "reason": delivery.get("reason"),
        "attempts": 0,
        "max_attempts": max_attempts,
        "next_attempt_at": _future_iso(_retry_delay_for_attempt(0)),
        "last_attempt_at": None,
        "last_error": delivery.get("message") or delivery.get("reason"),
        "created_at": now,
        "updated_at": now,
    }
    report_schedule_repository.create_retry_job(job)
    return _public_retry_job(job)


def _is_retryable_delivery(delivery: dict[str, Any]) -> bool:
    return delivery.get("status") == "failed" and delivery.get("reason") in RETRYABLE_FAILURE_REASONS


def _public_retry_job(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": row.get("job_id"),
        "workspace_id": row.get("workspace_id"),
        "schedule_id": row.get("schedule_id"),
        "schedule_name": row.get("schedule_name"),
        "original_delivery_id": row.get("original_delivery_id"),
        "latest_delivery_id": row.get("latest_delivery_id"),
        "latest_delivery_status": row.get("latest_delivery_status"),
        "latest_delivery_reason": row.get("latest_delivery_reason"),
        "original_report_id": row.get("original_report_id"),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "attempts": int(row.get("attempts") or 0),
        "max_attempts": int(row.get("max_attempts") or 0),
        "next_attempt_at": row.get("next_attempt_at"),
        "last_attempt_at": row.get("last_attempt_at"),
        "last_error": row.get("last_error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _validate_retry_job_status(status: str | None) -> str | None:
    if status is None or str(status).strip() == "":
        return None
    value = str(status).strip().lower()
    allowed = {"pending", "running", "succeeded", "exhausted", "cancelled"}
    if value not in allowed:
        raise ReportDeliveryError("retry job status must be pending, running, succeeded, exhausted, or cancelled")
    return value


def _share_url(share: dict[str, Any] | None) -> str:
    if not share or not PUBLIC_BASE_URL or not share.get("share_token"):
        return ""
    return f"{PUBLIC_BASE_URL.rstrip('/')}/#shared-report={share['share_token']}"


def _split_mimetype(value: str) -> tuple[str, str]:
    bare = str(value or "application/octet-stream").split(";", 1)[0].strip()
    if "/" not in bare:
        return "application", "octet-stream"
    maintype, subtype = bare.split("/", 1)
    return maintype or "application", subtype or "octet-stream"


def _truncate(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _future_iso(minutes: int) -> str:
    return (datetime.now(UTC) + timedelta(minutes=max(0, minutes))).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_max_retry_attempts() -> int:
    return max(0, min(10, int(REPORT_DELIVERY_MAX_RETRY_ATTEMPTS or 0)))


def _retry_delay_for_attempt(attempt_index: int) -> int:
    values = _retry_backoff_minutes()
    if not values:
        return 5
    index = max(0, int(attempt_index or 0))
    if index >= len(values):
        return values[-1]
    return values[index]


def _retry_backoff_minutes() -> list[int]:
    values: list[int] = []
    for raw in str(REPORT_DELIVERY_RETRY_BACKOFF_MINUTES or "5,30,120").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value >= 0:
            values.append(min(value, 24 * 60))
    return values or [5, 30, 120]
