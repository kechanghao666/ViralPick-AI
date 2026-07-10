from __future__ import annotations

from io import BytesIO

from flask import Blueprint, g, request, send_file

from backend import migrations as db_migrations
from backend.auth import require_auth, require_permission, strict_auth
from backend.config import APP_ENV, APP_NAME, APP_VERSION, DATABASE_PATH
from backend.db import fetch_one
from backend.permissions import permission_summary
from backend.services import (
    audit_service,
    alert_service,
    assistant_service,
    automation_service,
    auth_service,
    brand_service,
    business_center_service,
    comment_nlp_service,
    competitor_service,
    forecast_service,
    hot_score_service,
    import_service,
    local_knowledge_service,
    llm_adapter,
    ops_service,
    platform_connect_service,
    product_service,
    report_delivery_service,
    report_schedule_service,
    report_share_service,
    report_export_service,
    report_service,
    sales_analysis_service,
    scoring_model_service,
    team_service,
)
from backend.services.analytics_service import (
    clamp_limit,
    get_category_summary,
    get_competitors,
    get_hot_products,
    get_overview,
    get_product_detail,
    get_product_rankings,
    get_sales_trend,
    get_sentiment_summary,
)
from backend.utils.response import error, ok
from backend.utils.validators import parse_horizon, parse_pagination, parse_sort_order


api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/health")
def health():
    return ok(
        {
            "app": APP_NAME,
            "version": APP_VERSION,
            "environment": APP_ENV,
            "database_path": str(DATABASE_PATH),
            "database_exists": DATABASE_PATH.exists(),
        }
    )


@api_bp.get("/ready")
def ready():
    if not DATABASE_PATH.exists():
        return error("Database does not exist", status=503)
    try:
        migration_status = db_migrations.get_migration_status(DATABASE_PATH)
        if migration_status["pending"]:
            pending_versions = ", ".join(item["version"] for item in migration_status["pending"])
            return error(f"Database migrations are pending: {pending_versions}", status=503)
        product_count = fetch_one("SELECT COUNT(*) AS count FROM products") or {"count": 0}
    except Exception as exc:
        return error(f"Database is not ready: {exc}", status=503)
    if int(product_count.get("count") or 0) <= 0:
        return error("Database has no product data", status=503)
    return ok(
        {
            "database": "ready",
            "product_count": product_count["count"],
            "schema_version": migration_status["current_version"],
            "version": APP_VERSION,
        }
    )


@api_bp.get("/llm/status")
def llm_status():
    return ok(llm_adapter.get_status())


@api_bp.get("/knowledge/status")
def knowledge_status():
    return ok(local_knowledge_service.get_status())


@api_bp.post("/knowledge/rebuild")
@require_permission("imports.manage", strict=False)
def knowledge_rebuild():
    try:
        return ok(local_knowledge_service.rebuild_knowledge_base())
    except Exception as exc:
        return error(str(exc), status=500)


@api_bp.get("/knowledge/search")
def knowledge_search():
    query = str(request.args.get("q") or request.args.get("query") or "").strip()
    if not query:
        return error("query is required", status=400)
    limit = clamp_limit(request.args.get("limit"), default=5, maximum=10)
    product_id = str(request.args.get("product_id") or "").strip() or None
    return ok(
        {
            "items": local_knowledge_service.search(query, product_id=product_id, limit=limit),
            "status": local_knowledge_service.get_status(),
        }
    )


@api_bp.post("/assistant/chat")
def assistant_chat():
    payload = request.get_json(silent=True) or {}
    use_llm = _parse_bool(payload.get("use_llm"))
    try:
        return ok(
            assistant_service.answer_question(
                message=payload.get("message") or payload.get("question"),
                product_id=payload.get("product_id"),
                page=payload.get("page"),
                use_llm=True if use_llm is None else bool(use_llm),
            )
        )
    except assistant_service.AssistantError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.post("/auth/login")
