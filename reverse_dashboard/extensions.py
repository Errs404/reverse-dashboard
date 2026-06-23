from __future__ import annotations

from flask import current_app, g, session

from .services.audit_service import AuditService
from .services.auth_service import AuthService
from .services.docker_service import DockerService
from .services.database_service import DatabaseService
from .services.file_service import FileService
from .services.json_store import JsonStore
from .services.settings_service import SettingsService
from .services.system_service import SystemService
from .services.runtime_service import BackupService, FirewallService, NginxService, PM2Service, ServiceManager, TerminalService


def store() -> JsonStore:
    if "json_store" not in g:
        g.json_store = JsonStore(current_app.config["DATA_DIR"])
    return g.json_store


def auth_service() -> AuthService:
    if "auth_service" not in g:
        g.auth_service = AuthService(store())
    return g.auth_service


def audit_service() -> AuditService:
    if "audit_service" not in g:
        g.audit_service = AuditService(current_app.config["DATA_DIR"])
    return g.audit_service


def system_service() -> SystemService:
    if "system_service" not in g:
        g.system_service = SystemService()
    return g.system_service


def file_service() -> FileService:
    if "file_service" not in g:
        g.file_service = FileService(current_app.config["HOST_ROOT"])
    return g.file_service


def docker_service() -> DockerService:
    if "docker_service" not in g:
        g.docker_service = DockerService()
    return g.docker_service


def database_service() -> DatabaseService:
    if "database_service" not in g:
        g.database_service = DatabaseService(current_app.config["ENABLE_DATABASE"], current_app.config["ENABLE_HOST_CONTROL"], current_app.config["DATA_DIR"])
    return g.database_service


def settings_service() -> SettingsService:
    if "settings_service" not in g:
        g.settings_service = SettingsService(store())
    return g.settings_service


def pm2_service() -> PM2Service:
    if "pm2_service" not in g:
        g.pm2_service = PM2Service(current_app.config["ENABLE_PM2"], current_app.config["ALLOW_RUNTIME_INSTALL"], current_app.config["ENABLE_HOST_CONTROL"], current_app.config["BASE_DIR"])
    return g.pm2_service


def nginx_service() -> NginxService:
    if "nginx_service" not in g:
        g.nginx_service = NginxService(current_app.config["ENABLE_NGINX"], current_app.config["ALLOW_RUNTIME_INSTALL"], current_app.config["ENABLE_HOST_CONTROL"], current_app.config["BASE_DIR"], current_app.config["LETSENCRYPT_EMAIL"], current_app.config["LETSENCRYPT_STAGING"])
    return g.nginx_service


def service_manager() -> ServiceManager:
    if "service_manager" not in g:
        g.service_manager = ServiceManager(current_app.config["ENABLE_HOST_CONTROL"])
    return g.service_manager


def backup_service() -> BackupService:
    if "backup_service" not in g:
        backup_settings = settings_service().load().get("backup", {})
        gdrive_enabled = current_app.config["ENABLE_GDRIVE_BACKUP"] and bool(backup_settings.get("gdrive_enabled", True))
        gdrive_remote = str(backup_settings.get("gdrive_remote") or current_app.config["GDRIVE_REMOTE"] or "")
        g.backup_service = BackupService(current_app.config["DATA_DIR"], current_app.config["BACKUP_DIR"], current_app.config["ENABLE_BACKUP"], gdrive_enabled, gdrive_remote)
    return g.backup_service


def firewall_service() -> FirewallService:
    if "firewall_service" not in g:
        g.firewall_service = FirewallService(current_app.config["ENABLE_HOST_CONTROL"])
    return g.firewall_service


def terminal_service() -> TerminalService:
    if "terminal_service" not in g:
        g.terminal_service = TerminalService(current_app.config["ENABLE_TERMINAL"], current_app.config["ENABLE_HOST_CONTROL"], current_app.config["HOST_ROOT"])
    return g.terminal_service


def current_user() -> dict | None:
    if not session.get("logged_in"):
        return None
    return {"username": session.get("username"), "role": session.get("role", "readonly")}
