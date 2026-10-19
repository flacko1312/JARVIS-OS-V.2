"""Secure remote API server for JARVIS Headless.

Listens on Tailscale interface (100.x.x.x) when available, otherwise
localhost only. All endpoints require a bearer token.

Endpoints:
  GET  /api/health     — unauthenticated health probe
  GET  /api/status     — full status (authenticated)
  GET  /api/tools      — list available tools
  POST /api/tool/invoke — invoke a tool (authenticated, permission-gated)
  GET  /api/panel      — minimal HTML status panel (authenticated)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import socket
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, parse_qs

if TYPE_CHECKING:
    from main import JarvisLive

logger = logging.getLogger("jarvis.api")

_API_PORT = 7471
_start_time: float = 0.0
_jarvis_ref: JarvisLive | None = None
_api_token: str | None = None


def _get_tailscale_ip() -> str | None:
    """Detect Tailscale IP (100.x.x.x) if available."""
    try:
        r = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            ip = r.stdout.strip().split("\n")[0]
            if ip.startswith("100."):
                return ip
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return None


def _validate_token(token: str) -> bool:
    """Constant-time token comparison."""
    if not _api_token:
        return False
    return hmac.compare_digest(token.encode(), _api_token.encode())


def _tailscale_status() -> dict[str, Any]:
    """Get Tailscale connection info."""
    try:
        r = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            self_node = data.get("Self", {})
            return {
                "connected": True,
                "hostname": self_node.get("HostName", "unknown"),
                "tailnet": data.get("MagicDNSSuffix", "unknown"),
                "ip": self_node.get("TailscaleIPs", [None])[0],
                "online": self_node.get("Online", False),
            }
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"connected": False}


class _APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._respond_health()
        elif path == "/api/status":
            if not self._check_auth():
                return
            self._respond_status()
        elif path == "/api/tools":
            if not self._check_auth():
                return
            self._respond_tools()
        elif path == "/api/panel":
            if not self._check_auth():
                return
            self._respond_panel()
        elif path == "/api/tailscale":
            if not self._check_auth():
                return
            self._send_json(200, _tailscale_status())
        elif path == "/api/voice":
            if not self._check_auth():
                return
            self._respond_voice_metrics()
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/tool/invoke":
            if not self._check_auth():
                return
            self._respond_invoke()
        else:
            self._send_json(404, {"error": "not found"})

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            if _validate_token(token):
                return True
        self._send_json(401, {"error": "unauthorized"})
        return False

    def _respond_health(self):
        jarvis = _jarvis_ref
        if jarvis is None:
            self._send_json(503, {"status": "starting"})
            return
        from health_server import _state_name, _FUNCTIONAL_STATES
        state = _state_name(jarvis)
        self._send_json(200 if state in _FUNCTIONAL_STATES else 503, {
            "status": "ok" if state in _FUNCTIONAL_STATES else "not_ready",
            "state": state,
        })

    def _respond_status(self):
        jarvis = _jarvis_ref
        if jarvis is None:
            self._send_json(503, {"error": "not initialized"})
            return
        from health_server import _state_name, _FUNCTIONAL_STATES, _lilith_available
        from core.live_model import HEADLESS_LIVE_MODEL
        state = _state_name(jarvis)
        lilith_ok = _lilith_available(jarvis)
        uptime = time.time() - _start_time if _start_time else 0
        hours, rem = divmod(int(uptime), 3600)
        mins, secs = divmod(rem, 60)
        ts = _tailscale_status()
        self._send_json(200, {
            "state": state,
            "gemini": state in _FUNCTIONAL_STATES,
            "lilith": "online" if lilith_ok is True else "offline" if lilith_ok is False else "unknown",
            "model": HEADLESS_LIVE_MODEL,
            "voice": getattr(jarvis, "voice_name", "unknown"),
            "pid": os.getpid(),
            "uptime": f"{hours}h{mins:02d}m{secs:02d}s",
            "tailscale": ts,
            "api_port": _API_PORT,
        })

    def _respond_tools(self):
        """List available headless tools with permission levels."""
        from core.headless_permissions import check_permission, get_all_rules
        tools = []
        for rule in get_all_rules():
            tools.append({
                "tool": rule.tool,
                "action": rule.action,
                "level": rule.level.value,
                "description": rule.description,
            })
        self._send_json(200, {"tools": tools})

    def _respond_voice_metrics(self):
        """Voice and connection stability metrics."""
        try:
            from core.voice_stability import get_monitor
            monitor = get_monitor()
            data = monitor.get_metrics()
            data["healthy"] = monitor.is_healthy()
            data["reconnect_history"] = monitor.get_reconnect_history(limit=10)
            self._send_json(200, data)
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _respond_invoke(self):
        """Invoke a tool via API. Only READ_ONLY and SAFE_WRITE allowed remotely."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, {"error": "invalid JSON"})
            return

        tool = body.get("tool", "")
        action = body.get("action", "*")

        from core.headless_permissions import check_permission, PermissionLevel
        perm = check_permission(tool, action)
        if perm.level == PermissionLevel.DENIED:
            self._send_json(403, {"error": f"Tool '{tool}' is denied"})
            return
        if perm.level == PermissionLevel.CONFIRM_REQUIRED:
            self._send_json(403, {
                "error": f"Tool '{tool}/{action}' requires voice confirmation, cannot invoke remotely"
            })
            return

        # Execute read-only/safe-write tools
        if tool == "system_status":
            from core.headless_tools import system_status
            self._send_json(200, system_status())
        elif tool == "process_list":
            from core.headless_tools import process_list
            filt = body.get("filter", "")
            self._send_json(200, {"processes": process_list(filt)})
        elif tool == "process_info":
            from core.headless_tools import process_info
            pid = body.get("pid", 0)
            self._send_json(200, process_info(int(pid)))
        elif tool == "systemd_status":
            from core.headless_tools import systemd_status
            svc = body.get("service", "")
            self._send_json(200, systemd_status(svc))
        elif tool == "systemd_list_failed":
            from core.headless_tools import systemd_list_failed
            self._send_json(200, {"failed": systemd_list_failed()})
        elif tool == "journal_read":
            from core.headless_tools import journal_read
            svc = body.get("service", "")
            lines = body.get("lines", 50)
            result = journal_read(svc, lines=int(lines))
            self._send_json(200, {"log": result})
        elif tool == "open_capabilities_catalog":
            from core.headless_tools import build_headless_catalog
            self._send_json(200, {"catalog": build_headless_catalog()})
        else:
            self._send_json(400, {"error": f"Tool '{tool}' not available via API"})

    def _respond_panel(self):
        """Minimal HTML status panel."""
        jarvis = _jarvis_ref
        if jarvis is None:
            status_text = "Starting..."
            state_class = "warning"
        else:
            from health_server import _state_name, _FUNCTIONAL_STATES
            state = _state_name(jarvis)
            status_text = state
            state_class = "ok" if state in _FUNCTIONAL_STATES else "warning"

        uptime = time.time() - _start_time if _start_time else 0
        hours, rem = divmod(int(uptime), 3600)
        mins, secs = divmod(rem, 60)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS Headless</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 2rem; }}
