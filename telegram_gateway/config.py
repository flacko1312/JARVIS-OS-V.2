from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    pass


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive")
    return value


def _chat_ids(raw: str) -> frozenset[int]:
    values: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.add(int(item))
        except ValueError as exc:
            raise ConfigurationError("TELEGRAM_ALLOWED_CHAT_IDS must contain numeric IDs") from exc
    if not values:
        raise ConfigurationError("TELEGRAM_ALLOWED_CHAT_IDS is required")
    return frozenset(values)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_chat_ids: frozenset[int]
    poll_timeout: int
    request_timeout: int
    socket_path: Path
    state_dir: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")
        if any(ch.isspace() for ch in token):
            raise ConfigurationError("TELEGRAM_BOT_TOKEN has an invalid format")
        runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        state_dir = Path(
            os.environ.get(
                "TELEGRAM_STATE_DIR",
                str(Path.home() / ".local" / "state" / "jarvis-telegram"),
            )
        ).expanduser()
        return cls(
            bot_token=token,
            allowed_chat_ids=_chat_ids(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")),
            poll_timeout=min(_positive_int("TELEGRAM_POLL_TIMEOUT", 30), 50),
            request_timeout=_positive_int("TELEGRAM_REQUEST_TIMEOUT", 135),
            socket_path=Path(
                os.environ.get("JARVIS_TEXT_SOCKET", str(runtime_dir / "jarvis-text.sock"))
            ),
            state_dir=state_dir,
            log_level=os.environ.get("TELEGRAM_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )
