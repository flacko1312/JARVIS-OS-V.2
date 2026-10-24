from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Any

from telegram_gateway.auth import ChatAuthorizer
from telegram_gateway.config import ConfigurationError, Settings
from telegram_gateway.formatter import telegram_html_chunks
from telegram_gateway.jarvis_client import JarvisTextClient, JarvisUnavailable
from telegram_gateway.sessions import OffsetStore, SessionStore
from telegram_gateway.telegram_client import TelegramClient, TelegramError

logger = logging.getLogger("jarvis.telegram")

WELCOME_TEXT = """**Lilith / JARVIS está en línea.**

Escríbeme con naturalidad. Mantengo el contexto de la conversación y puedo:
- responder preguntas generales;
- buscar información actual con fuentes reales;
- consultar CPU, memoria, discos, temperaturas y procesos;
- revisar systemd, Docker, PostgreSQL, Mosquitto, Ollama y logs;
- recuperar el contexto de proyectos JARVIS / LILITH.

Este canal es privado, de solo texto y de diagnóstico seguro. Usa /help para ver ejemplos."""

HELP_TEXT = """**Cómo usar Lilith / JARVIS**

No necesitas memorizar comandos: pregunta en lenguaje natural.

**Ejemplos**
- ¿Cómo está el servidor?
- ¿Está PostgreSQL funcionando?
- Revisa los últimos errores de JARVIS.
- Busca la última versión estable de Docker y cita las fuentes.
- ¿Qué estábamos haciendo con JARVIS Ubuntu?

**Comandos mínimos**
/start — presentación
/help — esta ayuda
/estado — diagnóstico general del servidor

Por seguridad no ejecuto órdenes shell arbitrarias recibidas por Telegram."""


class GatewayStopped(Exception):
    """Internal control flow used to interrupt a blocking long-poll on shutdown."""


class TypingIndicator:
    """Refresh Telegram's short-lived typing state while JARVIS is working."""

    def __init__(self, telegram: TelegramClient, chat_id: int, interval: float = 4.0):
        self.telegram = telegram
        self.chat_id = chat_id
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _send(self) -> None:
        try:
            self.telegram.send_chat_action(self.chat_id)
        except TelegramError as exc:
            logger.debug("Unable to refresh typing indicator: %s", exc)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._send()

    def __enter__(self) -> TypingIndicator:
        self._send()
        self._thread = threading.Thread(target=self._run, name="telegram-typing", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)


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
        # Exit as soon as Python can deliver the signal instead of resuming polling;
        # this keeps systemd shutdown within the configured timeout.
        if _args:
            raise GatewayStopped

    def send_answer(self, chat_id: int, answer: str) -> None:
        for chunk in telegram_html_chunks(answer):
            self.telegram.send_text(chat_id, chunk, parse_mode="HTML")

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
            self.send_answer(numeric_chat_id, "Este acceso de JARVIS admite únicamente mensajes de texto.")
            return
        prompt = text.strip()
        command = prompt.split(maxsplit=1)[0].split("@", 1)[0].lower()
        if command == "/start":
            self.send_answer(numeric_chat_id, WELCOME_TEXT)
            return
        if command in {"/help", "/ayuda"}:
            self.send_answer(numeric_chat_id, HELP_TEXT)
            return
        if command == "/estado":
            prompt = "Dame un diagnóstico general y conciso del estado actual del servidor JARVIS Ubuntu."
        started = time.monotonic()
        try:
            with TypingIndicator(self.telegram, numeric_chat_id):
                answer = self.jarvis.ask(prompt, self.sessions.for_chat(numeric_chat_id))
        except JarvisUnavailable:
            logger.exception("JARVIS unavailable for authorized Telegram request")
            answer = (
                "JARVIS está temporalmente no disponible. El gateway sigue conectado; "
                "inténtalo de nuevo en unos segundos."
            )
        self.send_answer(numeric_chat_id, answer)
        logger.info(
            "Update handled chat_id=%s latency_ms=%d response_chars=%d",
            numeric_chat_id,
            int((time.monotonic() - started) * 1000),
            len(answer),
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS Telegram text gateway")
    parser.add_argument("--check", action="store_true", help="validate config and connectivity, then exit")
    parser.add_argument(
        "--configure-profile",
        action="store_true",
        help="apply and verify the canonical Telegram bot profile, then exit",
    )
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
    if args.configure_profile:
        gateway.telegram.configure_profile()
        profile = gateway.telegram.get_profile()
        identity = profile["identity"]
        print(
            f"Profile configured for @{identity.get('username', '?')}: "
            f"{len(profile['commands'])} commands verified"
        )
        return 0
    if args.check:
        identity = gateway.telegram.get_me()
        if not settings.socket_path.exists():
            print(f"Configuration valid, Telegram bot @{identity.get('username', '?')} reachable, JARVIS socket missing")
            return 1
        print(f"Configuration valid, Telegram bot @{identity.get('username', '?')} reachable, JARVIS socket ready")
        return 0
    signal.signal(signal.SIGTERM, gateway.stop)
    signal.signal(signal.SIGINT, gateway.stop)
    try:
        gateway.run()
    except GatewayStopped:
        pass
    logger.info("Gateway stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
