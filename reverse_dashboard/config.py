from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("REVERSE_DASHBOARD_DATA", BASE_DIR / "data")).resolve()


def env_bool(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on", "y"}


class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    DATA_DIR = DATA_DIR
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 512 * 1024 * 1024))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    JSON_SORT_KEYS = False
    DASHBOARD_NAME = os.environ.get("DASHBOARD_NAME", "Reverse Dashboard")
    VERSION = "2.0.0-alpha.1"

    # Host access root. In Docker this should point to the mounted host root.
    HOST_ROOT = Path(os.environ.get("HOST_ROOT", "/")).resolve()
    FILES_READ_ONLY = env_bool("FILES_READ_ONLY", "0")

    # Explicitly allow dangerous host-control APIs only when enabled.
    ENABLE_HOST_CONTROL = env_bool("ENABLE_HOST_CONTROL", "0")
    ENABLE_DOCKER = env_bool("ENABLE_DOCKER", "1")
    ENABLE_DATABASE = env_bool("ENABLE_DATABASE", "1")
    ENABLE_PM2 = env_bool("ENABLE_PM2", "1")
    ENABLE_NGINX = env_bool("ENABLE_NGINX", "1")
    ENABLE_BACKUP = env_bool("ENABLE_BACKUP", "1")
    ENABLE_TERMINAL = env_bool("ENABLE_TERMINAL", "1")
    ENABLE_GDRIVE_BACKUP = env_bool("ENABLE_GDRIVE_BACKUP", "1")
    GDRIVE_REMOTE = os.environ.get("GDRIVE_REMOTE", "")
    LETSENCRYPT_EMAIL = os.environ.get("LETSENCRYPT_EMAIL", "")
    LETSENCRYPT_STAGING = env_bool("LETSENCRYPT_STAGING", "0")
    ALLOW_RUNTIME_INSTALL = env_bool("ALLOW_RUNTIME_INSTALL", "0")
    BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", DATA_DIR / "backups")).resolve()
