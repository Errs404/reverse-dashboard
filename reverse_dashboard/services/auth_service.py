from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from .json_store import JsonStore

SECURITY_FILE = "security.json"

ROLES = ("owner", "admin", "operator", "readonly")
PERMISSIONS = {
    "owner": {"*": "full"},
    "admin": {
        "dashboard": "view",
        "metrics": "view",
        "files": "full",
        "docker": "full",
        "database": "full",
        "network": "full",
        "storage": "view",
        "security": "view",
        "pm2": "full",
        "nginx": "full",
        "backup": "full",
        "terminal": "full",
        "settings": "full",
        "users": "limited",
    },
    "operator": {
        "dashboard": "view",
        "metrics": "view",
        "files": "read",
        "docker": "restart",
        "database": "view",
        "network": "view",
        "storage": "view",
        "pm2": "restart",
        "nginx": "view",
        "backup": "view",
        "settings": "view",
    },
    "readonly": {
        "dashboard": "view",
        "metrics": "view",
        "files": "read",
        "docker": "view",
        "database": "view",
        "network": "view",
        "storage": "view",
        "pm2": "view",
        "nginx": "view",
        "backup": "view",
        "settings": "view",
    },
}


@dataclass(frozen=True)
class User:
    username: str
    role: str


class AuthService:
    def __init__(self, store: JsonStore):
        self.store = store

    def default_config(self) -> dict[str, Any]:
        return {
            "setup_complete": False,
            "users": [],
            "session_timeout": 3600,
            "login_attempts": {},
            "max_login_attempts": 5,
            "lockout_seconds": 300,
        }

    def load(self) -> dict[str, Any]:
        cfg = self.store.read(SECURITY_FILE, self.default_config())
        merged = self.default_config()
        merged.update(cfg if isinstance(cfg, dict) else {})
        return merged

    def save(self, cfg: dict[str, Any]) -> None:
        self.store.write(SECURITY_FILE, cfg)

    def setup_owner(self, username: str, password: str) -> User:
        username = username.strip()
        if not username or len(password) < 8:
            raise ValueError("Username wajib diisi dan password minimal 8 karakter")
        cfg = self.load()
        if cfg.get("setup_complete"):
            raise PermissionError("Setup sudah selesai")
        cfg["setup_complete"] = True
        cfg["users"] = [self._new_user(username, password, "owner")]
        self.save(cfg)
        return User(username=username, role="owner")

    def authenticate(self, username: str, password: str, ip: str = "unknown") -> User | None:
        cfg = self.load()
        if self._is_locked(cfg, ip):
            raise PermissionError("Terlalu banyak percobaan login. Coba lagi nanti.")

        for user in cfg.get("users", []):
            if hmac.compare_digest(user.get("username", ""), username) and check_password_hash(user.get("password_hash", ""), password):
                self._record_attempt(cfg, ip, True)
                self.save(cfg)
                return User(username=user["username"], role=user.get("role", "readonly"))

        self._record_attempt(cfg, ip, False)
        self.save(cfg)
        return None

    def list_users(self) -> list[dict[str, str]]:
        cfg = self.load()
        return [{"username": u.get("username", ""), "role": u.get("role", "readonly")} for u in cfg.get("users", [])]

    def add_user(self, username: str, password: str, role: str) -> None:
        if role not in ROLES or role == "owner":
            raise ValueError("Role tidak valid")
        if not username.strip() or len(password) < 8:
            raise ValueError("Username wajib diisi dan password minimal 8 karakter")
        cfg = self.load()
        users = cfg.setdefault("users", [])
        if any(u.get("username") == username for u in users):
            raise ValueError("Username sudah ada")
        users.append(self._new_user(username, password, role))
        self.save(cfg)

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        if len(new_password) < 8:
            raise ValueError("Password baru minimal 8 karakter")
        cfg = self.load()
        for user in cfg.get("users", []):
            if user.get("username") == username and check_password_hash(user.get("password_hash", ""), old_password):
                user["password_hash"] = generate_password_hash(new_password)
                self.save(cfg)
                return True
        return False

    def has_permission(self, role: str, feature: str, level: str = "view") -> bool:
        if role == "owner":
            return True
        role_perms = PERMISSIONS.get(role, {})
        granted = role_perms.get(feature)
        if not granted:
            return False
        rank = {"view": 1, "read": 2, "restart": 2, "limited": 3, "full": 4}
        return rank.get(granted, 0) >= rank.get(level, 1)

    def _new_user(self, username: str, password: str, role: str) -> dict[str, str]:
        return {
            "id": secrets.token_hex(8),
            "username": username.strip(),
            "password_hash": generate_password_hash(password),
            "role": role,
            "created_at": str(int(time.time())),
        }

    def _is_locked(self, cfg: dict[str, Any], ip: str) -> bool:
        attempts = cfg.setdefault("login_attempts", {})
        item = attempts.get(hashlib.sha256(ip.encode()).hexdigest())
        if not item:
            return False
        if item.get("count", 0) < cfg.get("max_login_attempts", 5):
            return False
        return time.time() - item.get("last", 0) < cfg.get("lockout_seconds", 300)

    def _record_attempt(self, cfg: dict[str, Any], ip: str, success: bool) -> None:
        key = hashlib.sha256(ip.encode()).hexdigest()
        attempts = cfg.setdefault("login_attempts", {})
        if success:
            attempts.pop(key, None)
        else:
            item = attempts.setdefault(key, {"count": 0, "last": 0})
            item["count"] = item.get("count", 0) + 1
            item["last"] = time.time()
