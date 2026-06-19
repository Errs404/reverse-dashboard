from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tarfile
import time
from pathlib import Path


def run_cmd(args: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "command timeout"


class PM2Service:
    def __init__(self, enabled: bool = True, allow_install: bool = False, host_control: bool = False, base_dir: Path | None = None):
        self.enabled = enabled
        self.allow_install = allow_install
        self.host_control = host_control
        self.base_dir = base_dir or Path.cwd()

    def status(self) -> dict:
        pm2 = shutil.which("pm2")
        node = shutil.which("node")
        npm = shutil.which("npm")
        return {
            "enabled": self.enabled,
            "installed": bool(pm2),
            "pm2_path": pm2,
            "node_path": node,
            "npm_path": npm,
            "allow_install": self.allow_install and self.host_control,
            "install_command": "sudo bash scripts/install-runtime-tools.sh --pm2",
            "platform": platform.platform(),
        }

    def processes(self) -> list[dict]:
        if not self.enabled or not shutil.which("pm2"):
            return []
        code, out, _ = run_cmd(["pm2", "jlist"], timeout=12)
        if code != 0 or not out:
            return []
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return []
        rows = []
        for item in data:
            env = item.get("pm2_env", {})
            mon = item.get("monit", {})
            rows.append({
                "name": item.get("name", "unknown"),
                "pm_id": item.get("pm_id"),
                "status": env.get("status", "unknown"),
                "restart_time": env.get("restart_time", 0),
                "cpu": mon.get("cpu", 0),
                "memory": mon.get("memory", 0),
                "memory_human": self._bytes(mon.get("memory", 0)),
                "uptime": env.get("pm_uptime", 0),
            })
        return rows

    def action(self, name: str, action: str) -> dict:
        if action not in {"restart", "reload", "stop"}:
            raise ValueError("Invalid PM2 action")
        if not self.host_control:
            raise PermissionError("Host control disabled")
        code, out, err = run_cmd(["pm2", action, name], timeout=30)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code}

    def install(self) -> dict:
        script = self.base_dir / "scripts" / "install-runtime-tools.sh"
        if not script.exists():
            return {"success": False, "stdout": "", "stderr": f"installer not found: {script}", "code": 127}
        code, out, err = run_cmd(["bash", str(script), "--pm2"], timeout=300)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code}

    @staticmethod
    def _bytes(value: float) -> str:
        size = float(value or 0)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{value} B"


class NginxService:
    def __init__(self, enabled: bool = True, allow_install: bool = False, host_control: bool = False, base_dir: Path | None = None):
        self.enabled = enabled
        self.allow_install = allow_install
        self.host_control = host_control
        self.base_dir = base_dir or Path.cwd()

    def status(self) -> dict:
        nginx = shutil.which("nginx")
        version = ""
        if nginx:
            _, _, err = run_cmd([nginx, "-v"], timeout=8)
            version = err
        service_state = self._systemctl_state("nginx")
        return {
            "enabled": self.enabled,
            "installed": bool(nginx),
            "nginx_path": nginx,
            "version": version,
            "service_state": service_state,
            "allow_install": self.allow_install and self.host_control,
            "install_command": "sudo bash scripts/install-runtime-tools.sh --nginx",
            "config_paths": self.config_paths(),
        }

    def config_paths(self) -> list[dict]:
        candidates = [Path("/etc/nginx/nginx.conf"), Path("/etc/nginx/sites-enabled"), Path("/etc/nginx/conf.d")]
        return [{"path": str(p), "exists": p.exists(), "type": "dir" if p.is_dir() else "file"} for p in candidates]

    def test_config(self) -> dict:
        nginx = shutil.which("nginx")
        if not nginx:
            return {"success": False, "stdout": "", "stderr": "nginx not installed", "code": 127}
        code, out, err = run_cmd([nginx, "-t"], timeout=20)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code}

    def action(self, action: str) -> dict:
        if action not in {"reload", "restart"}:
            raise ValueError("Invalid nginx action")
        if not self.host_control:
            raise PermissionError("Host control disabled")
        code, out, err = run_cmd(["systemctl", action, "nginx"], timeout=30)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code}

    def install(self) -> dict:
        script = self.base_dir / "scripts" / "install-runtime-tools.sh"
        if not script.exists():
            return {"success": False, "stdout": "", "stderr": f"installer not found: {script}", "code": 127}
        code, out, err = run_cmd(["bash", str(script), "--nginx"], timeout=300)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code}

    @staticmethod
    def _systemctl_state(name: str) -> str:
        if not shutil.which("systemctl"):
            return "unknown"
        code, out, _ = run_cmd(["systemctl", "is-active", name], timeout=8)
        return out if code == 0 and out else "inactive"


