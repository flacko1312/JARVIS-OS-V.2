"""M7: fire-and-forget writer that mirrors JARVIS turns to LILITH Core shared sessions.

Design rules:
  * Optional — disabled when JARVIS_M7_ENABLED is unset or '0'.
  * Lazy session resume: Core session initialized on first write.
  * Fire-and-forget: writes never block the voice pipeline.
  * Fail-open: any LILITH error is logged at DEBUG and silently ignored.
  * Idempotent: each (turn_id, correlation_id) is unique per call.
  * Local store remains the primary durable continuity source.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger("jarvis.m7_writer")

_ENABLED_ENV = "JARVIS_M7_ENABLED"


def is_m7_enabled() -> bool:
    return os.environ.get(_ENABLED_ENV, "").strip() not in ("", "0", "false", "False")


class SharedConversationWriter:
    """Mirror validated JARVIS turns to LILITH Core shared conversations (M7).

    Obtain via ``SharedConversationWriter.from_bridge(bridge, channel=...)``.
    ``channel`` must match a ``ConversationChannel`` value: "windows" or "ubuntu".
    """

    def __init__(self, lilith_client: object, *, channel: str) -> None:
        self._client = lilith_client
        self._channel = channel
        self._session_id: str | None = None
        self._lock = asyncio.Lock()

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def from_bridge(cls, bridge: object, *, channel: str) -> "SharedConversationWriter | None":
        """Return a writer given a started LilithBridge, or None if unavailable."""
        if not is_m7_enabled():
            return None
        try:
            client = bridge._runtime.client  # type: ignore[attr-defined]
        except AttributeError:
            return None
        if client is None:
            return None
        return cls(client, channel=channel)

    # ── session management ───────────────────────────────────────────────

    async def _ensure_session(self) -> str | None:
        """Resume or create Core session; return session_id or None on failure."""
        if self._session_id:
            return self._session_id
        async with self._lock:
            if self._session_id:  # double-check after acquiring
                return self._session_id
            try:
                result = await self._client.resume_shared_conversation_session()  # type: ignore[attr-defined]
                session_data = (result or {}).get("session") or result or {}
                sid = str(session_data.get("session_id") or "")
                if sid:
                    self._session_id = sid
                    logger.info(
                        "M7: resumed/created Core session %s (channel=%s)",
                        sid[:8], self._channel,
                    )
                    return sid
            except Exception as exc:
                logger.debug("M7: session init failed (%s): %s", type(exc).__name__, exc)
        return None

    # ── turn write ───────────────────────────────────────────────────────

    async def write_turn(self, role: str, text: str) -> None:
        """Append one complete turn to the Core shared session; never raises."""
        if not text:
            return
        try:
            session_id = await self._ensure_session()
            if not session_id:
                return
            await self._client.append_shared_conversation_turn(  # type: ignore[attr-defined]
                session_id=session_id,
                turn_id=str(uuid4()),
                correlation_id=str(uuid4()),
                channel=self._channel,
                role=role,
                text=text[:8000],
                occurred_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.debug("M7: turn write failed (%s): %s", type(exc).__name__, exc)

    # ── history fetch ────────────────────────────────────────────────────

    async def fetch_history(self, *, limit: int = 50) -> list[dict]:
        """Return Core history for session restore; returns [] on any failure."""
        try:
            session_id = await self._ensure_session()
            if not session_id:
                return []
            return await self._client.get_shared_conversation_turns(  # type: ignore[attr-defined]
                session_id, limit=limit,
            )
        except Exception as exc:
            logger.debug("M7: history fetch failed (%s): %s", type(exc).__name__, exc)
            return []
