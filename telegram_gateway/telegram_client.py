from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, request_timeout: int = 135):
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._request_timeout = request_timeout

    def get_updates(self, offset: int, timeout: int) -> list[dict[str, Any]]:
        payload = self._call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": json.dumps(["message"])},
            timeout=timeout + 10,
        )
        result = payload.get("result", [])
        return result if isinstance(result, list) else []

    def send_text(self, chat_id: int, text: str, parse_mode: str | None = None) -> None:
        values = {
            "chat_id": str(chat_id),
            "text": text,
            "link_preview_options": json.dumps({"is_disabled": True}),
        }
        if parse_mode:
            values["parse_mode"] = parse_mode
        self._call(
            "sendMessage",
            values,
            timeout=self._request_timeout,
        )

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self._call("sendChatAction", {"chat_id": str(chat_id), "action": action}, timeout=10)

    def get_me(self) -> dict[str, Any]:
        result = self._call("getMe", {}, timeout=15).get("result", {})
        return result if isinstance(result, dict) else {}

    def configure_profile(self) -> None:
        """Apply the canonical public presentation without touching credentials."""
        commands = [
            {"command": "start", "description": "Abrir Lilith / JARVIS"},
            {"command": "help", "description": "Ver capacidades y ejemplos"},
            {"command": "estado", "description": "Consultar el estado del servidor"},
        ]
        self._call("setMyName", {"name": "Lilith · JARVIS"}, timeout=15)
        self._call(
            "setMyDescription",
            {
                "description": (
                    "Acceso privado a JARVIS Ubuntu: conversación con contexto, información web "
                    "con fuentes y diagnóstico de servicios, recursos, procesos, Docker y logs."
                )
            },
            timeout=15,
        )
        self._call(
            "setMyShortDescription",
            {"short_description": "Asistente privado para JARVIS Ubuntu · solo texto"},
            timeout=15,
        )
        self._call("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)}, timeout=15)

    def get_profile(self) -> dict[str, Any]:
        """Read back the configurable profile fields for deployment validation."""
        return {
            "identity": self.get_me(),
            "description": self._call("getMyDescription", {}, timeout=15).get("result", {}),
            "short_description": self._call("getMyShortDescription", {}, timeout=15).get("result", {}),
            "commands": self._call("getMyCommands", {}, timeout=15).get("result", []),
        }

    def _call(self, method: str, values: dict[str, str], timeout: int) -> dict[str, Any]:
        body = urlencode(values).encode("utf-8")
        request = Request(f"{self._base_url}/{method}", data=body, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            raise TelegramError(f"Telegram API request failed: {type(exc).__name__}") from exc
        if not payload.get("ok"):
            raise TelegramError(f"Telegram API rejected {method}")
        return payload