def auth_login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    if not email or not password:
        return error("email and password are required", status=400)
    try:
        session = auth_service.login(
            email=email,
            password=password,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        )
    except auth_service.AuthenticationError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 401))
    return ok(session)


@api_bp.post("/auth/register")
def auth_register():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    password_confirm = str(payload.get("password_confirm") or payload.get("confirm_password") or "")
    if password_confirm and password != password_confirm:
        return error("password confirmation does not match", status=400)
    try:
        session = auth_service.register(
            email=email,
            password=password,
            display_name=payload.get("display_name"),
            workspace_name=payload.get("workspace_name"),
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        )
    except auth_service.AuthenticationError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    return ok(session, status=201)


@api_bp.get("/auth/me")
@strict_auth
def auth_me():
    return ok({**g.current_user, "permissions": permission_summary(g.current_user)["permissions"]})


@api_bp.get("/auth/permissions")
@strict_auth
def auth_permissions():
    return ok(permission_summary(g.current_user))


@api_bp.get("/brand/settings")
@require_permission("brand.view")
def brand_settings():
    try:
        return ok(brand_service.get_brand_settings(g.current_user))
    except brand_service.BrandError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.put("/brand/settings")
@require_permission("brand.manage")
def update_brand_settings():
    payload = request.get_json(silent=True) or {}
    try:
        settings = brand_service.update_brand_settings(g.current_user, payload)
    except brand_service.BrandError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="brand.settings.update",
        user=g.current_user,
        resource_type="brand_settings",
        resource_id=g.current_user.get("workspace_id"),
        metadata={
            "brand_name": settings.get("brand_name"),
            "report_label": settings.get("report_label"),
            "cover_style": settings.get("cover_style"),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(settings)


@api_bp.post("/auth/logout")
@strict_auth
def auth_logout():
    auth_service.logout(
        request.headers.get("Authorization"),
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok({"logged_out": True})


@api_bp.get("/team/members")
@require_permission("team.view")
def team_members():
    return ok(team_service.list_members(g.current_user))


@api_bp.get("/team/invitations")
@require_permission("team.manage")
def team_invitations():
    limit = clamp_limit(request.args.get("limit"), default=50, maximum=100)
    return ok(team_service.list_invitations(g.current_user, limit=limit))


@api_bp.post("/team/invitations")
@require_permission("team.manage")
def create_team_invitation():
    payload = request.get_json(silent=True) or {}
    try:
        invitation = team_service.create_invitation(g.current_user, payload)
    except team_service.TeamError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    invitation["invite_url"] = _frontend_invite_url(invitation["invite_token"])
    auth_service.audit(
        action="team.invitation.create",
        user=g.current_user,
        resource_type="team_invitation",
        resource_id=invitation["invitation_id"],
        metadata={
            "email": invitation["email"],
            "role": invitation["role"],
            "expires_at": invitation["expires_at"],
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(invitation, status=201)


@api_bp.get("/team/invitations/<invite_token>")
def team_invitation_detail(invite_token: str):
    try:
        return ok(team_service.get_invitation_by_token(invite_token))
    except team_service.TeamError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.post("/team/invitations/<invite_token>/accept")
def accept_team_invitation(invite_token: str):
    payload = request.get_json(silent=True) or {}
    try:
        accepted = team_service.accept_invitation(invite_token, payload)
    except team_service.TeamError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    member = accepted["member"]
    auth_service.audit(
        action="team.invitation.accept",
        user={
            "workspace_id": member.get("workspace_id"),
            "user_id": member.get("user_id"),
        },
        resource_type="team_invitation",
        resource_id=member.get("user_id"),
        metadata={"email": member.get("email"), "role": member.get("role")},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(accepted, status=201)


@api_bp.delete("/team/invitations/<invitation_id>")
@require_permission("team.manage")
def revoke_team_invitation(invitation_id: str):
    try:
        invitation = team_service.revoke_invitation(g.current_user, invitation_id)
    except team_service.TeamError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="team.invitation.revoke",
        user=g.current_user,
        resource_type="team_invitation",
        resource_id=invitation_id,
        metadata={"email": invitation.get("email"), "status": invitation.get("status")},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(invitation)


@api_bp.post("/team/members")
@require_permission("team.manage")
def create_team_member():
    payload = request.get_json(silent=True) or {}
    try:
        member = team_service.create_member(g.current_user, payload)
    except team_service.TeamError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="team.member.create",
        user=g.current_user,
        resource_type="user",
        resource_id=member["user_id"],
        metadata={"email": member["email"], "role": member["role"]},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(member, status=201)


@api_bp.patch("/team/members/<user_id>")
@require_permission("team.manage")
def update_team_member(user_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        member = team_service.update_member(g.current_user, user_id, payload)
    except team_service.TeamError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="team.member.update",
        user=g.current_user,
        resource_type="user",
        resource_id=member["user_id"],
        metadata={
            "role": member["role"],
            "status": member["status"],
            "updated_fields": sorted(payload.keys()),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(member)


@api_bp.get("/audit/logs")
@require_permission("audit.view")
def audit_logs():
    page, page_size = parse_pagination(request.args)
    try:
        return ok(
            audit_service.list_logs(
                actor=g.current_user,
                action=request.args.get("action"),
                resource_type=request.args.get("resource_type"),
                user_id=request.args.get("user_id"),
                page=page,
                page_size=page_size,
            )
        )
    except audit_service.AuditError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/ops/status")
@require_permission("ops.view")
def ops_status():
    try:
        return ok(ops_service.get_status(g.current_user))
    except ops_service.OpsError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/ops/backups")
@require_permission("ops.view")
def ops_backups():
    try:
        return ok(ops_service.list_backups(g.current_user))
    except ops_service.OpsError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/ops/backups/<filename>/verify")
@require_permission("ops.manage")
def verify_ops_backup(filename: str):
    try:
        return ok(ops_service.verify_backup(g.current_user, filename))
    except ops_service.OpsError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/ops/monitoring")
@require_permission("ops.view")
def ops_monitoring():
    try:
        return ok(ops_service.get_monitoring(g.current_user))
    except ops_service.OpsError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/ops/alerts/status")
@require_permission("ops.view")
def ops_alert_status():
    try:
        ops_service.require_ops_access(g.current_user)
        return ok(alert_service.get_status())
    except ops_service.OpsError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/ops/automation/runs")
@require_permission("ops.view")
def ops_automation_runs():
    limit = clamp_limit(request.args.get("limit"), default=20, maximum=100)
    return ok(automation_service.list_runs(g.current_user.get("workspace_id"), limit=limit))


@api_bp.post("/ops/automation/run-once")
@require_permission("ops.manage")
def run_ops_automation_once():
    try:
        result = automation_service.run_once(
            workspace_id=g.current_user.get("workspace_id"),
            schedule_limit=clamp_limit(request.args.get("schedule_limit"), default=20, maximum=100),
            retry_limit=clamp_limit(request.args.get("retry_limit"), default=20, maximum=100),
            trigger="ops-api",
        )
    except automation_service.AutomationError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="ops.automation.run_once",
        user=g.current_user,
        resource_type="automation_run",
        resource_id=result.get("items", [{}])[0].get("run", {}).get("run_id") if result.get("items") else "none",
        metadata={
            "workspace_count": result.get("workspace_count"),
            "status": result.get("status"),
            "totals": result.get("totals"),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(result)


@api_bp.post("/ops/alerts/dispatch")
@require_permission("alerts.manage")
def dispatch_ops_alerts():
    try:
        monitoring = ops_service.get_monitoring(g.current_user)
        result = alert_service.dispatch_monitoring_alerts(monitoring, actor=g.current_user)
    except ops_service.OpsError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    except alert_service.AlertError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="ops.alert.dispatch",
        user=g.current_user,
        resource_type="monitoring_alert",
        resource_id=result.get("reason"),
        metadata={
            "sent": result.get("sent"),
            "reason": result.get("reason"),
            "matched_count": len(result.get("matched_alerts") or []),
            "provider": result.get("status", {}).get("provider"),
            "endpoint_host": result.get("status", {}).get("endpoint_host"),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(result)


@api_bp.post("/ops/backups")
@require_permission("ops.manage")
def create_ops_backup():
    try:
        backup = ops_service.create_backup(g.current_user)
    except ops_service.OpsError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="ops.backup.create",
        user=g.current_user,
        resource_type="backup",
        resource_id=backup["filename"],
        metadata={"size_bytes": backup["size_bytes"], "sha256": backup["sha256"]},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(backup, status=201)


@api_bp.get("/imports")
@require_permission("imports.manage")
def import_jobs():
    limit = clamp_limit(request.args.get("limit"), default=20, maximum=100)
    return ok(import_service.list_import_jobs(g.current_user, limit=limit))


@api_bp.get("/imports/schema")
def import_schema():
    return ok(import_service.get_import_schema())


@api_bp.post("/imports/preview")
def preview_import_job():
    uploaded_file = request.files.get("file")
    dataset_type = request.form.get("dataset_type") or None
    try:
        return ok(import_service.preview_import(uploaded_file=uploaded_file, dataset_type=dataset_type), status=201)
    except import_service.ImportValidationError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.post("/imports/commit")
def commit_import_job():
    payload = request.get_json(silent=True) or {}
    try:
        job = import_service.commit_import(
            preview_id=payload.get("preview_id"),
            dataset_type=payload.get("dataset_type"),
            field_mapping=payload.get("field_mapping") or {},
            mode=payload.get("mode", "append"),
            user=getattr(g, "current_user", None),
        )
    except import_service.ImportNotFoundError as exc:
        return error(str(exc), status=404)
    except import_service.ImportValidationError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    return ok(job, status=201)


@api_bp.get("/imports/templates/<dataset_type>")
@require_permission("imports.manage")
def download_import_template(dataset_type: str):
    try:
        exported = import_service.export_template(dataset_type)
    except import_service.ImportValidationError as exc:
        return error(str(exc), status=400)
    return send_file(
        BytesIO(exported.content),
        mimetype=exported.mimetype,
        as_attachment=True,
        download_name=exported.filename,
        max_age=0,
    )


@api_bp.get("/imports/<job_id>/errors")
@require_permission("imports.manage")
def download_import_errors(job_id: str):
    try:
        exported = import_service.export_error_report(job_id, g.current_user)
    except import_service.ImportNotFoundError as exc:
        return error(str(exc), status=404)
    except import_service.ImportValidationError as exc:
        return error(str(exc), status=400)
    auth_service.audit(
        action="data_import.errors.download",
        user=g.current_user,
        resource_type="import_job",
        resource_id=job_id,
        metadata={"filename": exported.filename},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return send_file(
        BytesIO(exported.content),
        mimetype=exported.mimetype,
        as_attachment=True,
        download_name=exported.filename,
        max_age=0,
    )


@api_bp.post("/imports")
@require_permission("imports.manage")
def create_import_job():
    uploaded_file = request.files.get("file")
    dataset_type = request.form.get("dataset_type", "")
    mode = request.form.get("mode", "validate")
    try:
        job = import_service.run_import(
            uploaded_file=uploaded_file,
            dataset_type=dataset_type,
            mode=mode,
            user=g.current_user,
        )
    except import_service.ImportValidationError as exc:
        return error(str(exc), status=400)
    auth_service.audit(
        action="data_import.create",
        user=g.current_user,
        resource_type="import_job",
        resource_id=job["job_id"],
        metadata={
            "dataset_type": job["dataset_type"],
            "mode": job["mode"],
            "status": job["status"],
            "row_count": job["row_count"],
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(job, status=201)


@api_bp.get("/overview")
def overview():
    return ok(get_overview())


@api_bp.get("/dashboard/executive")
def executive_dashboard():
    return ok(business_center_service.get_executive_dashboard())


@api_bp.get("/marketing/summary")
def marketing_summary():
    return ok(business_center_service.get_marketing_summary())


@api_bp.get("/inventory/summary")
def inventory_summary():
    return ok(business_center_service.get_inventory_summary())


@api_bp.get("/platforms/connections")
def platform_connections():
    return ok(platform_connect_service.list_platform_connections())


@api_bp.post("/platforms/sync")
def sync_platform_connections():
    payload = request.get_json(silent=True) or {}
    try:
        return ok(platform_connect_service.sync_platform(payload.get("platform_key")))
    except ValueError as exc:
        return error(str(exc), status=400)


@api_bp.post("/platforms/authorize")
def authorize_platform_connection():
    payload = request.get_json(silent=True) or {}
    try:
        return ok(platform_connect_service.authorize_platform(payload), status=201)
    except ValueError as exc:
        return error(str(exc), status=400)


@api_bp.get("/products/rankings")
def product_rankings():
    metric = request.args.get("metric", "gmv")
    limit = clamp_limit(request.args.get("limit"), default=10)
    return ok(
        {
            "metric": metric,
            "items": get_product_rankings(metric=metric, limit=limit),
        }
    )


@api_bp.get("/products")
def products():
    page, page_size = parse_pagination(request.args)
    sort = request.args.get("sort", "hot_score")
    order = parse_sort_order(request.args.get("order"))
    return ok(
        product_service.list_products(
            keyword=request.args.get("keyword"),
            category=request.args.get("category"),
            risk_level=request.args.get("risk_level"),
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
        )
    )


@api_bp.get("/products/<product_id>")
def product_detail(product_id: str):
    detail = get_product_detail(product_id)
    if not detail:
        return error(f"Product not found: {product_id}", status=404)
    return ok(detail)


@api_bp.get("/categories")
def categories():
    return ok(get_category_summary())


@api_bp.get("/hot-products")
def hot_products():
    limit = clamp_limit(request.args.get("limit"), default=10)
    return ok(get_hot_products(limit=limit))


@api_bp.get("/comments/sentiment")
def sentiment_summary():
    product_id = request.args.get("product_id")
    return ok(get_sentiment_summary(product_id=product_id))


@api_bp.get("/sales/trend")
def sales_trend():
    product_id = request.args.get("product_id")
    days = clamp_limit(request.args.get("days"), default=30, maximum=365)
    return ok(
        {
            "product_id": product_id,
            "days": days,
            "items": get_sales_trend(product_id=product_id, days=days),
        }
    )


@api_bp.get("/competitors")
def competitors():
    product_id = request.args.get("product_id")
    limit = clamp_limit(request.args.get("limit"), default=20)
    return ok(
        {
            "product_id": product_id,
            "items": get_competitors(product_id=product_id, limit=limit),
        }
    )


@api_bp.post("/competitors")
def create_competitor():
    payload = request.get_json(silent=True) or {}
    try:
        competitor = competitor_service.create_competitor(payload)
    except competitor_service.CompetitorError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    return ok(competitor, status=201)


@api_bp.get("/analysis/sales")
def sales_analysis():
    return ok(sales_analysis_service.get_sales_analysis())


@api_bp.get("/analysis/price-bands")
def price_bands():
    return ok(sales_analysis_service.get_price_band_analysis())


@api_bp.get("/hot-products/scoring")
def hot_product_scoring():
    limit = clamp_limit(request.args.get("limit"), default=20)
    product_id = request.args.get("product_id")
    data = hot_score_service.get_hot_scoring(limit=limit, product_id=product_id)
    if product_id and not data["items"]:
        return error(f"Product not found: {product_id}", status=404)
    return ok(data)


@api_bp.get("/scoring/models")
@require_permission("scoring.view")
def scoring_models():
    limit = clamp_limit(request.args.get("limit"), default=20, maximum=100)
    return ok(scoring_model_service.list_models(g.current_user, limit=limit))


@api_bp.post("/scoring/models")
@require_permission("scoring.manage")
def create_scoring_model():
    payload = request.get_json(silent=True) or {}
    try:
        model = scoring_model_service.create_model(payload, g.current_user)
    except scoring_model_service.ScoringModelError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="scoring.model.create",
        user=g.current_user,
        resource_type="scoring_model",
        resource_id=model["model_id"],
        metadata={"model_name": model["model_name"], "weights": model["weights"]},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(model, status=201)


@api_bp.get("/comments/keywords")
def comment_keywords():
    product_id = request.args.get("product_id")
    top_n = clamp_limit(request.args.get("top_n"), default=20, maximum=50)
    return ok(comment_nlp_service.get_comment_keywords(product_id=product_id, top_n=top_n))


@api_bp.get("/competitors/summary")
def competitor_summary():
    product_id = request.args.get("product_id")
    category = request.args.get("category")
    limit = clamp_limit(request.args.get("limit"), default=20)
    return ok(
        competitor_service.get_competitor_summary(
            product_id=product_id,
            category=category,
            limit=limit,
        )
    )


@api_bp.get("/reports/schedules")
@require_permission("reports.schedule")
def report_schedules():
    limit = clamp_limit(request.args.get("limit"), default=50, maximum=100)
    try:
        return ok(report_schedule_service.list_schedules(g.current_user, limit=limit))
    except report_schedule_service.ReportScheduleError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.post("/reports/schedules")
@require_permission("reports.schedule")
def create_report_schedule():
    payload = request.get_json(silent=True) or {}
    try:
        schedule = report_schedule_service.create_schedule(g.current_user, payload)
    except report_schedule_service.ReportScheduleError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="report.schedule.create",
        user=g.current_user,
        resource_type="report_schedule",
        resource_id=schedule["schedule_id"],
        metadata={
            "scope_type": schedule.get("scope_type"),
            "product_id": schedule.get("product_id"),
            "frequency": schedule.get("frequency"),
            "next_run_at": schedule.get("next_run_at"),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(schedule, status=201)


@api_bp.post("/reports/schedules/run-due")
@require_permission("reports.schedule")
def run_due_report_schedules():
    limit = clamp_limit(request.args.get("limit"), default=20, maximum=50)
    try:
        result = report_schedule_service.run_due_schedules(g.current_user, limit=limit)
    except report_schedule_service.ReportScheduleError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="report.schedule.run_due",
        user=g.current_user,
        resource_type="report_schedule",
        resource_id="due",
        metadata={
            "due_count": result.get("due_count"),
            "executed_count": result.get("executed_count"),
            "failed_count": result.get("failed_count"),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(result)


@api_bp.patch("/reports/schedules/<schedule_id>")
@require_permission("reports.schedule")
def update_report_schedule(schedule_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        schedule = report_schedule_service.update_schedule(g.current_user, schedule_id, payload)
    except report_schedule_service.ReportScheduleError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="report.schedule.update",
        user=g.current_user,
        resource_type="report_schedule",
        resource_id=schedule_id,
        metadata={"updated_fields": sorted(payload.keys()), "status": schedule.get("status")},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(schedule)


@api_bp.get("/reports/delivery/status")
@require_permission("reports.schedule")
def report_delivery_status():
    return ok(report_delivery_service.get_status())


@api_bp.get("/reports/schedules/<schedule_id>/deliveries")
@require_permission("reports.schedule")
def report_schedule_deliveries(schedule_id: str):
    limit = clamp_limit(request.args.get("limit"), default=20, maximum=100)
    try:
        schedule = report_schedule_service.get_schedule_for_actor(g.current_user, schedule_id)
        return ok(report_delivery_service.list_deliveries(g.current_user, schedule, limit=limit))
    except report_schedule_service.ReportScheduleError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/reports/delivery/retries")
@require_permission("reports.schedule")
def report_delivery_retries():
    limit = clamp_limit(request.args.get("limit"), default=50, maximum=100)
    try:
        return ok(report_delivery_service.list_retry_jobs(g.current_user, request.args.get("status"), limit=limit))
    except report_delivery_service.ReportDeliveryError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.post("/reports/delivery/retries/run-due")
@require_permission("reports.schedule")
def run_due_report_delivery_retries():
    limit = clamp_limit(request.args.get("limit"), default=20, maximum=100)
    result = report_delivery_service.run_due_retries(g.current_user, limit=limit)
    auth_service.audit(
        action="report.delivery.retry_due",
        user=g.current_user,
        resource_type="report_delivery_retry_job",
        resource_id="run-due",
        metadata={
            "due_count": result.get("due_count"),
            "processed_count": result.get("processed_count"),
            "succeeded_count": result.get("succeeded_count"),
            "exhausted_count": result.get("exhausted_count"),
            "cancelled_count": result.get("cancelled_count"),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(result)


@api_bp.post("/reports/deliveries/<delivery_id>/retry")
@require_permission("reports.schedule")
def retry_report_delivery(delivery_id: str):
    try:
        result = report_delivery_service.retry_delivery(g.current_user, delivery_id)
    except report_delivery_service.ReportDeliveryError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="report.delivery.retry",
        user=g.current_user,
        resource_type="report_delivery",
        resource_id=delivery_id,
        metadata={
            "new_delivery_id": result.get("delivery", {}).get("delivery_id"),
            "status": result.get("delivery", {}).get("status"),
            "reason": result.get("delivery", {}).get("reason"),
        },
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(result, status=201)


@api_bp.post("/reports/schedules/<schedule_id>/run")
@require_permission("reports.schedule")
def run_report_schedule(schedule_id: str):
    try:
        result = report_schedule_service.run_schedule(g.current_user, schedule_id)
    except report_schedule_service.ReportScheduleError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="report.schedule.run",
        user=g.current_user,
        resource_type="report_schedule",
        resource_id=schedule_id,
        metadata={"report_id": result.get("report", {}).get("report_id")},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(result, status=201)


@api_bp.delete("/reports/schedules/<schedule_id>")
@require_permission("reports.schedule")
def archive_report_schedule(schedule_id: str):
    try:
        schedule = report_schedule_service.archive_schedule(g.current_user, schedule_id)
    except report_schedule_service.ReportScheduleError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="report.schedule.archive",
        user=g.current_user,
        resource_type="report_schedule",
        resource_id=schedule_id,
        metadata={"status": schedule.get("status")},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(schedule)


@api_bp.get("/forecast/sales")
def forecast_sales():
    days = parse_horizon(request.args.get("days"))
    if days is None:
        return error("days must be one of 7, 14, or 30", status=400)
    return ok(
        forecast_service.get_sales_forecast(
            product_id=request.args.get("product_id"),
            category=request.args.get("category"),
            days=days,
        )
    )


@api_bp.post("/reports/generate")
@require_permission("reports.generate", strict=False)
def generate_report():
    payload = request.get_json(silent=True) or {}
    product_id = payload.get("product_id") or request.args.get("product_id")
    use_llm = _parse_bool(payload.get("use_llm"))
    if use_llm is None and "use_llm" in request.args:
        use_llm = _parse_bool(request.args.get("use_llm"))
    report = report_service.generate_report(product_id=product_id, use_llm=use_llm)
    if product_id and report is None:
        return error(f"Product not found: {product_id}", status=404)
    actor = getattr(g, "current_user", None)
    if actor:
        auth_service.audit(
            action="report.generate",
            user=actor,
            resource_type="report",
            resource_id=report["report_id"] if report else None,
            metadata={
                "product_id": product_id,
                "use_llm": use_llm,
                "ai_generation": report.get("ai_generation") if report else None,
            },
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        )
    return ok(report, status=201)


@api_bp.get("/reports/<report_id>")
@require_permission("reports.view", strict=False)
def report_detail(report_id: str):
    report = report_service.get_report(report_id)
    if not report:
        return error(f"Report not found: {report_id}", status=404)
    return ok(report)


@api_bp.post("/reports/<report_id>/shares")
@require_permission("reports.share")
def create_report_share(report_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        share = report_share_service.create_share(
            report_id=report_id,
            actor=g.current_user,
            expires_in_days=payload.get("expires_in_days"),
        )
    except report_share_service.ReportShareError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    if not share:
        return error(f"Report not found: {report_id}", status=404)
    share["share_url"] = _frontend_share_url(share["share_token"])
    auth_service.audit(
        action="report.share.create",
        user=g.current_user,
        resource_type="report_share",
        resource_id=share["share_id"],
        metadata={"report_id": report_id, "expires_at": share["expires_at"]},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(share, status=201)


@api_bp.get("/reports/<report_id>/shares")
@require_permission("reports.share")
def report_shares(report_id: str):
    shares = report_share_service.list_shares(report_id, g.current_user)
    if shares is None:
        return error(f"Report not found: {report_id}", status=404)
    return ok(shares)


@api_bp.get("/reports/shares/<share_id>/access-logs")
@require_permission("reports.share")
def report_share_access_logs(share_id: str):
    page, page_size = parse_pagination(request.args)
    try:
        return ok(report_share_service.list_share_access_logs(share_id, g.current_user, page=page, page_size=page_size))
    except report_share_service.ReportShareError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.delete("/reports/shares/<share_id>")
@require_permission("reports.share")
def revoke_report_share(share_id: str):
    try:
        share = report_share_service.revoke_share(share_id, g.current_user)
    except report_share_service.ReportShareError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))
    auth_service.audit(
        action="report.share.revoke",
        user=g.current_user,
        resource_type="report_share",
        resource_id=share_id,
        metadata={"report_id": share.get("report_id")},
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    return ok(share)


@api_bp.get("/reports/shared/<share_token>")
def shared_report(share_token: str):
    try:
        return ok(
            report_share_service.get_shared_report(
                share_token,
                access_context={
                    "ip_address": _client_ip(),
                    "user_agent": request.headers.get("User-Agent"),
                    "referrer": request.headers.get("Referer"),
                },
            )
        )
    except report_share_service.ReportShareError as exc:
        return error(str(exc), status=getattr(exc, "status_code", 400))


@api_bp.get("/reports/<report_id>/export")
@require_permission("reports.export", strict=False)
def export_report(report_id: str):
    export_format = request.args.get("format", "docx")
    try:
        exported = report_export_service.export_report(report_id, export_format)
    except report_export_service.ReportExportError as exc:
        return error(str(exc), status=400)
    if not exported:
        return error(f"Report not found: {report_id}", status=404)

    actor = getattr(g, "current_user", None)
    if actor:
        auth_service.audit(
            action="report.export",
            user=actor,
            resource_type="report",
            resource_id=report_id,
            metadata={"format": exported.format},
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        )
    return send_file(
        BytesIO(exported.content),
        mimetype=exported.mimetype,
        as_attachment=True,
        download_name=exported.filename,
        max_age=0,
    )


def _parse_bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _frontend_share_url(share_token: str) -> str:
    base = request.host_url.rstrip("/")
    return f"{base}/#shared-report={share_token}"


def _frontend_invite_url(invite_token: str) -> str:
    base = request.host_url.rstrip("/")
    return f"{base}/#invite={invite_token}"


def _client_ip() -> str:
    forwarded = str(request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or ""
