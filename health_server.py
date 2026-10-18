"""Minimal local-only health/status HTTP server for JARVIS Headless.

Binds exclusively to 127.0.0.1 — never exposed externally.
Runs in a daemon thread so it dies with the main process.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import JarvisLive

_HEALTH_PORT = 7470
_start_time: float = 0.0
_jarvis_ref: JarvisLive | None = None

_FUNCTIONAL_STATES = {"LISTENING"}


def _state_name(jarvis) -> str:
    state = getattr(jarvis, "_conversation_state", None)
    return str(getattr(state, "value", state) or "UNKNOWN").upper()


def _lilith_available(jarvis) -> bool | None:
    lilith = getattr(jarvis, "_lilith", None)
    runtime = getattr(lilith, "_runtime", None) if lilith is not None else None
    value = getattr(runtime, "lilith_available", None) if runtime is not None else None
    return value if isinstance(value, bool) else None


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond_health()
        elif self.path == "/status":
            self._respond_status()
        else:
            self._send(404, {"error": "not found"})

    def _respond_health(self):
        jarvis = _jarvis_ref
        if jarvis is None:
            self._send(503, {"status": "starting"})
            return
        state = _state_name(jarvis)
        functional = state in _FUNCTIONAL_STATES
        self._send(200 if functional else 503, {
            "status": "ok" if functional else "not_ready",
            "state": state,
        })

    def _respond_status(self):
        jarvis = _jarvis_ref
        if jarvis is None:
            self._send(503, {"error": "jarvis not initialized"})
            return
        state = _state_name(jarvis)
        lilith_ok = _lilith_available(jarvis)
        uptime = time.time() - _start_time if _start_time else 0
        hours, remainder = divmod(int(uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        from core.live_model import HEADLESS_LIVE_MODEL
        self._send(200, {
            "state": state,
            "gemini_connected": state in _FUNCTIONAL_STATES,
            "lilith": "online" if lilith_ok is True else "offline" if lilith_ok is False else "unknown",
            "model": HEADLESS_LIVE_MODEL,
            "voice": getattr(jarvis, "voice_name", "unknown"),
            "headless": True,
            "audio_enabled": not getattr(jarvis, "no_audio", True),
            "pid": os.getpid(),
            "started_at": _start_time,
            "checked_at": time.time(),
            "uptime": f"{hours}h{minutes:02d}m{seconds:02d}s",
        })

    def _send(self, code: int, body: dict):
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


def start(jarvis: JarvisLive, port: int = _HEALTH_PORT) -> None:
    global _jarvis_ref, _start_time
    _jarvis_ref = jarvis
    _start_time = time.time()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
