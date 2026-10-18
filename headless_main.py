"""Entry point for JARVIS Headless — Ubuntu server, no GUI.

Usage:
    python headless_main.py

Required environment variables:
    GEMINI_API_KEY          Gemini API key
    LILITH_API_URL          (optional) LILITH endpoint
    LILITH_API_KEY          (optional) LILITH integration token
    XDG_RUNTIME_DIR         (required on Linux for PulseAudio/ALSA)

The process runs JarvisLive with a HeadlessClient (no PyQt, no display).
It starts the conversation immediately — no startup-clap gate.
"""
from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass


def _setup_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG)

    fh = logging.handlers.RotatingFileHandler(
        log_dir / "jarvis-headless.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "[%(levelname)s] %(name)s: %(message)s"
    ))

    root.addHandler(fh)
    root.addHandler(ch)


def headless_conversation_store_path() -> Path:
    """Return a conversation store path separate from the desktop instance."""
    return BASE_DIR / "memory" / "conversation_state_headless.json"


def main() -> None:
    _load_dotenv()
    _setup_logging()
    logger = logging.getLogger("jarvis.headless")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.error("GEMINI_API_KEY not set. Cannot start.")
        sys.exit(1)

    from headless_client import HeadlessClient
    from main import JarvisLive, _load_voice_name

    client = HeadlessClient()
    voice_name = _load_voice_name()
    store_path = headless_conversation_store_path()

    jarvis = JarvisLive(
        client,
        voice_name,
        headless=True,
        api_key=api_key,
        conversation_store_path=store_path,
    )

    shutdown_event = asyncio.Event()

    def _signal_handler(signum, frame):
        logger.info("Signal %s received, shutting down...", signum)
        jarvis.request_shutdown()
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    jarvis.start_conversation()

    logger.info(
        "JARVIS Headless starting: voice=%s store=%s tools=%d",
        voice_name, store_path, len(jarvis.tool_declarations),
    )

    try:
        asyncio.run(jarvis.run())
    except KeyboardInterrupt:
        logger.info("Interrupted.")
    except Exception:
        logger.exception("Fatal error in headless main loop")
        sys.exit(1)

    logger.info("JARVIS Headless stopped.")


if __name__ == "__main__":
    main()
