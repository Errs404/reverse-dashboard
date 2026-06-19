from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("REVERSE_DASHBOARD_DATA", BASE_DIR / "data")).resolve()


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
    FILES_READ_ONLY = os.environ.get("FILES_READ_ONLY", "0") == "1"

    # Explicitly allow dangerous host-control APIs only when enabled.
    ENABLE_HOST_CONTROL = os.environ.get("ENABLE_HOST_CONTROL", "0") == "1"
    ENABLE_DOCKER = os.environ.get("ENABLE_DOCKER", "1") == "1"
    ENABLE_PM2 = os.environ.get("ENABLE_PM2", "1") == "1"
    ENABLE_NGINX = os.environ.get("ENABLE_NGINX", "1") == "1"
    ENABLE_BACKUP = os.environ.get("ENABLE_BACKUP", "1") == "1"
    ENABLE_TERMINAL = os.environ.get("ENABLE_TERMINAL", "1") == "1"
    ENABLE_GDRIVE_BACKUP = os.environ.get("ENABLE_GDRIVE_BACKUP", "1") == "1"
    GDRIVE_REMOTE = os.environ.get("GDRIVE_REMOTE", "")
    ALLOW_RUNTIME_INSTALL = os.environ.get("ALLOW_RUNTIME_INSTALL", "0") == "1"
    BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", DATA_DIR / "backups")).resolve()
