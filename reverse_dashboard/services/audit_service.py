from __future__ import annotations

import time
from pathlib import Path


class AuditService:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "audit.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, action: str, user: str = "system", ip: str = "unknown", detail: str = "") -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} | {user} | {ip} | {action} | {detail}\n"
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def tail(self, lines: int = 200) -> list[str]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as fh:
                return fh.readlines()[-lines:]
        except OSError:
            return []