class BackupService:
    def __init__(self, data_dir: Path, backup_dir: Path, enabled: bool = True, gdrive_enabled: bool = False, gdrive_remote: str = ""):
        self.data_dir = data_dir
        self.backup_dir = backup_dir
        self.enabled = enabled
        self.gdrive_enabled = gdrive_enabled
        self.gdrive_remote = gdrive_remote
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        backups = self.list_backups()
        return {"enabled": self.enabled, "backup_dir": str(self.backup_dir), "count": len(backups), "latest": backups[0] if backups else None, "gdrive": self.gdrive_status()}

    def gdrive_status(self) -> dict:
        return {"enabled": self.gdrive_enabled, "configured": bool(self.gdrive_remote), "remote": self.gdrive_remote, "rclone": shutil.which("rclone")}

    def list_backups(self) -> list[dict]:
        rows = []
        for path in sorted(self.backup_dir.glob("reverse-dashboard-*.tar.gz"), reverse=True):
            rows.append({"name": path.name, "size": path.stat().st_size, "size_human": PM2Service._bytes(path.stat().st_size), "created": int(path.stat().st_mtime)})
        return rows

    def create(self) -> dict:
        if not self.enabled:
            raise PermissionError("Backup disabled")
        name = f"reverse-dashboard-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
        target = self.backup_dir / name
        with tarfile.open(target, "w:gz") as tar:
            if self.data_dir.exists():
                for child in self.data_dir.iterdir():
                    if child.resolve() == self.backup_dir.resolve():
                        continue
                    tar.add(child, arcname=f"data/{child.name}")
        return {"name": name, "size": target.stat().st_size, "size_human": PM2Service._bytes(target.stat().st_size)}

    def path_for(self, name: str) -> Path:
        if "/" in name or "\\" in name or not name.endswith(".tar.gz"):
            raise ValueError("Invalid backup name")
        path = (self.backup_dir / name).resolve()
        if not str(path).startswith(str(self.backup_dir.resolve())) or not path.exists():
            raise FileNotFoundError(name)
        return path

    def upload_gdrive(self, name: str) -> dict:
        if not self.gdrive_enabled:
            raise PermissionError("Google Drive backup disabled")
        if not self.gdrive_remote:
            raise ValueError("GDRIVE_REMOTE is not configured")
        if not shutil.which("rclone"):
            raise RuntimeError("rclone not installed")
        path = self.path_for(name)
        code, out, err = run_cmd(["rclone", "copy", str(path), self.gdrive_remote], timeout=600)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code, "remote": self.gdrive_remote}


class FirewallService:
    def __init__(self, host_control: bool = False):
        self.host_control = host_control

    def status(self) -> dict:
        return {"host_control": self.host_control, "ufw": shutil.which("ufw"), "firewall_cmd": shutil.which("firewall-cmd")}

    def open_port(self, port: int, protocol: str = "tcp") -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        port = int(port)
        if port < 1 or port > 65535:
            raise ValueError("Port must be 1-65535")
        if protocol not in {"tcp", "udp"}:
            raise ValueError("Protocol must be tcp or udp")
        if shutil.which("ufw"):
            code, out, err = run_cmd(["ufw", "allow", f"{port}/{protocol}"], timeout=60)
            return {"tool": "ufw", "success": code == 0, "stdout": out, "stderr": err, "code": code}
        if shutil.which("firewall-cmd"):
            code1, out1, err1 = run_cmd(["firewall-cmd", "--permanent", f"--add-port={port}/{protocol}"], timeout=60)
            code2, out2, err2 = run_cmd(["firewall-cmd", "--reload"], timeout=60)
            return {"tool": "firewalld", "success": code1 == 0 and code2 == 0, "stdout": "\n".join([out1, out2]).strip(), "stderr": "\n".join([err1, err2]).strip(), "code": code1 or code2}
        raise RuntimeError("No supported firewall tool found. Install ufw or firewalld.")


class TerminalService:
    def __init__(self, enabled: bool = False, host_control: bool = False, cwd: Path | None = None):
        self.enabled = enabled
        self.host_control = host_control
        self.cwd = cwd or Path.cwd()

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "host_control": self.host_control,
            "available": self.enabled,
            "cwd": str(self.cwd),
            "shell": shutil.which("bash") or shutil.which("sh") or shutil.which("pwsh") or "unknown",
            "mode": "full_shell",
            "allowed_commands": ["all"],
            "warning": "Terminal is disabled only when ENABLE_TERMINAL=0.",
        }

    def run(self, command: str, timeout: int = 20) -> dict:
        if not self.enabled:
            raise PermissionError("Terminal disabled. Set ENABLE_TERMINAL=1 to enable guarded commands.")
        command = (command or "").strip()
        if not command:
            raise ValueError("Command is required")
        timeout = max(1, min(int(timeout or 20), 60))
        code, out, err = self._run_shell(command, timeout)
        return {"command": command, "code": code, "stdout": out, "stderr": err, "timeout": timeout}

    def _run_shell(self, command: str, timeout: int) -> tuple[int, str, str]:
        shell = shutil.which("bash") or shutil.which("sh")
        if shell:
            args = [shell, "-lc", command]
        elif shutil.which("pwsh"):
            args = ["pwsh", "-NoProfile", "-Command", command]
        else:
            raise ValueError("No supported shell found")
        try:
            proc = subprocess.run(args, cwd=self.cwd, capture_output=True, text=True, timeout=timeout, check=False)
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except subprocess.TimeoutExpired:
            return 124, "", "command timeout"
