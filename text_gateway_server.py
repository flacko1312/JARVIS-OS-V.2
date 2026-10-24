"""Owner-only local IPC adapter for text channels such as Telegram.

The server runs inside the existing JARVIS process and forwards each request to
``JarvisLive.ask_text``.  It contains no model, router, memory, or tool logic.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socketserver
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.text_gateway")

MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_TIMEOUT_SECONDS = 120.0


def default_socket_path() -> Path:
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return runtime_dir / "jarvis-text.sock"


class _TextHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            self._reply({"ok": False, "error": "request too large"})
            return
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reply({"ok": False, "error": "invalid JSON request"})
            return

        text = str(request.get("text", "")).strip()
        channel = str(request.get("channel", "telegram")).strip().lower()
        session_id = str(request.get("session_id", "")).strip()
        if not text:
            self._reply({"ok": False, "error": "text is required"})
            return
        if channel != "telegram":
            self._reply({"ok": False, "error": "unsupported channel"})
            return

        jarvis = self.server.jarvis  # type: ignore[attr-defined]
        loop = getattr(jarvis, "_loop", None)
        if loop is None or not loop.is_running():
            self._reply({"ok": False, "error": "JARVIS is not ready"})
            return
        logger.info("TEXT_REQUEST channel=%s session=%s chars=%d", channel, session_id[:16], len(text))
        try:
            pending = asyncio.run_coroutine_threadsafe(
                jarvis.ask_text(text, channel=channel, timeout=DEFAULT_TIMEOUT_SECONDS), loop
            )
            answer = pending.result(timeout=DEFAULT_TIMEOUT_SECONDS + 5)
        except TimeoutError:
            self._reply({"ok": False, "error": "JARVIS response timed out"})
            return
        except Exception as exc:
            logger.warning("TEXT_REQUEST failed type=%s", type(exc).__name__)
            self._reply({"ok": False, "error": "JARVIS could not process the request"})
            return
        self._reply({"ok": True, "answer": answer})

    def _reply(self, payload: dict[str, Any]) -> None:
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")


class _TextServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: str, jarvis: Any):
        self.jarvis = jarvis
        super().__init__(socket_path, _TextHandler)


def start(jarvis: Any, socket_path: Path | None = None) -> dict[str, Any]:
    """Start the local text bridge and restrict its Unix socket to the owner."""
    path = socket_path or default_socket_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    try:
        server = _TextServer(str(path), jarvis)
        os.chmod(path, 0o600)
    except OSError as exc:
        logger.error("Text gateway failed to start: %s", exc)
        return {"started": False, "reason": str(exc)}
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="jarvis-text-gateway")
    thread.start()
    logger.info("Text gateway listening on owner-only Unix socket %s", path)
    return {"started": True, "socket": str(path), "server": server}
