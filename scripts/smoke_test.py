from __future__ import annotations

import argparse
import sys
from typing import Any
from uuid import uuid4

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ViralPick AI HTTP smoke checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Base URL without trailing slash.")
    parser.add_argument("--check-frontend", action="store_true", help="Also verify the root frontend document.")
    parser.add_argument("--email", default="demo@viralpick.ai", help="Login email used for authenticated smoke checks.")
    parser.add_argument("--password", default="ViralPick@2026", help="Login password used for authenticated smoke checks.")
    return parser.parse_args()


def get_json(base_url: str, path: str) -> dict[str, Any]:
    response = requests.get(f"{base_url}{path}", timeout=15)
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") is not True:
        raise AssertionError(f"{path} returned unsuccessful payload: {payload}")
    return payload["data"]


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    checks = {
        "/api/health": get_json(base_url, "/api/health"),
        "/api/ready": get_json(base_url, "/api/ready"),
        "/api/llm/status": get_json(base_url, "/api/llm/status"),
        "/api/overview": get_json(base_url, "/api/overview"),
        "/api/products?page=1&page_size=3": get_json(base_url, "/api/products?page=1&page_size=3"),
        "/api/forecast/sales?days=7": get_json(base_url, "/api/forecast/sales?days=7"),
    }
    login_response = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": args.email, "password": args.password},
        timeout=15,
    )
    login_response.raise_for_status()
    session = login_response.json()
    if session.get("success") is not True:
        raise AssertionError(f"Login failed: {session}")
    token = session["data"]["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    me_response = requests.get(f"{base_url}/api/auth/me", headers=auth_headers, timeout=15)
    me_response.raise_for_status()
    if me_response.json().get("success") is not True:
        raise AssertionError("/api/auth/me failed")

    permissions_response = requests.get(f"{base_url}/api/auth/permissions", headers=auth_headers, timeout=15)
    permissions_response.raise_for_status()
    permissions_payload = permissions_response.json()
    if (
        permissions_payload.get("success") is not True
        or "reports.generate" not in permissions_payload["data"].get("permissions", [])
        or "reports.schedule" not in permissions_payload["data"].get("permissions", [])
        or "brand.manage" not in permissions_payload["data"].get("permissions", [])
        or not permissions_payload["data"].get("matrix")
    ):
        raise AssertionError(f"/api/auth/permissions failed: {permissions_payload}")

    default_brand = {
        "brand_name": "ViralPick AI",
        "report_label": "店铺经营分析报告",
        "logo_url": "",
        "primary_color": "#00a99d",
        "accent_color": "#f0a51b",
        "cover_style": "signal-grid",
    }
    brand_response = requests.get(f"{base_url}/api/brand/settings", headers=auth_headers, timeout=15)
    brand_response.raise_for_status()
    brand_payload = brand_response.json()
    if brand_payload.get("success") is not True or not brand_payload["data"].get("cover_styles"):
        raise AssertionError(f"/api/brand/settings failed: {brand_payload}")
    custom_brand_response = requests.put(
        f"{base_url}/api/brand/settings",
        json={
            "brand_name": "ViralPick Smoke Lab",
            "report_label": "Executive Commerce Signal",
            "logo_url": "https://example.com/smoke-logo.png",
            "primary_color": "#2457ff",
            "accent_color": "#ffb21a",
            "cover_style": "executive-dark",
        },
        headers=auth_headers,
        timeout=15,
    )
    custom_brand_response.raise_for_status()
    custom_brand_payload = custom_brand_response.json()
    if custom_brand_payload.get("success") is not True or custom_brand_payload["data"].get("brand_name") != "ViralPick Smoke Lab":
        raise AssertionError(f"/api/brand/settings update failed: {custom_brand_payload}")

    team_response = requests.get(f"{base_url}/api/team/members", headers=auth_headers, timeout=15)
    team_response.raise_for_status()
    team_payload = team_response.json()
    if team_payload.get("success") is not True or not team_payload["data"].get("items"):
        raise AssertionError(f"/api/team/members failed: {team_payload}")

    invite_suffix = uuid4().hex[:8]
    invite_email = f"smoke-invite-{invite_suffix}@example.com"
    invite_password = f"Invite{invite_suffix}@2026"
    invite_response = requests.post(
        f"{base_url}/api/team/invitations",
        json={
            "email": invite_email,
            "display_name": "Smoke Invite",
            "role": "viewer",
            "expires_in_days": 7,
        },
        headers=auth_headers,
        timeout=15,
    )
    invite_response.raise_for_status()
    invite_payload = invite_response.json()
    if invite_payload.get("success") is not True or not invite_payload["data"].get("invite_token"):
        raise AssertionError(f"/api/team/invitations create failed: {invite_payload}")
    invite_token = invite_payload["data"]["invite_token"]
    invite_detail_response = requests.get(f"{base_url}/api/team/invitations/{invite_token}", timeout=15)
    invite_detail_response.raise_for_status()
    invite_detail_payload = invite_detail_response.json()
    if invite_detail_payload.get("success") is not True or invite_detail_payload["data"].get("email") != invite_email:
        raise AssertionError(f"/api/team/invitations/<token> failed: {invite_detail_payload}")
    invite_accept_response = requests.post(
        f"{base_url}/api/team/invitations/{invite_token}/accept",
        json={
            "display_name": "Smoke Viewer",
            "password": invite_password,
            "password_confirm": invite_password,
        },
        timeout=15,
    )
    invite_accept_response.raise_for_status()
    invite_accept_payload = invite_accept_response.json()
    if invite_accept_payload.get("success") is not True or invite_accept_payload["data"]["member"].get("email") != invite_email:
        raise AssertionError(f"/api/team/invitations/<token>/accept failed: {invite_accept_payload}")
    invited_login_response = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": invite_email, "password": invite_password},
        timeout=15,
    )
    invited_login_response.raise_for_status()
    if invited_login_response.json().get("success") is not True:
        raise AssertionError("Invited user could not log in")

    audit_response = requests.get(f"{base_url}/api/audit/logs?page=1&page_size=5", headers=auth_headers, timeout=15)
    audit_response.raise_for_status()
    audit_payload = audit_response.json()
    if audit_payload.get("success") is not True or "summary" not in audit_payload["data"]:
        raise AssertionError(f"/api/audit/logs failed: {audit_payload}")

    scoring_models_response = requests.get(f"{base_url}/api/scoring/models", headers=auth_headers, timeout=15)
    scoring_models_response.raise_for_status()
    scoring_models_payload = scoring_models_response.json()
    if scoring_models_payload.get("success") is not True or not scoring_models_payload["data"].get("active_model"):
        raise AssertionError(f"/api/scoring/models failed: {scoring_models_payload}")

    custom_model_response = requests.post(
        f"{base_url}/api/scoring/models",
        json={
            "model_name": "Smoke test scoring model",
            "note": "HTTP smoke validation",
            "weights": {
                "sales_growth": 0.10,
                "gmv_growth": 0.10,
                "positive_rate": 0.30,
                "comment_heat": 0.10,
                "price_competitiveness": 0.15,
                "video_interaction": 0.20,
                "conversion_rate": 0.05,
            },
        },
        headers=auth_headers,
        timeout=15,
    )
    custom_model_response.raise_for_status()
    custom_model_payload = custom_model_response.json()
    if custom_model_payload.get("success") is not True or custom_model_payload["data"].get("status") != "active":
        raise AssertionError(f"/api/scoring/models create failed: {custom_model_payload}")

    ops_response = requests.get(f"{base_url}/api/ops/status", headers=auth_headers, timeout=15)
    ops_response.raise_for_status()
    ops_payload = ops_response.json()
    if ops_payload.get("success") is not True or "database" not in ops_payload["data"]:
        raise AssertionError(f"/api/ops/status failed: {ops_payload}")

    monitoring_response = requests.get(f"{base_url}/api/ops/monitoring", headers=auth_headers, timeout=15)
    monitoring_response.raise_for_status()
    monitoring_payload = monitoring_response.json()
    if (
        monitoring_payload.get("success") is not True
        or not monitoring_payload["data"].get("metrics")
        or not monitoring_payload["data"].get("alerts")
    ):
        raise AssertionError(f"/api/ops/monitoring failed: {monitoring_payload}")

    alert_status_response = requests.get(f"{base_url}/api/ops/alerts/status", headers=auth_headers, timeout=15)
    alert_status_response.raise_for_status()
    alert_status_payload = alert_status_response.json()
    if alert_status_payload.get("success") is not True or alert_status_payload["data"].get("provider") != "webhook":
        raise AssertionError(f"/api/ops/alerts/status failed: {alert_status_payload}")

    backup_response = requests.post(f"{base_url}/api/ops/backups", headers=auth_headers, timeout=30)
    backup_response.raise_for_status()
    backup_payload = backup_response.json()
    if backup_payload.get("success") is not True or not backup_payload["data"].get("sha256"):
        raise AssertionError(f"/api/ops/backups failed: {backup_payload}")
    backup_filename = backup_payload["data"]["filename"]
    backup_verify_response = requests.get(
        f"{base_url}/api/ops/backups/{backup_filename}/verify",
        headers=auth_headers,
        timeout=30,
    )
    backup_verify_response.raise_for_status()
    backup_verify_payload = backup_verify_response.json()
    if (
        backup_verify_payload.get("success") is not True
        or backup_verify_payload["data"].get("integrity_check") != "ok"
        or backup_verify_payload["data"].get("sha256") != backup_payload["data"]["sha256"]
    ):
        raise AssertionError(f"/api/ops/backups/<filename>/verify failed: {backup_verify_payload}")

    automation_run_response = requests.post(f"{base_url}/api/ops/automation/run-once", headers=auth_headers, timeout=30)
    automation_run_response.raise_for_status()
    automation_run_payload = automation_run_response.json()
    if automation_run_payload.get("success") is not True or "totals" not in automation_run_payload.get("data", {}):
        raise AssertionError(f"/api/ops/automation/run-once failed: {automation_run_payload}")

    automation_runs_response = requests.get(f"{base_url}/api/ops/automation/runs", headers=auth_headers, timeout=15)
    automation_runs_response.raise_for_status()
    automation_runs_payload = automation_runs_response.json()
    if automation_runs_payload.get("success") is not True or not automation_runs_payload.get("data", {}).get("items"):
        raise AssertionError(f"/api/ops/automation/runs failed: {automation_runs_payload}")

    imports_response = requests.get(f"{base_url}/api/imports", headers=auth_headers, timeout=15)
    imports_response.raise_for_status()
    imports_payload = imports_response.json()
    if imports_payload.get("success") is not True or not imports_payload["data"].get("supported_datasets"):
        raise AssertionError(f"/api/imports failed: {imports_payload}")

    template_response = requests.get(f"{base_url}/api/imports/templates/comments", headers=auth_headers, timeout=15)
    template_response.raise_for_status()
    if b"comment_id,product_id" not in template_response.content:
        raise AssertionError("/api/imports/templates/comments did not return a comments CSV template")

    bad_csv = (
        "comment_id,product_id,mapped_product_category,review_text,sentiment,"
        "sentiment_label,category_source,data_source\n"
        "SMOKE-BAD-C-1,P0001,餐厨用品,缺少评分字段,negative,0,manual,merchant authorized sample\n"
    ).encode("utf-8-sig")
    failed_import = requests.post(
        f"{base_url}/api/imports",
        data={"dataset_type": "comments", "mode": "validate"},
        files={"file": ("smoke-bad-comments.csv", bad_csv, "text/csv")},
        headers=auth_headers,
        timeout=30,
    )
    if failed_import.status_code != 400:
        raise AssertionError(f"Expected failed import for error report smoke check: {failed_import.text}")
    jobs_response = requests.get(f"{base_url}/api/imports?limit=20", headers=auth_headers, timeout=15)
    jobs_response.raise_for_status()
    jobs_payload = jobs_response.json()
    failed_jobs = [
        item
        for item in jobs_payload.get("data", {}).get("items", [])
        if item.get("filename") == "smoke-bad-comments.csv" and item.get("status") == "failed"
    ]
    if not failed_jobs:
        raise AssertionError(f"Failed import job not recorded: {jobs_payload}")
    errors_response = requests.get(
        f"{base_url}/api/imports/{failed_jobs[0]['job_id']}/errors",
        headers=auth_headers,
        timeout=15,
    )
    errors_response.raise_for_status()
    if "rating".encode("utf-8") not in errors_response.content:
        raise AssertionError("/api/imports/<job_id>/errors did not include validation details")

    report_response = requests.post(
        f"{base_url}/api/reports/generate",
        json={"product_id": "P0001"},
        headers=auth_headers,
        timeout=30,
    )
    report_response.raise_for_status()
    report_payload = report_response.json()
    if report_payload.get("success") is not True or not report_payload["data"].get("report_id"):
        raise AssertionError(f"Report generation failed: {report_payload}")
    report_id = report_payload["data"]["report_id"]

    schedule_response = requests.post(
        f"{base_url}/api/reports/schedules",
        json={
            "schedule_name": f"Smoke recurring report {uuid4().hex[:6]}",
            "product_id": "P0001",
            "frequency": "weekly",
            "weekday": 1,
            "run_time": "09:00",
            "timezone": "Asia/Shanghai",
            "use_llm": False,
            "export_format": "docx",
            "recipient_emails": "ops@example.com",
        },
        headers=auth_headers,
        timeout=15,
    )
    schedule_response.raise_for_status()
    schedule_payload = schedule_response.json()
    if schedule_payload.get("success") is not True or not schedule_payload["data"].get("schedule_id"):
        raise AssertionError(f"Report schedule creation failed: {schedule_payload}")
    schedule_id = schedule_payload["data"]["schedule_id"]
    if schedule_payload["data"].get("delivery_channel") != "email":
        raise AssertionError(f"Report schedule delivery channel was not captured: {schedule_payload}")

    delivery_status_response = requests.get(f"{base_url}/api/reports/delivery/status", headers=auth_headers, timeout=15)
    delivery_status_response.raise_for_status()
    delivery_status_payload = delivery_status_response.json()
    if delivery_status_payload.get("success") is not True or delivery_status_payload["data"].get("provider") != "smtp":
        raise AssertionError(f"Report delivery status failed: {delivery_status_payload}")

    schedules_response = requests.get(f"{base_url}/api/reports/schedules", headers=auth_headers, timeout=15)
    schedules_response.raise_for_status()
    schedules_payload = schedules_response.json()
    if (
        schedules_payload.get("success") is not True
        or not any(item.get("schedule_id") == schedule_id for item in schedules_payload["data"].get("items", []))
    ):
        raise AssertionError(f"Report schedule list failed: {schedules_payload}")

    schedule_run_response = requests.post(
        f"{base_url}/api/reports/schedules/{schedule_id}/run",
        headers=auth_headers,
        timeout=30,
    )
    schedule_run_response.raise_for_status()
    schedule_run_payload = schedule_run_response.json()
    if (
        schedule_run_payload.get("success") is not True
        or not schedule_run_payload["data"].get("report", {}).get("report_id")
        or not schedule_run_payload["data"].get("delivery", {}).get("delivery_id")
        or schedule_run_payload["data"].get("schedule", {}).get("last_report_id")
        != schedule_run_payload["data"]["report"]["report_id"]
    ):
        raise AssertionError(f"Report schedule run failed: {schedule_run_payload}")

    deliveries_response = requests.get(
        f"{base_url}/api/reports/schedules/{schedule_id}/deliveries",
        headers=auth_headers,
        timeout=15,
    )
    deliveries_response.raise_for_status()
    deliveries_payload = deliveries_response.json()
    if (
        deliveries_payload.get("success") is not True
        or not deliveries_payload["data"].get("items")
        or deliveries_payload["data"]["items"][0].get("delivery_id")
        != schedule_run_payload["data"]["delivery"]["delivery_id"]
    ):
        raise AssertionError(f"Report schedule deliveries failed: {deliveries_payload}")

    retry_delivery_response = requests.post(
        f"{base_url}/api/reports/deliveries/{schedule_run_payload['data']['delivery']['delivery_id']}/retry",
        headers=auth_headers,
        timeout=30,
    )
    retry_delivery_response.raise_for_status()
    retry_delivery_payload = retry_delivery_response.json()
    if (
        retry_delivery_payload.get("success") is not True
        or retry_delivery_payload["data"].get("delivery", {}).get("retry_of_delivery_id")
        != schedule_run_payload["data"]["delivery"]["delivery_id"]
    ):
        raise AssertionError(f"Report delivery retry failed: {retry_delivery_payload}")

    retry_jobs_response = requests.get(
        f"{base_url}/api/reports/delivery/retries",
        headers=auth_headers,
        timeout=15,
    )
    retry_jobs_response.raise_for_status()
    retry_jobs_payload = retry_jobs_response.json()
    if retry_jobs_payload.get("success") is not True or "items" not in retry_jobs_payload.get("data", {}):
        raise AssertionError(f"Report delivery retry queue list failed: {retry_jobs_payload}")

    retry_jobs_run_response = requests.post(
        f"{base_url}/api/reports/delivery/retries/run-due",
        headers=auth_headers,
        timeout=30,
    )
    retry_jobs_run_response.raise_for_status()
    retry_jobs_run_payload = retry_jobs_run_response.json()
    if retry_jobs_run_payload.get("success") is not True or "processed_count" not in retry_jobs_run_payload.get("data", {}):
        raise AssertionError(f"Report delivery retry queue run failed: {retry_jobs_run_payload}")

    schedule_pause_response = requests.patch(
        f"{base_url}/api/reports/schedules/{schedule_id}",
        json={"status": "paused"},
        headers=auth_headers,
        timeout=15,
    )
    schedule_pause_response.raise_for_status()
    if schedule_pause_response.json().get("data", {}).get("status") != "paused":
        raise AssertionError(f"Report schedule pause failed: {schedule_pause_response.text}")

    run_due_response = requests.post(f"{base_url}/api/reports/schedules/run-due", headers=auth_headers, timeout=30)
    run_due_response.raise_for_status()
    if run_due_response.json().get("success") is not True:
        raise AssertionError(f"Report schedule run-due failed: {run_due_response.text}")

    schedule_archive_response = requests.delete(
        f"{base_url}/api/reports/schedules/{schedule_id}",
        headers=auth_headers,
        timeout=15,
    )
    schedule_archive_response.raise_for_status()
    if schedule_archive_response.json().get("data", {}).get("status") != "archived":
        raise AssertionError(f"Report schedule archive failed: {schedule_archive_response.text}")

    share_response = requests.post(
        f"{base_url}/api/reports/{report_id}/shares",
        json={"expires_in_days": 7},
        headers=auth_headers,
        timeout=15,
    )
    share_response.raise_for_status()
    share_payload = share_response.json()
    if share_payload.get("success") is not True or not share_payload["data"].get("share_token"):
        raise AssertionError(f"Report share creation failed: {share_payload}")
    shared_response = requests.get(
        f"{base_url}/api/reports/shared/{share_payload['data']['share_token']}",
        headers={"User-Agent": "ViralPick smoke test"},
        timeout=15,
    )
    shared_response.raise_for_status()
    shared_payload = shared_response.json()
    if (
        shared_payload.get("success") is not True
        or shared_payload["data"]["report"].get("report_id") != report_id
        or not shared_payload["data"].get("presentation", {}).get("highlights")
        or shared_payload["data"].get("presentation", {}).get("brand") != "ViralPick Smoke Lab"
    ):
        raise AssertionError(f"Shared report lookup failed: {shared_payload}")
    access_logs_response = requests.get(
        f"{base_url}/api/reports/shares/{share_payload['data']['share_id']}/access-logs?page=1&page_size=5",
        headers=auth_headers,
        timeout=15,
    )
    access_logs_response.raise_for_status()
    access_logs_payload = access_logs_response.json()
    if (
        access_logs_payload.get("success") is not True
        or access_logs_payload["data"].get("summary", {}).get("total", 0) < 1
        or not access_logs_payload["data"].get("items")
        or "127.0.0.1" in str(access_logs_payload["data"])
    ):
        raise AssertionError(f"Report share access log lookup failed: {access_logs_payload}")

    reset_brand_response = requests.put(
        f"{base_url}/api/brand/settings",
        json=default_brand,
        headers=auth_headers,
        timeout=15,
    )
    reset_brand_response.raise_for_status()

    export_response = requests.get(
        f"{base_url}/api/reports/{report_id}/export?format=docx",
        headers=auth_headers,
        timeout=30,
    )
    export_response.raise_for_status()
    if export_response.content[:2] != b"PK":
        raise AssertionError("DOCX report export does not look like a Word document")

    pdf_export_response = requests.get(
        f"{base_url}/api/reports/{report_id}/export?format=pdf",
        headers=auth_headers,
        timeout=30,
    )
    pdf_export_response.raise_for_status()
    if pdf_export_response.content[:4] != b"%PDF":
        raise AssertionError("PDF report export does not look like a PDF document")

    if args.check_frontend:
        response = requests.get(base_url, timeout=15)
        response.raise_for_status()
        if "ViralPick AI" not in response.text:
            raise AssertionError("Frontend root does not look like ViralPick AI.")

    for path, data in checks.items():
        print(f"OK {path}: {type(data).__name__}")
    print("OK /api/auth/login: authenticated")
    print("OK /api/auth/me: authenticated")
    print("OK /api/auth/permissions: authenticated permission matrix")
    print("OK /api/brand/settings: authenticated brand template")
    print("OK /api/team/members: authenticated")
    print("OK /api/team/invitations: authenticated invite lifecycle")
    print("OK /api/audit/logs: authenticated")
    print("OK /api/scoring/models: authenticated model management")
    print("OK /api/ops/status: authenticated")
    print("OK /api/ops/monitoring: authenticated alerts")
    print("OK /api/ops/alerts/status: authenticated alert channel")
    print("OK /api/ops/automation/run-once: authenticated automation")
    print("OK /api/ops/automation/runs: authenticated automation history")
    print("OK /api/ops/backups: authenticated backup")
    print("OK /api/ops/backups/<filename>/verify: authenticated backup validation")
    print("OK /api/imports: authenticated")
    print("OK /api/imports/templates/<dataset_type>: authenticated csv")
    print("OK /api/imports/<job_id>/errors: authenticated csv")
    print("OK /api/reports/generate: authenticated report")
    print("OK /api/reports/schedules: authenticated schedule lifecycle")
    print("OK /api/reports/delivery/status: authenticated delivery status")
    print("OK /api/reports/schedules/<id>/deliveries: authenticated delivery outbox")
    print("OK /api/reports/deliveries/<id>/retry: authenticated manual delivery retry")
    print("OK /api/reports/delivery/retries: authenticated retry queue")
    print("OK /api/reports/delivery/retries/run-due: authenticated retry queue runner")
    print("OK /api/reports/<id>/shares: authenticated share")
    print("OK /api/reports/shared/<token>: public report")
    print("OK /api/reports/shares/<id>/access-logs: authenticated visitor audit")
    print("OK /api/reports/<id>/export: authenticated docx")
    print("OK /api/reports/<id>/export: authenticated pdf")
    if args.check_frontend:
        print("OK /: frontend document")
    return 0


if __name__ == "__main__":
    sys.exit(main())
