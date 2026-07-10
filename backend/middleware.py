from __future__ import annotations

import time
from uuid import uuid4

from flask import Flask, g, request

from backend.auth import attach_current_user
from backend.config import cors_origins
from backend.rate_limiter import check_request
from backend.utils.response import error


def register_request_middleware(app: Flask) -> None:
    @app.before_request
    def attach_request_context():
        g.request_id = request.headers.get("X-Request-ID") or uuid4().hex
        g.request_started_at = time.perf_counter()
        attach_current_user()
        rate_limit = check_request(app, request, getattr(g, "current_user", None))
        if rate_limit:
            g.rate_limit = rate_limit
            if not rate_limit.allowed:
                response, status = error("Too many requests. Please retry later.", status=429)
                response.status_code = status
                return response

    @app.after_request
    def add_operational_headers(response):
        request_id = getattr(g, "request_id", uuid4().hex)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        origins = cors_origins()
        origin = request.headers.get("Origin")
        if "*" in origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Request-ID"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"

        rate_limit = getattr(g, "rate_limit", None)
        if rate_limit:
            response.headers["X-RateLimit-Bucket"] = rate_limit.bucket
            response.headers["X-RateLimit-Limit"] = str(rate_limit.limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit.remaining)
            response.headers["X-RateLimit-Window"] = str(rate_limit.window_seconds)
            if not rate_limit.allowed:
                response.headers["Retry-After"] = str(rate_limit.retry_after)

        duration_ms = int((time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())) * 1000)
        app.logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )
        return response
