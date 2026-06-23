from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path
from typing import BinaryIO

from .system_service import bytes_human


class FileService:
    def __init__(self, root: Path | str = "/"):
        self.root = Path(root).resolve()

    def resolve(self, requested: str | None) -> Path:
        if not requested or requested in {"/", "."}:
            return self.root
        path = Path(requested)
        requested_absolute = path.is_absolute()
        if not requested_absolute and path.root and not path.drive:
            path = Path(*path.parts[1:]) if len(path.parts) > 1 else Path(".")
        if not requested_absolute:
            path = self.root / path
        resolved = path.resolve()
        if self._is_within_root(resolved):
            return resolved

        # Treat absolute paths outside the configured root as root-relative input.
        # Example: with HOST_ROOT=/host/root, "/etc" resolves to "/host/root/etc".
        if requested_absolute:
            relative_parts = [part for part in path.parts if part not in {path.anchor, os.sep, "/"}]
            resolved = (self.root / Path(*relative_parts)).resolve() if relative_parts else self.root

        if not self._is_within_root(resolved):
            raise PermissionError("Path di luar root file browser")
        return resolved

    def _is_within_root(self, path: Path) -> bool:
        try:
            path.relative_to(self.root)
            return True
        except ValueError:
            return False

    def list_dir(self, requested: str | None, page: int = 1, per_page: int = 80) -> dict:
        path = self.resolve(requested)
        if not path.exists():
            raise FileNotFoundError("Path tidak ditemukan")
        if not path.is_dir():
            raise NotADirectoryError("Path bukan folder")

        entries = []
        for child in path.iterdir():
            try:
                st = child.stat()
                is_dir = child.is_dir()
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "is_dir": is_dir,
                    "size": st.st_size,
                    "size_human": "-" if is_dir else bytes_human(st.st_size),
                    "modified": int(st.st_mtime),
                    "mode": oct(st.st_mode)[-3:],
                })
            except OSError:
                continue
        entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        total = len(entries)
        start = max(page - 1, 0) * per_page
        end = start + per_page
        return {
            "current_path": str(path),
            "parent": str(path.parent) if path.parent != path else None,
            "page": page,
            "per_page": per_page,
            "total": total,
            "has_more": end < total,
            "items": entries[start:end],
        }

    def read_text(self, requested: str, max_bytes: int = 1024 * 1024) -> dict:
        path = self.resolve(requested)
        if not path.is_file():
            raise FileNotFoundError("File tidak ditemukan")
        if path.stat().st_size > max_bytes:
            raise ValueError("File terlalu besar untuk editor teks")
        mime, _ = mimetypes.guess_type(str(path))
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return {"path": str(path), "mime": mime or "text/plain", "content": fh.read()}

    def write_text(self, requested: str, content: str) -> None:
        path = self.resolve(requested)
        if path.exists() and not path.is_file():
            raise IsADirectoryError("Target bukan file")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def save_upload(self, requested_dir: str, filename: str, stream: BinaryIO, overwrite: bool = False) -> Path:
        safe_name = Path(filename or "").name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("Nama file upload tidak valid")
        dest_dir = self.resolve(requested_dir)
        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)
        if not dest_dir.is_dir():
            raise NotADirectoryError("Target upload bukan folder")
        target = (dest_dir / safe_name).resolve()
        if not self._is_within_root(target):
            raise PermissionError("Target upload di luar root file browser")
        if target.exists() and not overwrite:
            raise FileExistsError(f"File sudah ada: {safe_name}")
        with target.open("wb") as fh:
            shutil.copyfileobj(stream, fh)
        return target

    def mutate(self, action: str, path_value: str, **kwargs) -> None:
        path = self.resolve(path_value)
        if action == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
        elif action == "touch":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        elif action == "delete":
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        elif action == "rename":
            new_name = kwargs.get("new_name", "").strip()
            if not new_name or "/" in new_name or "\\" in new_name:
                raise ValueError("Nama baru tidak valid")
            path.rename(path.with_name(new_name))
        elif action == "copy":
            dest = self.resolve(kwargs.get("dest", ""))
            final = dest / path.name if dest.is_dir() else dest
            if path.is_dir():
                shutil.copytree(path, final, dirs_exist_ok=True)
            else:
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, final)
        elif action == "move":
            dest = self.resolve(kwargs.get("dest", ""))
            final = dest / path.name if dest.is_dir() else dest
            shutil.move(str(path), str(final))
        else:
            raise ValueError("Action tidak dikenal")
