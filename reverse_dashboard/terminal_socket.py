from __future__ import annotations

import fcntl
import os
import pty
import select
import signal
import struct
import termios
from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen

from flask import current_app, request, session
from flask_socketio import disconnect, emit

from .extensions import audit_service, auth_service


@dataclass
class PtySession:
    fd: int
    proc: Popen
    cwd: Path


SESSIONS: dict[str, PtySession] = {}


def register_terminal_socket(socketio) -> None:
    namespace = "/terminal"

    def allowed() -> bool:
        if not session.get("logged_in"):
            return False
        if not current_app.config.get("ENABLE_TERMINAL", False):
            return False
        return auth_service().has_permission(session.get("role", "readonly"), "terminal", "full")

    @socketio.on("connect", namespace=namespace)
    def terminal_connect():
        if not allowed():
            return False
        emit("terminal_status", {"connected": True})

    @socketio.on("terminal_start", namespace=namespace)
    def terminal_start(data=None):
        if not allowed():
            emit("terminal_output", {"data": "\r\nPermission denied\r\n"})
            disconnect()
            return
        sid = request.sid
        close_session(sid)
        rows = int((data or {}).get("rows") or 30)
        cols = int((data or {}).get("cols") or 120)
        shell = os.environ.get("SHELL") or "/bin/bash"
        cwd = Path(current_app.config.get("HOST_ROOT", "/")).resolve()
        master_fd, slave_fd = pty.openpty()
        set_winsize(master_fd, rows, cols)
        env = os.environ.copy()
        env.update({"TERM": "xterm-256color", "COLORTERM": "truecolor"})
        proc = Popen([shell, "-l"], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, cwd=str(cwd), env=env, preexec_fn=os.setsid, close_fds=True)
        os.close(slave_fd)
        SESSIONS[sid] = PtySession(fd=master_fd, proc=proc, cwd=cwd)
        audit_service().log("TERMINAL_PTY_START", session.get("username", "unknown"), request.remote_addr or "unknown", str(cwd))
        socketio.start_background_task(read_loop, socketio, sid, namespace)
        emit("terminal_status", {"connected": True, "pid": proc.pid})

    @socketio.on("terminal_input", namespace=namespace)
    def terminal_input(data=None):
        pty_session = SESSIONS.get(request.sid)
        if not pty_session:
            emit("terminal_output", {"data": "\r\nNo active terminal session\r\n"})
            return
        value = str((data or {}).get("data", ""))
        if value:
            os.write(pty_session.fd, value.encode("utf-8", errors="ignore"))

    @socketio.on("terminal_resize", namespace=namespace)
    def terminal_resize(data=None):
        pty_session = SESSIONS.get(request.sid)
        if not pty_session:
            return
        set_winsize(pty_session.fd, int((data or {}).get("rows") or 30), int((data or {}).get("cols") or 120))

    @socketio.on("terminal_stop", namespace=namespace)
    def terminal_stop():
        close_session(request.sid)
        emit("terminal_status", {"connected": False})

    @socketio.on("disconnect", namespace=namespace)
    def terminal_disconnect():
        close_session(request.sid)


def read_loop(socketio, sid: str, namespace: str) -> None:
    pty_session = SESSIONS.get(sid)
    if not pty_session:
        return
    fd = pty_session.fd
    try:
        while sid in SESSIONS and pty_session.proc.poll() is None:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            socketio.emit("terminal_output", {"data": chunk.decode("utf-8", errors="replace")}, to=sid, namespace=namespace)
    finally:
        socketio.emit("terminal_status", {"connected": False}, to=sid, namespace=namespace)
        close_session(sid)


def set_winsize(fd: int, rows: int, cols: int) -> None:
    rows = max(10, min(rows, 80))
    cols = max(40, min(cols, 240))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def close_session(sid: str) -> None:
    pty_session = SESSIONS.pop(sid, None)
    if not pty_session:
        return
    try:
        if pty_session.proc.poll() is None:
            os.killpg(os.getpgid(pty_session.proc.pid), signal.SIGHUP)
    except OSError:
        pass
    try:
        os.close(pty_session.fd)
    except OSError:
        pass
