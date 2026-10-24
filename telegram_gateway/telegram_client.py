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

    def send_text(self, chat_id: int, text: str) -> None:
        self._call(
            "sendMessage",
            {"chat_id": str(chat_id), "text": text, "disable_web_page_preview": "true"},
            timeout=self._request_timeout,
        )

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self._call("sendChatAction", {"chat_id": str(chat_id), "action": action}, timeout=10)

    def get_me(self) -> dict[str, Any]:
        result = self._call("getMe", {}, timeout=15).get("result", {})
        return result if isinstance(result, dict) else {}

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
