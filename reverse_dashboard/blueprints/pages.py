from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for

from ..security import login_required, permission_required

bp = Blueprint("pages", __name__)


@bp.get("/")
def home():
    return redirect(url_for("pages.dashboard"))


@bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", active="dashboard")


@bp.get("/files")
@permission_required("files", "read")
def files():
    return render_template("files.html", active="files")


@bp.get("/docker")
@permission_required("docker", "view")
def docker_page():
    return render_template("docker.html", active="docker")


@bp.get("/network")
@permission_required("network", "view")
def network_page():
    return render_template("network.html", active="network")


@bp.get("/storage")
@permission_required("storage", "view")
def storage_page():
    return render_template("storage.html", active="storage")


@bp.get("/database")
@permission_required("database", "view")
def database_page():
    return render_template("database.html", active="database")


@bp.get("/security")
@permission_required("security", "view")
def security_page():
    return render_template("security.html", active="security")


@bp.get("/pm2")
@permission_required("pm2", "view")
def pm2_page():
    return render_template("pm2.html", active="pm2")


@bp.get("/nginx")
@permission_required("nginx", "view")
def nginx_page():
    return render_template("nginx.html", active="nginx")


@bp.get("/backup")
@permission_required("backup", "view")
def backup_page():
    return render_template("backup.html", active="backup")


@bp.get("/terminal")
@permission_required("terminal", "full")
def terminal_page():
    return render_template("terminal.html", active="terminal", fullscreen_layout=True)


@bp.get("/settings")
@permission_required("settings", "view")
def settings_page():
    return render_template("settings.html", active="settings")


@bp.get("/audit")
@permission_required("settings", "view")
def audit_page():
    return render_template("audit.html", active="audit")
