from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file, session

from ..extensions import audit_service, auth_service, backup_service, database_service, firewall_service, nginx_service, pm2_service, system_service, terminal_service
from ..security import login_required, permission_required

bp = Blueprint("api", __name__)


@bp.get("/health")
def health():
    return jsonify({"ok": True})


@bp.get("/me")
@login_required
def me():
    return jsonify({"username": session.get("username"), "role": session.get("role")})


@bp.get("/system")
@login_required
def system_info():
    return jsonify(system_service().info())


@bp.get("/stats")
@login_required
def stats():
    return jsonify(system_service().summary())


@bp.get("/processes")
@login_required
def processes():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"processes": system_service().processes(limit=max(1, min(limit, 200)))})


@bp.get("/disks")
@login_required
def disks():
    return jsonify({"disks": system_service().disks()})


@bp.get("/network")
@permission_required("network", "view")
def network():
    return jsonify(system_service().network())


@bp.get("/network/firewall")
@permission_required("network", "view")
def firewall_status():
    return jsonify(firewall_service().status())


@bp.post("/network/open-port")
@permission_required("network", "full")
def open_port():
    data = request.get_json(silent=True) or {}
    try:
        result = firewall_service().open_port(int(data.get("port", 0)), str(data.get("protocol", "tcp")))
        audit_service().log("OPEN_PORT", session.get("username", "unknown"), request.remote_addr or "unknown", f"{data.get('port')}/{data.get('protocol', 'tcp')}")
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/storage")
@permission_required("storage", "view")
def storage():
    return jsonify(system_service().storage())


@bp.get("/security/summary")
@permission_required("security", "view")
def security_summary():
    return jsonify(system_service().security_summary(auth_service().load()))


@bp.get("/database/status")
@permission_required("database", "view")
def database_status():
    return jsonify(database_service().status())


@bp.post("/database/action")
@permission_required("database", "full")
def database_action():
    data = request.get_json(silent=True) or {}
    service = str(data.get("service", ""))
    action = str(data.get("action", ""))
    try:
        result = database_service().action(service, action)
        audit_service().log("DATABASE_ACTION", session.get("username", "unknown"), request.remote_addr or "unknown", f"{action} {service}")
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/database/list")
@permission_required("database", "view")
def database_list():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(database_service().list_databases(data))
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/database/create")
@permission_required("database", "full")
def database_create():
    data = request.get_json(silent=True) or {}
    try:
        result = database_service().create_database(data)
        audit_service().log("DATABASE_CREATE", session.get("username", "unknown"), request.remote_addr or "unknown", f"{data.get('engine')} {data.get('database')}")
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/database/user")
@permission_required("database", "full")
def database_user():
    data = request.get_json(silent=True) or {}
    try:
        result = database_service().create_user(data)
        audit_service().log("DATABASE_USER_CREATE", session.get("username", "unknown"), request.remote_addr or "unknown", f"{data.get('engine')} {data.get('new_username')}")
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/database/import")
@permission_required("database", "full")
def database_import():
    upload = request.files.get("file")
    if not upload:
        return jsonify({"error": "File SQL wajib diupload"}), 400
    try:
        result = database_service().import_database(request.form.to_dict(), upload.filename or "import.sql", upload.stream)
        audit_service().log("DATABASE_IMPORT", session.get("username", "unknown"), request.remote_addr or "unknown", f"{request.form.get('engine')} {request.form.get('database')}")
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/database/export")
@permission_required("database", "view")
def database_export():
    data = request.get_json(silent=True) or {}
    try:
        path = database_service().export_database(data)
        audit_service().log("DATABASE_EXPORT", session.get("username", "unknown"), request.remote_addr or "unknown", f"{data.get('engine')} {data.get('database')}")
        return send_file(path, as_attachment=True, download_name=path.name)
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/audit")
@permission_required("settings", "view")
def audit_logs():
    lines = request.args.get("lines", 200, type=int)
    return jsonify({"logs": audit_service().tail(max(1, min(lines, 1000)))})


@bp.get("/users")
@permission_required("users", "limited")
def users():
    return jsonify({"users": auth_service().list_users()})


@bp.post("/users")
@permission_required("users", "limited")
def add_user():
    data = request.get_json(silent=True) or {}
    try:
        auth_service().add_user(data.get("username", ""), data.get("password", ""), data.get("role", "readonly"))
        audit_service().log("USER_CREATED", session.get("username", "unknown"), request.remote_addr or "unknown", data.get("username", ""))
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/pm2/status")
@permission_required("pm2", "view")
def pm2_status():
    return jsonify(pm2_service().status())


@bp.get("/pm2/processes")
@permission_required("pm2", "view")
def pm2_processes():
    return jsonify({"processes": pm2_service().processes()})


