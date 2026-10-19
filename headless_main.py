"""Entry point for JARVIS Headless — Ubuntu server, no GUI.

Usage:
    python headless_main.py [--no-audio]

Required environment variables:
    GEMINI_API_KEY          Gemini API key
    LILITH_API_URL          (optional) LILITH endpoint
    LILITH_API_KEY          (optional) LILITH integration token
    XDG_RUNTIME_DIR         (required on Linux for PulseAudio/ALSA, unless --no-audio)

The process runs JarvisLive with a HeadlessClient (no PyQt, no display).
It starts the conversation immediately — no startup-clap gate.
"""
from __future__ import annotations

import argparse
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS Headless runtime")
    parser.add_argument(
        "--no-audio", action="store_true",
        help="Start without microphone or speaker (text-only Gemini session)",
    )
    return parser.parse_args()


_LOCK_PATH = BASE_DIR / ".headless.pid"


def _acquire_instance_lock() -> bool:
    """Ensure only one headless_main.py runs at a time via a PID lockfile."""
    if _LOCK_PATH.exists():
        try:
            old_pid = int(_LOCK_PATH.read_text().strip())
            if sys.platform == "linux":
                os.kill(old_pid, 0)
                return False
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
    _LOCK_PATH.write_text(str(os.getpid()))
    return True


def _release_instance_lock() -> None:
    try:
        if _LOCK_PATH.exists() and _LOCK_PATH.read_text().strip() == str(os.getpid()):
            _LOCK_PATH.unlink()
    except OSError:
        pass


def main() -> None:
    args = _parse_args()
    _load_dotenv()
    _setup_logging()
    logger = logging.getLogger("jarvis.headless")

    if not _acquire_instance_lock():
        logger.error(
            "Another headless_main.py is already running (PID in %s). Aborting.",
            _LOCK_PATH,
        )
        sys.exit(1)

    if not args.no_audio and sys.platform == "linux" and not os.environ.get("XDG_RUNTIME_DIR"):
        os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
        logger.info("XDG_RUNTIME_DIR not set; defaulting to %s", os.environ["XDG_RUNTIME_DIR"])

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
        no_audio=args.no_audio,
        api_key=api_key,
        conversation_store_path=store_path,
    )

    def _signal_handler(signum, frame):
        logger.info("Signal %s received, shutting down...", signum)
        jarvis.request_shutdown()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    import health_server
    health_server.start(jarvis)
    from core.voice_stability import get_monitor as _get_voice_monitor
    _get_voice_monitor().start()
    logger.info("Health server listening on 127.0.0.1:%d", 7470)

    jarvis.start_conversation()

    logger.info(
        "JARVIS Headless starting: voice=%s store=%s tools=%d no_audio=%s",
        voice_name, store_path, len(jarvis.tool_declarations), args.no_audio,
    )

    try:
        asyncio.run(jarvis.run())
    except KeyboardInterrupt:
        logger.info("Interrupted.")
    except Exception:
        logger.exception("Fatal error in headless main loop")
        _release_instance_lock()
        sys.exit(1)

    _release_instance_lock()
    logger.info("JARVIS Headless stopped.")


if __name__ == "__main__":
    main()