h1 {{ color: #58a6ff; font-size: 1.5rem; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; max-width: 600px; }}
.status {{ font-size: 1.2rem; font-weight: 600; }}
.ok {{ color: #3fb950; }}
.warning {{ color: #d29922; }}
.row {{ display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #21262d; }}
.label {{ color: #8b949e; }}
</style>
</head>
<body>
<h1>JARVIS Headless — server-lilith</h1>
<div class="card">
  <div class="status {state_class}">{status_text}</div>
  <div class="row"><span class="label">Uptime</span><span>{hours}h{mins:02d}m{secs:02d}s</span></div>
  <div class="row"><span class="label">PID</span><span>{os.getpid()}</span></div>
  <div class="row"><span class="label">API Port</span><span>{_API_PORT}</span></div>
</div>
<p style="color:#484f58;font-size:0.85rem;">Authenticated panel. All mutations require voice confirmation.</p>
</body>
</html>"""
        payload = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, code: int, body: Any):
        payload = json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        if args and "401" in str(args[1:2]):
            logger.warning("API unauthorized request from %s", self.client_address[0])


def start(jarvis: JarvisLive, port: int = _API_PORT, token: str | None = None) -> dict[str, Any]:
    """Start the API server.

    Binds to Tailscale IP if available, otherwise 127.0.0.1.
    Returns bind info dict.
    """
    global _jarvis_ref, _start_time, _api_token
    _jarvis_ref = jarvis
    _start_time = time.time()
    _api_token = token or os.environ.get("JARVIS_API_TOKEN")

    if not _api_token:
        logger.warning("JARVIS_API_TOKEN not set — API server disabled")
        return {"started": False, "reason": "no token configured"}

    ts_ip = _get_tailscale_ip()
    bind_addr = ts_ip or "127.0.0.1"

    try:
        server = HTTPServer((bind_addr, port), _APIHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        info = {
            "started": True,
            "bind": bind_addr,
            "port": port,
            "tailscale": ts_ip is not None,
            "url": f"http://{bind_addr}:{port}",
        }
        logger.info("API server started on %s:%d (tailscale=%s)", bind_addr, port, ts_ip is not None)
        return info
    except OSError as e:
        logger.error("API server failed to start: %s", e)
        return {"started": False, "reason": str(e)}
