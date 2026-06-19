from __future__ import annotations

import os
import platform
import socket
import time
from pathlib import Path

import psutil


def bytes_human(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


class SystemService:
    def summary(self) -> dict:
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        boot = psutil.boot_time()
        return {
            "cpu": {
                "percent": psutil.cpu_percent(interval=0.1),
                "cores": psutil.cpu_count(logical=True),
                "load": os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0],
            },
            "memory": {
                "percent": vm.percent,
                "used": vm.used,
                "total": vm.total,
                "used_human": bytes_human(vm.used),
                "total_human": bytes_human(vm.total),
            },
            "disk": {
                "percent": disk.percent,
                "used": disk.used,
                "total": disk.total,
                "used_human": bytes_human(disk.used),
                "total_human": bytes_human(disk.total),
            },
            "network": {
                "sent": net.bytes_sent,
                "recv": net.bytes_recv,
                "sent_human": bytes_human(net.bytes_sent),
                "recv_human": bytes_human(net.bytes_recv),
            },
            "uptime_seconds": int(time.time() - boot),
        }

    def info(self) -> dict:
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "processor": platform.processor() or "unknown",
        }

    def processes(self, limit: int = 50) -> list[dict]:
        rows = []
        for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent", "status"]):
            try:
                info = proc.info
                rows.append({
                    "pid": info.get("pid"),
                    "name": info.get("name") or "unknown",
                    "user": info.get("username") or "-",
                    "cpu": round(info.get("cpu_percent") or 0, 1),
                    "memory": round(info.get("memory_percent") or 0, 1),
                    "status": info.get("status") or "-",
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        rows.sort(key=lambda item: (item["cpu"], item["memory"]), reverse=True)
        return rows[:limit]

    def disks(self) -> list[dict]:
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "percent": usage.percent,
                    "used_human": bytes_human(usage.used),
                    "total_human": bytes_human(usage.total),
                })
            except (PermissionError, OSError):
                continue
        return disks

    def network(self) -> dict:
        total = psutil.net_io_counters()
        interfaces = []
        per_nic = psutil.net_io_counters(pernic=True)
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, counters in per_nic.items():
            iface_addrs = []
            for addr in addrs.get(name, []):
                if addr.family in (socket.AF_INET, socket.AF_INET6):
                    iface_addrs.append(addr.address)
            stat = stats.get(name)
            interfaces.append({
                "name": name,
                "is_up": bool(stat.isup) if stat else False,
                "speed": getattr(stat, "speed", 0) if stat else 0,
                "mtu": getattr(stat, "mtu", 0) if stat else 0,
                "addresses": iface_addrs,
                "sent": counters.bytes_sent,
                "recv": counters.bytes_recv,
                "sent_human": bytes_human(counters.bytes_sent),
                "recv_human": bytes_human(counters.bytes_recv),
                "packets_sent": counters.packets_sent,
                "packets_recv": counters.packets_recv,
                "errors": counters.errin + counters.errout,
                "drops": counters.dropin + counters.dropout,
            })
        interfaces.sort(key=lambda item: (item["is_up"], item["recv"] + item["sent"]), reverse=True)
        return {
            "hostname": socket.gethostname(),
            "total": {
                "sent": total.bytes_sent,
                "recv": total.bytes_recv,
                "sent_human": bytes_human(total.bytes_sent),
                "recv_human": bytes_human(total.bytes_recv),
                "packets_sent": total.packets_sent,
                "packets_recv": total.packets_recv,
            },
            "interfaces": interfaces,
        }

    def storage(self) -> dict:
        partitions = self.disks()
        root = psutil.disk_usage("/")
        return {
            "root": {
                "percent": root.percent,
                "used": root.used,
                "total": root.total,
                "free": root.free,
                "used_human": bytes_human(root.used),
                "total_human": bytes_human(root.total),
                "free_human": bytes_human(root.free),
            },
            "partitions": partitions,
            "partition_count": len(partitions),
        }

    def security_summary(self, security_cfg: dict) -> dict:
        users = security_cfg.get("users", [])
        attempts = security_cfg.get("login_attempts", {})
        now = time.time()
        lockout = int(security_cfg.get("lockout_seconds", 300) or 0)
        locked = sum(1 for item in attempts.values() if item.get("count", 0) >= security_cfg.get("max_login_attempts", 5) and now - item.get("last", 0) < lockout)
        roles: dict[str, int] = {}
        for user in users:
            role = user.get("role", "readonly")
            roles[role] = roles.get(role, 0) + 1
        return {
            "setup_complete": bool(security_cfg.get("setup_complete")),
            "session_timeout": security_cfg.get("session_timeout", 3600),
            "max_login_attempts": security_cfg.get("max_login_attempts", 5),
            "lockout_seconds": lockout,
            "users_total": len(users),
            "roles": roles,
            "active_attempt_records": len(attempts),
            "locked_sources": locked,
        }
