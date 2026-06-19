from __future__ import annotations

from typing import Any
from pathlib import Path

try:
    import docker
except ImportError:  # pragma: no cover
    docker = None

from .system_service import bytes_human


class DockerService:
    def diagnostics(self) -> dict[str, Any]:
        if docker is None:
            return {"available": False, "reason": "Docker Python SDK missing", "fix": "pip install docker"}
        sock = Path("/var/run/docker.sock")
        try:
            client = docker.from_env()
            client.ping()
            return {"available": True, "reason": "Docker connected", "fix": ""}
        except PermissionError:
            return {"available": False, "reason": "Permission denied to Docker socket", "fix": "Add the service user to docker group or mount socket with proper permissions"}
        except Exception as exc:
            msg = str(exc)
            if not sock.exists():
                return {"available": False, "reason": "Docker socket not found", "fix": "Install/start Docker or mount /var/run/docker.sock into the container"}
            if "Permission denied" in msg:
                return {"available": False, "reason": "Permission denied to Docker socket", "fix": "sudo usermod -aG docker <user> then restart service"}
            if "Connection refused" in msg or "Error while fetching server API version" in msg:
                return {"available": False, "reason": "Docker daemon not reachable", "fix": "sudo systemctl enable --now docker"}
            return {"available": False, "reason": msg, "fix": "Check Docker daemon, socket mount, and permissions"}

    def available(self) -> bool:
        return bool(self.diagnostics().get("available"))

    def containers(self) -> list[dict[str, Any]]:
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        rows = []
        for c in client.containers.list(all=True):
            attrs = c.attrs
            ports = []
            for container_port, bindings in (attrs.get("NetworkSettings", {}).get("Ports") or {}).items():
                if bindings:
                    for bind in bindings:
                        ports.append({
                            "container": container_port,
                            "host_ip": bind.get("HostIp"),
                            "host_port": bind.get("HostPort"),
                        })
            rows.append({
                "id": c.short_id,
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                "status": c.status,
                "created": attrs.get("Created", "")[:19].replace("T", " "),
                "ports": ports,
                "network_mode": attrs.get("HostConfig", {}).get("NetworkMode", ""),
            })
        return rows

    def stats(self, container_id: str) -> dict[str, Any]:
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        container = client.containers.get(container_id)
        if container.status != "running":
            return {"cpu": 0, "memory": 0, "memory_used": "-", "memory_limit": "-"}
        raw = container.stats(stream=False)
        cpu_delta = raw["cpu_stats"]["cpu_usage"]["total_usage"] - raw["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = raw["cpu_stats"].get("system_cpu_usage", 0) - raw["precpu_stats"].get("system_cpu_usage", 0)
        cpu_percent = (cpu_delta / system_delta * 100) if system_delta else 0
        mem_usage = raw.get("memory_stats", {}).get("usage", 0)
        mem_limit = raw.get("memory_stats", {}).get("limit", 1)
        return {
            "cpu": round(cpu_percent, 1),
            "memory": round((mem_usage / mem_limit * 100) if mem_limit else 0, 1),
            "memory_used": bytes_human(mem_usage),
            "memory_limit": bytes_human(mem_limit),
        }

    def action(self, container_id: str, action: str) -> None:
        if action not in {"start", "stop", "restart", "kill"}:
            raise ValueError("Action Docker tidak valid")
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        container = client.containers.get(container_id)
        getattr(container, action)()

    def logs(self, container_id: str, lines: int = 300) -> str:
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        container = client.containers.get(container_id)
        return container.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
