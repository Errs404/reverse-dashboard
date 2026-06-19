from __future__ import annotations

import time
from functools import wraps

from flask import jsonify, redirect, request, session, url_for

from .extensions import audit_service, auth_service


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        cfg = auth_service().load()
        if not cfg.get("setup_complete") and request.endpoint != "auth.setup" and not request.path.startswith("/static"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Setup required"}), 428
            return redirect(url_for("auth.setup"))
        if not session.get("logged_in"):
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login"))
        timeout = int(cfg.get("session_timeout", 3600) or 0)
        login_time = float(session.get("login_time", 0) or 0)
        if timeout > 0 and login_time > 0 and time.time() - login_time > timeout:
            user = session.get("username", "unknown")
            session.clear()
            audit_service().log("SESSION_TIMEOUT", user, request.remote_addr or "unknown")
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Session expired"}), 401
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)
    return wrapper


def permission_required(feature: str, level: str = "view"):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            role = session.get("role", "readonly")
            if not auth_service().has_permission(role, feature, level):
                audit_service().log("PERMISSION_DENIED", session.get("username", "unknown"), request.remote_addr or "unknown", f"{feature}:{level}")
                if request.path.startswith("/api/") or request.is_json:
                    return jsonify({"error": "Permission denied"}), 403
                return redirect(url_for("pages.dashboard"))
            return func(*args, **kwargs)
        return wrapper
    return decorator
