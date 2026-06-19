from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from ..extensions import audit_service, settings_service
from ..security import permission_required

bp = Blueprint("settings", __name__)


@bp.get("")
@permission_required("settings", "view")
def get_settings():
    return jsonify(settings_service().load())


@bp.post("")
@permission_required("settings", "full")
def update_settings():
    data = request.get_json(silent=True) or {}
    settings = settings_service().save(data)
    audit_service().log("SETTINGS_UPDATE", session.get("username", "unknown"), request.remote_addr or "unknown")
    return jsonify({"success": True, "settings": settings})


@bp.post("/reset")
@permission_required("settings", "full")
def reset_settings():
    settings = settings_service().reset()
    audit_service().log("SETTINGS_RESET", session.get("username", "unknown"), request.remote_addr or "unknown")
    return jsonify({"success": True, "settings": settings})
