from __future__ import annotations

import shutil
import os
import re
import subprocess
import time
from pathlib import Path
from typing import BinaryIO

from .runtime_service import run_cmd


class DatabaseService:
    def __init__(self, enabled: bool = True, host_control: bool = False, data_dir: Path | None = None):
        self.enabled = enabled
        self.host_control = host_control
        self.data_dir = data_dir or Path.cwd()
        self.export_dir = self.data_dir / "database-exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        services = [
            self._engine("mysql", "MySQL", "mysql", "mysql"),
            self._engine("mariadb", "MariaDB", "mariadb", "mysql"),
            self._engine("postgresql", "PostgreSQL", "psql", "postgresql"),
            self._sqlite(),
        ]
        return {
            "enabled": self.enabled,
            "host_control": self.host_control,
            "available": any(item.get("installed") for item in services),
            "services": services,
            "notes": [
                "Database manager tahap awal memakai service host dan command-line client yang sudah terpasang.",
                "Operasi create user/database perlu credentials database dan akan ditambahkan sebagai flow terpisah.",
            ],
        }

    def action(self, service: str, action: str) -> dict:
        if not self.enabled:
            raise PermissionError("Database feature disabled")
        if not self.host_control:
            raise PermissionError("Host control disabled")
        if service not in {"mysql", "mariadb", "postgresql"}:
            raise ValueError("Service database tidak valid")
        if action not in {"start", "stop", "restart", "reload"}:
            raise ValueError("Action database tidak valid")
        if not shutil.which("systemctl"):
            raise RuntimeError("systemctl tidak tersedia")
        code, out, err = run_cmd(["systemctl", action, service], timeout=60)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code, "service": service, "action": action}

    def list_databases(self, data: dict) -> dict:
        engine = self._engine_key(data.get("engine", "mysql"))
        if engine in {"mysql", "mariadb"}:
            code, out, err = self._run_mysql(engine, data, "SHOW DATABASES;")
            databases = [line.strip() for line in out.splitlines() if line.strip() and line.strip() != "Database"]
        else:
            code, out, err = self._run_postgres(data, "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;", tuples_only=True)
            databases = [line.strip() for line in out.splitlines() if line.strip()]
        return {"success": code == 0, "databases": databases, "stdout": out, "stderr": err, "code": code}

    def create_database(self, data: dict) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        engine = self._engine_key(data.get("engine", "mysql"))
        name = self._safe_identifier(data.get("database", ""), "database")
        if engine in {"mysql", "mariadb"}:
            sql = f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            code, out, err = self._run_mysql(engine, data, sql)
        else:
            code, out, err = self._run_postgres(data, f"CREATE DATABASE {self._pg_ident(name)};")
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code, "database": name}

    def create_user(self, data: dict) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        engine = self._engine_key(data.get("engine", "mysql"))
        username = self._safe_identifier(data.get("new_username", ""), "username")
        password = str(data.get("new_password", ""))
        database = str(data.get("database", "")).strip()
        if len(password) < 8:
            raise ValueError("Password database minimal 8 karakter")
        if engine in {"mysql", "mariadb"}:
            host = str(data.get("new_host", "%") or "%")
            escaped_user = self._mysql_string(username)
            escaped_host = self._mysql_string(host)
            escaped_password = self._mysql_string(password)
            sql = f"CREATE USER IF NOT EXISTS '{escaped_user}'@'{escaped_host}' IDENTIFIED BY '{escaped_password}';"
            if database:
                db = self._safe_identifier(database, "database")
                sql += f" GRANT ALL PRIVILEGES ON `{db}`.* TO '{escaped_user}'@'{escaped_host}'; FLUSH PRIVILEGES;"
            code, out, err = self._run_mysql(engine, data, sql)
        else:
            escaped_password = password.replace("'", "''")
            sql = f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{username}') THEN CREATE ROLE {self._pg_ident(username)} LOGIN PASSWORD '{escaped_password}'; END IF; END $$;"
            if database:
                db = self._safe_identifier(database, "database")
                sql += f" GRANT ALL PRIVILEGES ON DATABASE {self._pg_ident(db)} TO {self._pg_ident(username)};"
            code, out, err = self._run_postgres(data, sql)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code, "username": username}

    def export_database(self, data: dict) -> Path:
        engine = self._engine_key(data.get("engine", "mysql"))
        database = self._safe_identifier(data.get("database", ""), "database")
        ts = time.strftime("%Y%m%d-%H%M%S")
        suffix = "sql"
        target = (self.export_dir / f"{engine}-{database}-{ts}.{suffix}").resolve()
        if engine in {"mysql", "mariadb"}:
            binary = shutil.which("mysqldump") or shutil.which("mariadb-dump")
            if not binary:
                raise RuntimeError("mysqldump/mariadb-dump tidak tersedia")
            args, env = self._mysql_cli_args(binary, data)
            args.append(database)
            with target.open("w", encoding="utf-8") as fh:
                proc = subprocess.run(args, stdout=fh, stderr=subprocess.PIPE, text=True, timeout=900, check=False, env=env)
        else:
            binary = shutil.which("pg_dump")
            if not binary:
                raise RuntimeError("pg_dump tidak tersedia")
            args, env = self._postgres_cli_args(binary, data)
            args.extend(["-d", database])
            with target.open("w", encoding="utf-8") as fh:
                proc = subprocess.run(args, stdout=fh, stderr=subprocess.PIPE, text=True, timeout=900, check=False, env=env)
        if proc.returncode != 0:
            target.unlink(missing_ok=True)
            raise RuntimeError(proc.stderr.strip() or "Export database gagal")
        return target

    def import_database(self, data: dict, filename: str, stream: BinaryIO) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        engine = self._engine_key(data.get("engine", "mysql"))
        database = self._safe_identifier(data.get("database", ""), "database")
        safe_name = Path(filename or "import.sql").name
        temp_path = (self.export_dir / f"import-{int(time.time())}-{safe_name}").resolve()
        with temp_path.open("wb") as fh:
            shutil.copyfileobj(stream, fh)
        try:
            if engine in {"mysql", "mariadb"}:
                binary = shutil.which("mysql") or shutil.which("mariadb")
                if not binary:
                    raise RuntimeError("mysql/mariadb client tidak tersedia")
                args, env = self._mysql_cli_args(binary, data)
                args.append(database)
                with temp_path.open("rb") as fh:
                    proc = subprocess.run(args, stdin=fh, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, timeout=900, check=False, env=env)
            else:
                binary = shutil.which("psql")
                if not binary:
                    raise RuntimeError("psql tidak tersedia")
                args, env = self._postgres_cli_args(binary, data)
                args.extend(["-d", database, "-f", str(temp_path)])
                proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=900, check=False, env=env)
            stdout = proc.stdout.decode("utf-8", errors="replace") if isinstance(proc.stdout, bytes) else proc.stdout
            stderr = proc.stderr.decode("utf-8", errors="replace") if isinstance(proc.stderr, bytes) else proc.stderr
            return {"success": proc.returncode == 0, "stdout": stdout.strip(), "stderr": stderr.strip(), "code": proc.returncode}
        finally:
            temp_path.unlink(missing_ok=True)

    def _engine(self, key: str, label: str, binary: str, package: str) -> dict:
        path = shutil.which(binary)
        version = ""
        if path:
            code, out, err = run_cmd([path, "--version"], timeout=8)
            version = out or err if code == 0 else err
        return {
            "key": key,
            "label": label,
            "installed": bool(path),
            "binary": path,
            "version": version,
            "service_state": self._systemctl_state(key),
            "install_hint": f"apt install -y {package}",
        }

    def _run_mysql(self, engine: str, data: dict, sql: str) -> tuple[int, str, str]:
        binary = shutil.which("mysql") if engine == "mysql" else (shutil.which("mariadb") or shutil.which("mysql"))
        if not binary:
            return 127, "", "mysql/mariadb client tidak tersedia"
        args, env = self._mysql_cli_args(binary, data)
        args.extend(["-e", sql])
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, check=False, env=env)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def _run_postgres(self, data: dict, sql: str, tuples_only: bool = False) -> tuple[int, str, str]:
        binary = shutil.which("psql")
        if not binary:
            return 127, "", "psql tidak tersedia"
        args, env = self._postgres_cli_args(binary, data)
        if tuples_only:
            args.append("-At")
        args.extend(["-c", sql])
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, check=False, env=env)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    @staticmethod
    def _mysql_cli_args(binary: str, data: dict) -> tuple[list[str], dict[str, str]]:
        env = os.environ.copy()
        password = str(data.get("password", ""))
        if password:
            env["MYSQL_PWD"] = password
        args = [binary]
        username = str(data.get("username", "root") or "root")
        args.extend(["-u", username])
        host = str(data.get("host", "") or "")
        if host:
            args.extend(["-h", host])
        port = str(data.get("port", "") or "")
        if port:
            args.extend(["-P", port])
        return args, env

    @staticmethod
    def _postgres_cli_args(binary: str, data: dict) -> tuple[list[str], dict[str, str]]:
        env = os.environ.copy()
        password = str(data.get("password", ""))
        if password:
            env["PGPASSWORD"] = password
        username = str(data.get("username", "postgres") or "postgres")
        host = str(data.get("host", "") or "")
        port = str(data.get("port", "") or "")
        args = [binary, "-U", username]
        if host:
            args.extend(["-h", host])
        if port:
            args.extend(["-p", port])
        return args, env

    @staticmethod
    def _engine_key(value: object) -> str:
        engine = str(value or "mysql").strip().lower()
        if engine not in {"mysql", "mariadb", "postgresql"}:
            raise ValueError("Engine database tidak valid")
        return engine

    @staticmethod
    def _safe_identifier(value: object, label: str) -> str:
        text = str(value or "").strip()
        if not re.match(r"^[A-Za-z0-9_$-]{1,64}$", text):
            raise ValueError(f"Nama {label} tidak valid")
        return text

    @staticmethod
    def _mysql_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _pg_ident(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def _sqlite(self) -> dict:
        path = shutil.which("sqlite3")
        version = ""
        if path:
            code, out, err = run_cmd([path, "--version"], timeout=8)
            version = out or err if code == 0 else err
        return {
            "key": "sqlite",
            "label": "SQLite",
            "installed": bool(path),
            "binary": path,
            "version": version,
            "service_state": "embedded",
            "install_hint": "apt install -y sqlite3",
            "common_paths": [str(path) for path in [Path.cwd(), Path("/var/lib")] if path.exists()],
        }

    @staticmethod
    def _systemctl_state(name: str) -> str:
        if not shutil.which("systemctl"):
            return "unknown"
        code, out, _ = run_cmd(["systemctl", "is-active", name], timeout=8)
        return out if code == 0 and out else "inactive"
