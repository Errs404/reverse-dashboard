from __future__ import annotations

import time

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from ..extensions import audit_service, auth_service
from ..security import login_required

bp = Blueprint("auth", __name__)


@bp.get("/setup")
def setup():
    if auth_service().load().get("setup_complete"):
        return redirect(url_for("auth.login"))
    return render_template("setup.html")


@bp.post("/api/setup")
def setup_api():
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service().setup_owner(data.get("username", ""), data.get("password", ""))
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    session.clear()
    session.update({
        "logged_in": True,
        "username": user.username,
        "role": user.role,
        "login_time": time.time(),
    })
    audit_service().log("SETUP_OWNER", user.username, request.remote_addr or "unknown")
    return jsonify({"success": True})


@bp.get("/login")
def login():
    if not auth_service().load().get("setup_complete"):
        return redirect(url_for("auth.setup"))
    if session.get("logged_in"):
        return redirect(url_for("pages.dashboard"))
    return render_template("login.html")


@bp.post("/api/login")
def login_api():
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service().authenticate(data.get("username", ""), data.get("password", ""), request.remote_addr or "unknown")
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 429
    if not user:
        audit_service().log("LOGIN_FAILED", data.get("username", "unknown"), request.remote_addr or "unknown")
        return jsonify({"error": "Username atau password salah"}), 401

    session.clear()
    session.update({
        "logged_in": True,
        "username": user.username,
        "role": user.role,
        "login_time": time.time(),
    })
    audit_service().log("LOGIN_SUCCESS", user.username, request.remote_addr or "unknown")
    return jsonify({"success": True, "role": user.role})


@bp.post("/api/logout")
@login_required
def logout_api():
    user = session.get("username", "unknown")
    session.clear()
    audit_service().log("LOGOUT", user, request.remote_addr or "unknown")
    return jsonify({"success": True})


@bp.get("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("auth.login"))
