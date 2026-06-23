from __future__ import annotations

from typing import Any
from pathlib import Path
import re

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

    def images(self) -> list[dict[str, Any]]:
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        rows = []
        for image in client.images.list():
            attrs = image.attrs
            tags = image.tags or [image.short_id]
            rows.append({
                "id": image.short_id,
                "tags": tags,
                "size": attrs.get("Size", 0),
                "size_human": bytes_human(attrs.get("Size", 0)),
                "created": attrs.get("Created", "")[:19].replace("T", " "),
            })
        rows.sort(key=lambda item: (item["tags"][0] if item["tags"] else item["id"]).lower())
        return rows

    def networks(self) -> list[dict[str, Any]]:
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        rows = []
        for network in client.networks.list():
            attrs = network.attrs
            rows.append({
                "id": network.short_id,
                "name": network.name,
                "driver": attrs.get("Driver", ""),
                "scope": attrs.get("Scope", ""),
                "containers": len(attrs.get("Containers") or {}),
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
        if action not in {"start", "stop", "restart", "kill", "remove"}:
            raise ValueError("Action Docker tidak valid")
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        container = client.containers.get(container_id)
        if action == "remove":
            container.remove(force=True)
            return
        getattr(container, action)()

    def pull_image(self, image: str) -> dict[str, Any]:
        image = (image or "").strip()
        if not image:
            raise ValueError("Image wajib diisi")
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        pulled = client.images.pull(image)
        return {"id": pulled.short_id, "tags": pulled.tags or [image]}

    def remove_image(self, image: str, force: bool = False) -> None:
        image = (image or "").strip()
        if not image:
            raise ValueError("Image wajib diisi")
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        client.images.remove(image=image, force=force)

    def create_container(self, data: dict[str, Any]) -> dict[str, Any]:
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        image = str(data.get("image", "")).strip()
        if not image:
            raise ValueError("Image wajib diisi")
        client = docker.from_env()
        kwargs: dict[str, Any] = {
            "image": image,
            "detach": True,
        }
        name = str(data.get("name", "")).strip()
        if name:
            kwargs["name"] = name
        command = str(data.get("command", "")).strip()
        if command:
            kwargs["command"] = command
        ports = self._parse_ports(str(data.get("ports", "")))
        if ports:
            kwargs["ports"] = ports
        environment = self._parse_key_values(str(data.get("env", "")))
        if environment:
            kwargs["environment"] = environment
        volumes = self._parse_volumes(str(data.get("volumes", "")))
        if volumes:
            kwargs["volumes"] = volumes
        network = str(data.get("network", "")).strip()
        if network:
            kwargs["network"] = network
        restart_policy = str(data.get("restart_policy", "")).strip()
        if restart_policy and restart_policy != "no":
            if restart_policy not in {"always", "unless-stopped", "on-failure"}:
                raise ValueError("Restart policy tidak valid")
            kwargs["restart_policy"] = {"Name": restart_policy}
        container = client.containers.run(**kwargs)
        if bool(data.get("start", True)) is False:
            container.stop(timeout=10)
        return {"id": container.short_id, "name": container.name, "image": image}

    def logs(self, container_id: str, lines: int = 300) -> str:
        if docker is None:
            raise RuntimeError("Docker SDK belum tersedia")
        client = docker.from_env()
        container = client.containers.get(container_id)
        return container.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")

    @staticmethod
    def _parse_key_values(raw: str) -> dict[str, str]:
        values = {}
        for line in raw.replace(",", "\n").splitlines():
            item = line.strip()
            if not item:
                continue
            key, sep, value = item.partition("=")
            if not sep or not key.strip():
                raise ValueError(f"Format environment tidak valid: {item}")
            values[key.strip()] = value.strip()
        return values

    @staticmethod
    def _parse_ports(raw: str) -> dict[str, int | tuple[str, int]]:
        ports: dict[str, int | tuple[str, int]] = {}
        for line in raw.replace(",", "\n").splitlines():
            item = line.strip()
            if not item:
                continue
            if ":" not in item:
                raise ValueError(f"Format port tidak valid: {item}")
            host, container = item.rsplit(":", 1)
            if "/" not in container:
                container = f"{container}/tcp"
            if not re.match(r"^\d+/(tcp|udp)$", container):
                raise ValueError(f"Port container tidak valid: {container}")
            if ":" in host:
                host_ip, host_port = host.rsplit(":", 1)
                ports[container] = (host_ip, int(host_port))
            else:
                ports[container] = int(host)
        return ports

    @staticmethod
    def _parse_volumes(raw: str) -> dict[str, dict[str, str]]:
        volumes = {}
        for line in raw.replace(",", "\n").splitlines():
            item = line.strip()
            if not item:
                continue
            parts = item.split(":")
            if len(parts) < 2:
                raise ValueError(f"Format volume tidak valid: {item}")
            host_path, container_path = parts[0], parts[1]
            mode = parts[2] if len(parts) > 2 else "rw"
            if mode not in {"rw", "ro"}:
                raise ValueError(f"Mode volume tidak valid: {mode}")
            volumes[host_path] = {"bind": container_path, "mode": mode}
        return volumes
