from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, session

from ..extensions import audit_service, docker_service
from ..security import permission_required

bp = Blueprint("docker", __name__)


def docker_enabled():
    return current_app.config.get("ENABLE_DOCKER", True)


@bp.get("/status")
@permission_required("docker", "view")
def status():
    diag = docker_service().diagnostics() if docker_enabled() else {"available": False, "reason": "Docker feature disabled", "fix": "Set ENABLE_DOCKER=1"}
    return jsonify({"enabled": docker_enabled(), **diag})


@bp.get("/containers")
@permission_required("docker", "view")
def containers():
    if not docker_enabled():
        return jsonify({"error": "Docker feature disabled"}), 403
    try:
        return jsonify({"containers": docker_service().containers()})
    except Exception as exc:
        return jsonify({"error": str(exc), "containers": []}), 500


@bp.get("/containers/<container_id>/stats")
@permission_required("docker", "view")
def stats(container_id: str):
    try:
        return jsonify(docker_service().stats(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/containers/<container_id>/action")
@permission_required("docker", "restart")
def action(container_id: str):
    data = request.get_json(silent=True) or {}
    action_name = data.get("action", "")
    if session.get("role") == "operator" and action_name != "restart":
        return jsonify({"error": "Operator hanya boleh restart container"}), 403
    try:
        docker_service().action(container_id, action_name)
        audit_service().log("DOCKER_ACTION", session.get("username", "unknown"), request.remote_addr or "unknown", f"{action_name} {container_id}")
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/containers/<container_id>/logs")
@permission_required("docker", "view")
def logs(container_id: str):
    lines = request.args.get("lines", 300, type=int)
    try:
        return jsonify({"logs": docker_service().logs(container_id, max(1, min(lines, 2000)))})
    except Exception as exc:
        return jsonify({"error": str(exc), "logs": ""}), 500
