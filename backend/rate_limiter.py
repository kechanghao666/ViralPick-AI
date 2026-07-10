from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

from flask import Request


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    bucket: str
    limit: int
    remaining: int
    retry_after: int
    window_seconds: int


_LOCK = threading.Lock()
_REQUESTS: dict[str, Deque[float]] = {}


def check_request(app, request: Request, user: dict | None = None) -> RateLimitResult | None:
    if request.method == "OPTIONS" or not request.path.startswith("/api/"):
        return None
    if not app.config.get("RATE_LIMIT_ENABLED", False):
        return None

    bucket = _bucket_for(request)
    limit = _limit_for(app, bucket)
    window_seconds = int(app.config.get("RATE_LIMIT_WINDOW_SECONDS", 60))
    if limit <= 0 or window_seconds <= 0:
        return None

    now = time.monotonic()
    key = f"{bucket}:{_identity_for(request, user)}:{request.endpoint or request.path}"
    cutoff = now - window_seconds

    with _LOCK:
        timestamps = _REQUESTS.setdefault(key, deque())
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        if len(timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])) + 1)
            return RateLimitResult(
                allowed=False,
                bucket=bucket,
                limit=limit,
                remaining=0,
                retry_after=retry_after,
                window_seconds=window_seconds,
            )

        timestamps.append(now)
        return RateLimitResult(
            allowed=True,
            bucket=bucket,
            limit=limit,
            remaining=max(0, limit - len(timestamps)),
            retry_after=0,
            window_seconds=window_seconds,
        )


def reset_rate_limits() -> None:
    with _LOCK:
        _REQUESTS.clear()


def _bucket_for(request: Request) -> str:
    if request.path == "/api/auth/login":
        return "auth"
    if request.method in {"POST", "PATCH", "DELETE"}:
        return "write"
    return "default"


def _limit_for(app, bucket: str) -> int:
    if bucket == "auth":
        return int(app.config.get("RATE_LIMIT_AUTH_PER_WINDOW", 20))
    if bucket == "write":
        return int(app.config.get("RATE_LIMIT_WRITE_PER_WINDOW", 120))
    return int(app.config.get("RATE_LIMIT_DEFAULT_PER_WINDOW", 300))


def _identity_for(request: Request, user: dict | None) -> str:
    if user and user.get("user_id"):
        return f"user:{user['user_id']}"
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded.split(",", 1)[0].strip() if forwarded else request.remote_addr
    return f"ip:{client_ip or 'unknown'}"
