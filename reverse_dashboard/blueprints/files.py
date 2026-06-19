from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, session

from ..extensions import audit_service, file_service
from ..security import permission_required

bp = Blueprint("files", __name__)


def writes_enabled() -> bool:
    return not current_app.config.get("FILES_READ_ONLY", False)


@bp.get("/list")
@permission_required("files", "read")
def list_files():
    try:
        return jsonify(file_service().list_dir(
            request.args.get("path", "/"),
            page=request.args.get("page", 1, type=int),
            per_page=request.args.get("per_page", 80, type=int),
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/content")
@permission_required("files", "read")
def read_content():
    try:
        return jsonify(file_service().read_text(request.args.get("path", "")))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/content")
@permission_required("files", "full")
def write_content():
    if not writes_enabled():
        return jsonify({"error": "File browser berjalan dalam mode read-only"}), 403
    data = request.get_json(silent=True) or {}
    try:
        file_service().write_text(data.get("path", ""), data.get("content", ""))
        audit_service().log("FILE_WRITE", session.get("username", "unknown"), request.remote_addr or "unknown", data.get("path", ""))
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/action")
@permission_required("files", "full")
def action():
    if not writes_enabled():
        return jsonify({"error": "File browser berjalan dalam mode read-only"}), 403
    data = request.get_json(silent=True) or {}
    try:
        kwargs = {k: v for k, v in data.items() if k not in {"action", "path"}}
        file_service().mutate(data.get("action", ""), data.get("path", ""), **kwargs)
        audit_service().log("FILE_ACTION", session.get("username", "unknown"), request.remote_addr or "unknown", f"{data.get('action')} {data.get('path')}")
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
