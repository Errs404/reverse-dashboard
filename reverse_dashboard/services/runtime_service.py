from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import tarfile
import time
import ssl
import socket
from datetime import datetime, timezone
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
    def __init__(self, enabled: bool = True, allow_install: bool = False, host_control: bool = False, base_dir: Path | None = None, letsencrypt_email: str = "", letsencrypt_staging: bool = False):
        self.enabled = enabled
        self.allow_install = allow_install
        self.host_control = host_control
        self.base_dir = base_dir or Path.cwd()
        self.letsencrypt_email = letsencrypt_email
        self.letsencrypt_staging = letsencrypt_staging

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

    def list_sites(self) -> list[dict]:
        available = Path("/etc/nginx/sites-available")
        enabled = Path("/etc/nginx/sites-enabled")
        rows = []
        if not available.exists():
            return rows
        for path in sorted(p for p in available.iterdir() if p.is_file()):
            content = self._read_config(path)
            names = self._server_names(content)
            enabled_path = enabled / path.name
            rows.append({
                "name": path.name,
                "path": str(path),
                "enabled": enabled_path.exists(),
                "server_names": names,
                "ssl": "ssl_certificate" in content,
                "proxy_passes": re.findall(r"proxy_pass\s+([^;]+);", content),
                "modified": int(path.stat().st_mtime),
            })
        return rows

    def get_site(self, name: str) -> dict:
        path = self._site_path(name)
        if not path.exists():
            raise FileNotFoundError("Site config tidak ditemukan")
        return {"name": path.name, "content": self._read_config(path), "enabled": (Path("/etc/nginx/sites-enabled") / path.name).exists()}

    def save_site(self, name: str, content: str, enable: bool = True) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        path = self._site_path(name)
        if not content.strip():
            raise ValueError("Config tidak boleh kosong")
        path.parent.mkdir(parents=True, exist_ok=True)
        old_content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        if enable:
            self.enable_site(path.name)
        test = self.test_config()
        if not test.get("success"):
            if old_content is None:
                path.unlink(missing_ok=True)
                (Path("/etc/nginx/sites-enabled") / path.name).unlink(missing_ok=True)
            else:
                path.write_text(old_content, encoding="utf-8")
            raise RuntimeError(test.get("stderr") or "Nginx config test failed")
        return {"success": True, "name": path.name, "path": str(path), "test": test}

    def create_proxy_site(self, domain: str, upstream: str, root: str = "", ssl_redirect: bool = False) -> dict:
        domain = self._safe_domain(domain)
        upstream = upstream.strip()
        if not upstream.startswith(("http://", "https://")):
            upstream = f"http://{upstream}"
        root_line = f"\n    root {root.strip()};\n" if root.strip() else ""
        redirect_block = "" if not ssl_redirect else "\n    # Certbot will replace this after issuing SSL.\n"
        content = f"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain};{root_line}
    client_max_body_size 512M;{redirect_block}
    location / {{
        proxy_pass {upstream};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }}
}}
"""
        return self.save_site(domain, content, enable=True)

    def enable_site(self, name: str) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        path = self._site_path(name)
        if not path.exists():
            raise FileNotFoundError("Site config tidak ditemukan")
        enabled = Path("/etc/nginx/sites-enabled")
        enabled.mkdir(parents=True, exist_ok=True)
        link = enabled / path.name
        if not link.exists():
            link.symlink_to(path)
        return {"success": True, "enabled": True, "name": path.name}

    def disable_site(self, name: str) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        link = Path("/etc/nginx/sites-enabled") / self._safe_site_name(name)
        if link.exists() or link.is_symlink():
            link.unlink()
        return {"success": True, "enabled": False, "name": link.name}

    def delete_site(self, name: str) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        safe_name = self._safe_site_name(name)
        self.disable_site(safe_name)
        path = Path("/etc/nginx/sites-available") / safe_name
        path.unlink(missing_ok=True)
        return {"success": True, "deleted": safe_name}

    def issue_ssl(self, domain: str) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        domain = self._safe_domain(domain)
        certbot = shutil.which("certbot")
        if not certbot:
            raise RuntimeError("certbot tidak tersedia")
        args = [certbot, "--nginx", "-d", domain, "--redirect", "--agree-tos", "--non-interactive"]
        if self.letsencrypt_email:
            args.extend(["--email", self.letsencrypt_email])
        else:
            args.append("--register-unsafely-without-email")
        if self.letsencrypt_staging:
            args.append("--staging")
        code, out, err = run_cmd(args, timeout=600)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code, "domain": domain}

    def certificates(self) -> dict:
        certbot = shutil.which("certbot")
        if not certbot:
            return {"certbot": None, "certificates": [], "stderr": "certbot not installed"}
        code, out, err = run_cmd([certbot, "certificates"], timeout=60)
        return {"certbot": certbot, "code": code, "stdout": out, "stderr": err, "certificates": self._parse_certbot_certificates(out)}

    def renew_dry_run(self) -> dict:
        certbot = shutil.which("certbot")
        if not certbot:
            return {"success": False, "stdout": "", "stderr": "certbot not installed", "code": 127}
        code, out, err = run_cmd([certbot, "renew", "--dry-run"], timeout=900)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code}

    def certificate_probe(self, domain: str) -> dict:
        domain = self._safe_domain(domain)
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter", "")
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc) if not_after else None
        days_left = (expires - datetime.now(timezone.utc)).days if expires else None
        return {"domain": domain, "issuer": cert.get("issuer"), "subject": cert.get("subject"), "not_after": not_after, "days_left": days_left}

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
    def _read_config(path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _server_names(content: str) -> list[str]:
        names = []
        for match in re.findall(r"server_name\s+([^;]+);", content):
            names.extend(part for part in match.split() if part != "_")
        return names

    @staticmethod
    def _safe_site_name(name: str) -> str:
        value = Path(str(name or "").strip()).name
        if not value or value in {".", ".."} or not re.match(r"^[A-Za-z0-9._-]{1,120}$", value):
            raise ValueError("Nama site tidak valid")
        return value

    def _site_path(self, name: str) -> Path:
        return Path("/etc/nginx/sites-available") / self._safe_site_name(name)

    @staticmethod
    def _safe_domain(domain: str) -> str:
        value = str(domain or "").strip().lower()
        if not re.match(r"^[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]$", value) or ".." in value:
            raise ValueError("Domain tidak valid")
        return value

    @staticmethod
    def _systemctl_state(name: str) -> str:
        if not shutil.which("systemctl"):
            return "unknown"
        code, out, _ = run_cmd(["systemctl", "is-active", name], timeout=8)
        return out if code == 0 and out else "inactive"

    @staticmethod
    def _parse_certbot_certificates(output: str) -> list[dict]:
        certs = []
        current: dict[str, object] = {}
        for line in output.splitlines():
            text = line.strip()
            if text.startswith("Certificate Name:"):
                if current:
                    certs.append(current)
                current = {"name": text.split(":", 1)[1].strip()}
            elif text.startswith("Domains:"):
                current["domains"] = text.split(":", 1)[1].strip().split()
            elif text.startswith("Expiry Date:"):
                current["expiry"] = text.split(":", 1)[1].strip()
            elif text.startswith("Certificate Path:"):
                current["cert_path"] = text.split(":", 1)[1].strip()
            elif text.startswith("Private Key Path:"):
                current["key_path"] = text.split(":", 1)[1].strip()
        if current:
            certs.append(current)
        return certs


class ServiceManager:
    DEFAULT_SERVICES = ["nginx", "docker", "mysql", "mariadb", "postgresql", "redis-server", "ssh", "ufw"]

    def __init__(self, host_control: bool = False):
        self.host_control = host_control

    def list_services(self) -> dict:
        return {"host_control": self.host_control, "services": [self.status(name) for name in self.DEFAULT_SERVICES]}

    def status(self, name: str) -> dict:
        safe = self._safe_name(name)
        return {
            "name": safe,
            "exists": self._exists(safe),
            "active": self._systemctl("is-active", safe),
            "enabled": self._systemctl("is-enabled", safe),
        }

    def action(self, name: str, action: str) -> dict:
        if not self.host_control:
            raise PermissionError("Host control disabled")
        safe = self._safe_name(name)
        if action not in {"start", "stop", "restart", "reload", "enable", "disable"}:
            raise ValueError("Action service tidak valid")
        code, out, err = run_cmd(["systemctl", action, safe], timeout=90)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code, "service": safe, "action": action}

    def logs(self, name: str, lines: int = 120) -> dict:
        safe = self._safe_name(name)
        lines = max(20, min(int(lines or 120), 1000))
        code, out, err = run_cmd(["journalctl", "-u", safe, "-n", str(lines), "--no-pager"], timeout=30)
        return {"success": code == 0, "stdout": out, "stderr": err, "code": code, "service": safe}

    @staticmethod
    def _safe_name(name: str) -> str:
        value = str(name or "").strip()
        if not re.match(r"^[A-Za-z0-9@_.-]{1,120}$", value):
            raise ValueError("Nama service tidak valid")
        return value

    @staticmethod
    def _systemctl(action: str, name: str) -> str:
        if not shutil.which("systemctl"):
            return "unknown"
        code, out, _ = run_cmd(["systemctl", action, name], timeout=8)
        return out if out else ("unknown" if code != 0 else "")

    @staticmethod
    def _exists(name: str) -> bool:
        if not shutil.which("systemctl"):
            return False
        code, _, _ = run_cmd(["systemctl", "status", name], timeout=8)
        return code in {0, 3}


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

    def install_rclone(self) -> dict:
        if shutil.which("rclone"):
            return {"success": True, "stdout": f"rclone already installed: {shutil.which('rclone')}", "stderr": "", "code": 0}
        shell = shutil.which("bash") or shutil.which("sh")
        if not shell:
            return {"success": False, "stdout": "", "stderr": "bash/sh not found", "code": 127}
        command = "curl -fsSL https://rclone.org/install.sh | bash"
        try:
            proc = subprocess.run([shell, "-lc", command], capture_output=True, text=True, timeout=300, check=False)
            return {"success": proc.returncode == 0, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "code": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "rclone install timeout", "code": 124}

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
