"""LILITH bridge for typed input (JL-W003).

Thin, failure-safe glue between ``JarvisLive.send_text()`` and the existing
``runtime.JarvisRuntime`` (``lilith_client`` + ``router``). It adds NO routing or
HTTP logic of its own; it only decides whether a typed message was *actually
executed by LILITH* (so it must not also be sent to Gemini) or must continue to
Gemini exactly as before.

Design rules:
  * Optional: with ``LILITH_API_URL`` / ``LILITH_API_KEY`` unset the bridge is
    ``None`` and JARVIS behaves exactly as before.
  * Never raises into the caller; every failure means "pass through to Gemini".
  * Pass through (do NOT swallow the text) when LILITH is offline (except HOME, whose
    failure is reported in the HUD so Gemini cannot claim a success), when the router
    has no supported command (HOME without an on/off verb), when the router did not
    handle the text, or on any error.
  * Voice is not routed here (Gemini transcripts arrive too late); see JL-W005.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.lilith_bridge")

# Texts starting with "[" are internal prompts (e.g. "[UI EVENT] ...",
# "[VERIFIED LOCAL SELF-SHUTDOWN] ..."), never user commands for LILITH.
_INTERNAL_PREFIX = "["
_ROUTE_TIMEOUT_SECONDS = 12.0


@dataclass(frozen=True)
class TypedRouteOutcome:
    """Result of offering a typed message to LILITH."""

    handled: bool                 # True: LILITH executed it; do NOT send to Gemini
    message: str | None = None    # text to show in the HUD when handled
    notice: str | None = None     # optional HUD note when passing through
    reason: str = ""              # short machine-readable reason (logs/tests)
    domain: str = ""


_PASS = TypedRouteOutcome(handled=False)


def _format_message(result: dict[str, Any]) -> str:
    """Human text for a handled result (the router often returns data only)."""
    if result.get("message"):
        return str(result["message"])
    data = result.get("data")
    if isinstance(data, list):                      # memory search
        if not data:
            return "No encuentro nada en la memoria de LILITH sobre eso."
        lines = []
        for item in data[:3]:
            if isinstance(item, dict):
                # Real /memory/search items: {key, score, source, text, ts}
                text = (item.get("text") or item.get("value") or item.get("content")
                        or item.get("key") or item)
            else:
                text = item
            lines.append(f"- {text}")
        return "Memoria de LILITH:\n" + "\n".join(lines)
    if isinstance(data, dict):
        if data.get("entity_id") and data.get("action"):     # home action
            return f"Hecho: {data['action']} en {data['entity_id']}."
        return "Guardado en la memoria de LILITH."          # memory store
    return "Hecho."


class LilithBridge:
    """Owns one ``JarvisRuntime`` inside the existing asyncio lifecycle."""

    def __init__(self, runtime: Any, *, route_timeout: float = _ROUTE_TIMEOUT_SECONDS):
        self._runtime = runtime
        self._timeout = route_timeout
        self._started = False

    # ── construction ────────────────────────────────────────────────────
    @classmethod
    def from_env(cls) -> "LilithBridge | None":
        """Return a bridge, or None when LILITH is not configured/importable."""
        if not (os.environ.get("LILITH_API_URL") and os.environ.get("LILITH_API_KEY")):
            return None
        try:
            from runtime import JarvisRuntime  # lazy: JARVIS must start without httpx
            return cls(JarvisRuntime())
        except Exception as exc:  # noqa: BLE001
            logger.warning("LILITH integration disabled: %s", type(exc).__name__)
            return None

    # ── lifecycle ───────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def lilith_available(self) -> bool:
        try:
            return bool(self._runtime.lilith_available)
        except Exception:  # noqa: BLE001
            return False

    async def start(self) -> bool:
        """Start the runtime/monitor. Never raises; LILITH offline is not an error."""
        try:
            await self._runtime.start()
            self._started = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("LILITH runtime start failed: %s", type(exc).__name__)
            self._started = False
        return self._started

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self._runtime.stop()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LILITH runtime stop failed: %s", type(exc).__name__)
        finally:
            self._started = False

    # ── routing ─────────────────────────────────────────────────────────
    async def route_typed(self, text: str) -> TypedRouteOutcome:
        """Offer typed text to LILITH. ``handled=True`` only if LILITH executed it."""
        text = str(text or "").strip()
        if not self._started or not text or text.startswith(_INTERNAL_PREFIX):
            return _PASS
        try:
            result = await asyncio.wait_for(
                self._runtime.process_input(text), timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001 - includes TimeoutError
            logger.warning("LILITH routing failed (%s); passing through", type(exc).__name__)
            return TypedRouteOutcome(handled=False, reason="error")

        domain = str(result.get("domain", ""))
        if not result.get("handled"):
            return TypedRouteOutcome(handled=False, reason="not_handled", domain=domain)

        data = result.get("data")
        if isinstance(data, dict) and data.get("offline") and domain == "home":
            # Physical control: say it could not be done instead of letting Gemini improvise.
            return TypedRouteOutcome(
                handled=True, reason="lilith_offline", domain=domain,
                message=str(data.get("message") or "LILITH no está disponible. No puedo controlar la casa ahora."),
            )
        if isinstance(data, dict) and data.get("offline"):
            return TypedRouteOutcome(
                handled=False, reason="lilith_offline", domain=domain,
                notice="LILITH no disponible; continúo con Gemini.",
            )
        if isinstance(data, dict) and data.get("needs_clarification"):
            # HOME text without a supported on/off command: LILITH did nothing.
            return TypedRouteOutcome(handled=False, reason="needs_clarification", domain=domain)

        return TypedRouteOutcome(
            handled=True, message=_format_message(result), reason="handled", domain=domain,
        )