@bp.post("/pm2/action")
@permission_required("pm2", "restart")
def pm2_action():
    data = request.get_json(silent=True) or {}
    try:
        result = pm2_service().action(str(data.get("name", "")), str(data.get("action", "restart")))
        audit_service().log("PM2_ACTION", session.get("username", "unknown"), request.remote_addr or "unknown", f"{data.get('action')} {data.get('name')}")
        return jsonify(result)
    except (ValueError, PermissionError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/pm2/install")
@permission_required("pm2", "full")
def pm2_install():
    result = pm2_service().install()
    audit_service().log("PM2_INSTALL", session.get("username", "unknown"), request.remote_addr or "unknown", str(result.get("code")))
    return jsonify(result)


@bp.get("/nginx/status")
@permission_required("nginx", "view")
def nginx_status():
    return jsonify(nginx_service().status())


@bp.get("/nginx/test")
@permission_required("nginx", "view")
def nginx_test():
    return jsonify(nginx_service().test_config())


@bp.post("/nginx/action")
@permission_required("nginx", "restart")
def nginx_action():
    data = request.get_json(silent=True) or {}
    try:
        result = nginx_service().action(str(data.get("action", "reload")))
        audit_service().log("NGINX_ACTION", session.get("username", "unknown"), request.remote_addr or "unknown", str(data.get("action")))
        return jsonify(result)
    except (ValueError, PermissionError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/nginx/install")
@permission_required("nginx", "full")
def nginx_install():
    result = nginx_service().install()
    audit_service().log("NGINX_INSTALL", session.get("username", "unknown"), request.remote_addr or "unknown", str(result.get("code")))
    return jsonify(result)


@bp.get("/nginx/sites")
@permission_required("nginx", "view")
def nginx_sites():
    return jsonify({"sites": nginx_service().list_sites()})


@bp.get("/nginx/sites/<name>")
@permission_required("nginx", "view")
def nginx_site(name: str):
    try:
        return jsonify(nginx_service().get_site(name))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 404


@bp.post("/nginx/sites")
@permission_required("nginx", "full")
def nginx_site_save():
    data = request.get_json(silent=True) or {}
    try:
        result = nginx_service().save_site(str(data.get("name", "")), str(data.get("content", "")), bool(data.get("enable", True)))
        audit_service().log("NGINX_SITE_SAVE", session.get("username", "unknown"), request.remote_addr or "unknown", str(data.get("name", "")))
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/nginx/sites/proxy")
@permission_required("nginx", "full")
def nginx_site_proxy():
    data = request.get_json(silent=True) or {}
    try:
        result = nginx_service().create_proxy_site(str(data.get("domain", "")), str(data.get("upstream", "")), str(data.get("root", "")), bool(data.get("ssl_redirect", False)))
        audit_service().log("NGINX_SITE_CREATE_PROXY", session.get("username", "unknown"), request.remote_addr or "unknown", f"{data.get('domain')} -> {data.get('upstream')}")
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/nginx/sites/<name>/action")
@permission_required("nginx", "full")
def nginx_site_action(name: str):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", ""))
    try:
        if action == "enable":
            result = nginx_service().enable_site(name)
        elif action == "disable":
            result = nginx_service().disable_site(name)
        elif action == "delete":
            result = nginx_service().delete_site(name)
        else:
            return jsonify({"error": "Action site tidak valid"}), 400
        audit_service().log("NGINX_SITE_ACTION", session.get("username", "unknown"), request.remote_addr or "unknown", f"{action} {name}")
        return jsonify(result)
    except (ValueError, PermissionError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/nginx/ssl")
@permission_required("nginx", "full")
def nginx_ssl():
    data = request.get_json(silent=True) or {}
    domain = str(data.get("domain", ""))
    try:
        result = nginx_service().issue_ssl(domain)
        audit_service().log("NGINX_SSL", session.get("username", "unknown"), request.remote_addr or "unknown", domain)
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/backup/status")
@permission_required("backup", "view")
def backup_status():
    return jsonify(backup_service().status())


@bp.get("/backup/list")
@permission_required("backup", "view")
def backup_list():
    return jsonify({"backups": backup_service().list_backups()})


@bp.post("/backup/create")
@permission_required("backup", "full")
def backup_create():
    try:
        result = backup_service().create()
        audit_service().log("BACKUP_CREATED", session.get("username", "unknown"), request.remote_addr or "unknown", result.get("name", ""))
        return jsonify(result)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/backup/download/<name>")
@permission_required("backup", "view")
def backup_download(name: str):
    try:
        path = backup_service().path_for(name)
        return send_file(path, as_attachment=True, download_name=path.name)
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 404


@bp.post("/backup/gdrive/<name>")
@permission_required("backup", "full")
def backup_gdrive_upload(name: str):
    try:
        result = backup_service().upload_gdrive(name)
        audit_service().log("BACKUP_GDRIVE_UPLOAD", session.get("username", "unknown"), request.remote_addr or "unknown", name)
        return jsonify(result)
    except (ValueError, PermissionError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/terminal/status")
@permission_required("terminal", "full")
def terminal_status():
    return jsonify(terminal_service().status())


@bp.post("/terminal/run")
@permission_required("terminal", "full")
def terminal_run():
    data = request.get_json(silent=True) or {}
    command = str(data.get("command", ""))
    try:
        result = terminal_service().run(command, int(data.get("timeout", 20) or 20))
        audit_service().log("TERMINAL_COMMAND", session.get("username", "unknown"), request.remote_addr or "unknown", command)
        return jsonify(result)
    except (ValueError, PermissionError) as exc:
        audit_service().log("TERMINAL_DENIED", session.get("username", "unknown"), request.remote_addr or "unknown", command)
        return jsonify({"error": str(exc)}), 400
