from __future__ import annotations

from typing import Any

from .json_store import JsonStore

SETTINGS_FILE = "settings.json"


DEFAULT_SETTINGS: dict[str, Any] = {
    "general": {
        "server_name": "Reverse Server",
        "timezone": "Asia/Jakarta",
        "default_page": "dashboard",
    },
    "appearance": {
        "accent": "cyan",
        "density": "comfortable",
        "theme": "dark",
    },
    "monitoring": {
        "stats_interval_ms": 2000,
        "process_limit": 50,
    },
    "features": {
        "docker": True,
        "files": True,
        "terminal": False,
        "host_control": False,
    },
}


class SettingsService:
    def __init__(self, store: JsonStore):
        self.store = store

    def load(self) -> dict[str, Any]:
        saved = self.store.read(SETTINGS_FILE, {})
        return self._merge(DEFAULT_SETTINGS, saved if isinstance(saved, dict) else {})

    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.load()
        merged = self._merge(current, updates)
        self.store.write(SETTINGS_FILE, merged)
        return merged

    def reset(self) -> dict[str, Any]:
        self.store.write(SETTINGS_FILE, DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

    def _merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge(result[key], value)
            else:
                result[key] = value
        return result
