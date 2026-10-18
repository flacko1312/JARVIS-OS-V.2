"""Headless implementation of JarvisClient for Ubuntu server deployment.

No PyQt, no display, no GUI. Logs state transitions and messages to the
standard logging infrastructure so they appear in journalctl when running
under systemd.
"""
from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.headless.client")


class _NullVoiceSelector:
    """Satisfies the VoiceSelector protocol with no-op defaults."""

    def currentIndex(self) -> int:
        return 0

    def itemData(self, index: int) -> Any:
        return None

    def currentText(self) -> str:
        return ""


class HeadlessClient:
    """JarvisClient implementation for headless (no-GUI) operation.

    Implements every method and property required by the JarvisClient Protocol
    defined in core.jarvis_client without importing PyQt or any display library.
    """

    def __init__(self) -> None:
        self._muted = False
        self._mute_lock = threading.Lock()
        self._state = "STANDBY"
        self.on_text_command: Callable[[str], None] | None = None
        self.on_conversation_toggle: Callable[[], bool] | None = None
        self._voice_selector = _NullVoiceSelector()

    @property
    def muted(self) -> bool:
        with self._mute_lock:
            return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        with self._mute_lock:
            self._muted = bool(value)

    @property
    def current_file(self) -> str | None:
        return None

    @property
    def _voice_combo(self) -> _NullVoiceSelector:
        return self._voice_selector

    def write_log(self, text: str) -> None:
        logger.info("%s", text)

    def set_state(self, state: str) -> None:
        prev = self._state
        self._state = str(state).upper()
        if prev != self._state:
            logger.info("STATE %s -> %s", prev, self._state)

    def show_subtitle(self, text: str) -> None:
        if text and text.strip():
            logger.debug("SUBTITLE: %s", text.strip()[:200])

    def clear_subtitle(self) -> None:
        pass

    def set_theme(self, theme_key: str) -> None:
        pass

    def set_graphics_quality(self, quality: str) -> None:
        pass

    def sync_voice_display(self, voice_name: str) -> None:
        logger.debug("VOICE: %s", voice_name)

    def handle_ui_command(self, action: str) -> None:
        logger.debug("UI_COMMAND (ignored in headless): %s", action)

    def toggle_mute(self) -> bool:
        with self._mute_lock:
            self._muted = not self._muted
            logger.info("MUTE %s", "ON" if self._muted else "OFF")
            return self._muted
