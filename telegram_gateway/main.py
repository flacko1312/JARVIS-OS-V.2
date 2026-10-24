from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from typing import Any

from telegram_gateway.auth import ChatAuthorizer
from telegram_gateway.config import ConfigurationError, Settings
from telegram_gateway.formatter import split_message
from telegram_gateway.jarvis_client import JarvisTextClient, JarvisUnavailable
from telegram_gateway.sessions import OffsetStore, SessionStore
from telegram_gateway.telegram_client import TelegramClient, TelegramError

logger = logging.getLogger("jarvis.telegram")


class Gateway:
    def __init__(self, settings: Settings, telegram: TelegramClient | None = None):
        self.settings = settings
        self.telegram = telegram or TelegramClient(settings.bot_token, settings.request_timeout)
        self.jarvis = JarvisTextClient(settings.socket_path, settings.request_timeout)
        self.auth = ChatAuthorizer(settings.allowed_chat_ids)
        self.sessions = SessionStore(settings.state_dir / "sessions.json")
        self.offsets = OffsetStore(settings.state_dir / "update_offset")
        self._running = True

    def stop(self, *_args: object) -> None:
        self._running = False

    def run(self) -> None:
        offset = self.offsets.load()
        backoff = 1
        logger.info("Gateway started; allowed_chats=%d", len(self.settings.allowed_chat_ids))
        while self._running:
            try:
                updates = self.telegram.get_updates(offset, self.settings.poll_timeout)
                backoff = 1
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = max(offset, update_id + 1)
                    self.handle_update(update)
                    self.offsets.save(offset)
            except TelegramError as exc:
                logger.warning("Polling error: %s; retrying in %ds", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        if not self.auth.is_allowed(chat_id):
            logger.warning("Unauthorized Telegram chat blocked chat_id=%s", chat_id)
            return
        numeric_chat_id = int(chat_id)
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            self.telegram.send_text(numeric_chat_id, "Este acceso de JARVIS admite únicamente mensajes de texto.")
            return
        prompt = text.strip()
        if prompt in {"/start", "/help"}:
            self.telegram.send_text(
                numeric_chat_id,
                "Lilith / JARVIS en línea. Puedes conversar, buscar información con fuentes y consultar el servidor en lenguaje natural.",
            )
            return
        started = time.monotonic()
        try:
            self.telegram.send_chat_action(numeric_chat_id)
            answer = self.jarvis.ask(prompt, self.sessions.for_chat(numeric_chat_id))
        except JarvisUnavailable as exc:
            answer = f"No he podido consultar JARVIS.\n\nDetalle: {exc}"
        for chunk in split_message(answer):
            self.telegram.send_text(numeric_chat_id, chunk)
        logger.info(
            "Update handled chat_id=%s latency_ms=%d response_chars=%d",
            numeric_chat_id,
            int((time.monotonic() - started) * 1000),
            len(answer),
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS Telegram text gateway")
    parser.add_argument("--check", action="store_true", help="validate config and connectivity, then exit")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    gateway = Gateway(settings)
    if args.check:
        identity = gateway.telegram.get_me()
        if not settings.socket_path.exists():
            print(f"Configuration valid, Telegram bot @{identity.get('username', '?')} reachable, JARVIS socket missing")
            return 1
        print(f"Configuration valid, Telegram bot @{identity.get('username', '?')} reachable, JARVIS socket ready")
        return 0
    signal.signal(signal.SIGTERM, gateway.stop)
    signal.signal(signal.SIGINT, gateway.stop)
    gateway.run()
    logger.info("Gateway stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
