from __future__ import annotations

import json
import socket
from pathlib import Path


class JarvisUnavailable(RuntimeError):
    pass


class JarvisTextClient:
    def __init__(self, socket_path: Path, timeout: int = 135):
        self.socket_path = socket_path
        self.timeout = timeout

    def ask(self, text: str, session_id: str) -> str:
        request = {
            "channel": "telegram",
            "session_id": session_id,
            "text": str(text),
        }
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(str(self.socket_path))
                client.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
                response = self._readline(client)
        except (OSError, TimeoutError) as exc:
            raise JarvisUnavailable("JARVIS no está disponible temporalmente.") from exc
        try:
            payload = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JarvisUnavailable("JARVIS devolvió una respuesta no válida.") from exc
        if not payload.get("ok"):
            raise JarvisUnavailable(str(payload.get("error") or "JARVIS no pudo responder."))
        return str(payload.get("answer") or "").strip()

    @staticmethod
    def _readline(client: socket.socket) -> bytes:
        data = bytearray()
        while len(data) <= 4 * 1024 * 1024:
            chunk = client.recv(65536)
            if not chunk:
                break
            data.extend(chunk)
            if b"\n" in chunk:
                break
        if not data:
            raise JarvisUnavailable("JARVIS cerró la conexión sin responder.")
        return bytes(data).split(b"\n", 1)[0]
