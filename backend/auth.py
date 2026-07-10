from __future__ import annotations

from functools import wraps

from flask import current_app, g, request

from backend.permissions import has_permission
from backend.services import auth_service
from backend.utils.response import error


def attach_current_user() -> None:
    g.current_user = auth_service.authenticate_bearer(request.headers.get("Authorization"))


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "current_user", None):
            return view(*args, **kwargs)
        if not current_app.config.get("AUTH_REQUIRED", False):
            return view(*args, **kwargs)
        return error("Authentication required", status=401)

    return wrapped


def strict_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "current_user", None):
            return view(*args, **kwargs)
        return error("Authentication required", status=401)

    return wrapped


def require_permission(permission: str, strict: bool = True):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if user:
                if has_permission(user, permission):
                    return view(*args, **kwargs)
                return error("Permission denied", status=403)
            if not strict and not current_app.config.get("AUTH_REQUIRED", False):
                return view(*args, **kwargs)
            return error("Authentication required", status=401)

        return wrapped

    return decorator
