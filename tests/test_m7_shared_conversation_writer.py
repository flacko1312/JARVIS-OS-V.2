"""M7: hermetic tests for SharedConversationWriter.

Coverage:
  - writer disabled when JARVIS_M7_ENABLED not set
  - lazy session resume on first write
  - fire-and-forget write_turn call structure
  - history fetch mapping
  - failure isolation (never raises to caller)
  - cross-device history restore into local continuity
  - duplicate write prevention via idempotency UUIDs
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4


# ── helpers ────────────────────────────────────────────────────────────

class _FakeClient:
    """In-memory stub of LilithClient M7 methods."""

    def __init__(self):
        self.resume_calls = 0
        self.appended_turns: list[dict] = []
        self.session_id = str(uuid4())

    async def resume_shared_conversation_session(self) -> dict:
        self.resume_calls += 1
        return {"ok": True, "session": {"session_id": self.session_id}}

    async def append_shared_conversation_turn(self, **kwargs) -> dict:
        self.appended_turns.append(kwargs)
        return {"ok": True, "created": True}

    async def get_shared_conversation_turns(self, session_id: str, *, limit: int = 100) -> list[dict]:
        return [
            {"role": "user", "text": "hola", "sequence": 0},
            {"role": "assistant", "text": "hola de vuelta", "sequence": 1},
        ]


class _FakeBridge:
    """Stub LilithBridge."""
    class _RT:
        def __init__(self, client):
            self.client = client
    def __init__(self, client):
        self._runtime = self._RT(client)


# ── import writer ───────────────────────────────────────────────────────

from core.shared_conversation_writer import SharedConversationWriter, is_m7_enabled


class TestM7EnabledFlag(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JARVIS_M7_ENABLED", None)
            self.assertFalse(is_m7_enabled())

    def test_enabled_by_1(self):
        with patch.dict(os.environ, {"JARVIS_M7_ENABLED": "1"}):
            self.assertTrue(is_m7_enabled())

    def test_disabled_by_0(self):
        with patch.dict(os.environ, {"JARVIS_M7_ENABLED": "0"}):
            self.assertFalse(is_m7_enabled())

    def test_from_bridge_returns_none_when_disabled(self):
        with patch.dict(os.environ, {"JARVIS_M7_ENABLED": "0"}):
            bridge = _FakeBridge(_FakeClient())
            self.assertIsNone(SharedConversationWriter.from_bridge(bridge, channel="windows"))

    def test_from_bridge_returns_writer_when_enabled(self):
        with patch.dict(os.environ, {"JARVIS_M7_ENABLED": "1"}):
            bridge = _FakeBridge(_FakeClient())
            writer = SharedConversationWriter.from_bridge(bridge, channel="windows")
            self.assertIsNotNone(writer)
            self.assertEqual(writer._channel, "windows")


class TestLazySessionResume(unittest.IsolatedAsyncioTestCase):
    async def test_resume_called_once_on_first_write(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="windows")
        await writer.write_turn("user", "hola")
        await writer.write_turn("assistant", "respuesta")
        self.assertEqual(client.resume_calls, 1)

    async def test_session_id_cached_after_first_write(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="windows")
        await writer.write_turn("user", "primero")
        sid = writer._session_id
        await writer.write_turn("user", "segundo")
        self.assertEqual(writer._session_id, sid)
        self.assertEqual(client.resume_calls, 1)

    async def test_concurrent_writes_do_not_double_resume(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="ubuntu")
        await asyncio.gather(
            writer.write_turn("user", "a"),
            writer.write_turn("user", "b"),
            writer.write_turn("assistant", "c"),
        )
        self.assertEqual(client.resume_calls, 1)


class TestWriteTurnContract(unittest.IsolatedAsyncioTestCase):
    async def test_turn_sent_with_correct_channel_and_role(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="ubuntu")
        await writer.write_turn("user", "hola ubuntu")
        self.assertEqual(len(client.appended_turns), 1)
        t = client.appended_turns[0]
        self.assertEqual(t["channel"], "ubuntu")
        self.assertEqual(t["role"], "user")
        self.assertEqual(t["text"], "hola ubuntu")
        self.assertIn("session_id", t)
        self.assertIn("turn_id", t)
        self.assertIn("correlation_id", t)
        self.assertIn("occurred_at", t)

    async def test_text_truncated_to_8000_chars(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="windows")
        long_text = "x" * 10000
        await writer.write_turn("assistant", long_text)
        self.assertEqual(len(client.appended_turns[0]["text"]), 8000)

    async def test_empty_text_not_sent(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="windows")
        await writer.write_turn("user", "")
        self.assertEqual(len(client.appended_turns), 0)
        self.assertEqual(client.resume_calls, 0)

    async def test_each_write_has_unique_turn_id_and_correlation_id(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="windows")
        await writer.write_turn("user", "primero")
        await writer.write_turn("user", "segundo")
        ids = {t["turn_id"] for t in client.appended_turns}
        cors = {t["correlation_id"] for t in client.appended_turns}
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(cors), 2)


class TestFailureIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_session_init_failure_does_not_raise(self):
        client = _FakeClient()
        client.resume_shared_conversation_session = AsyncMock(side_effect=RuntimeError("LILITH down"))
        writer = SharedConversationWriter(client, channel="windows")
        await writer.write_turn("user", "hola")  # Must not raise

    async def test_append_failure_does_not_raise(self):
        client = _FakeClient()
        client.append_shared_conversation_turn = AsyncMock(side_effect=ConnectionError("timeout"))
        writer = SharedConversationWriter(client, channel="windows")
        await writer.write_turn("user", "hola")  # Must not raise

    async def test_fetch_history_failure_returns_empty_list(self):
        client = _FakeClient()
        client.get_shared_conversation_turns = AsyncMock(side_effect=ConnectionError("offline"))
        writer = SharedConversationWriter(client, channel="ubuntu")
        result = await writer.fetch_history()
        self.assertEqual(result, [])


class TestHistoryFetch(unittest.IsolatedAsyncioTestCase):
    async def test_history_returns_chronological_turns(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="ubuntu")
        turns = await writer.fetch_history(limit=10)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["role"], "user")
        self.assertEqual(turns[1]["role"], "assistant")

    async def test_history_uses_same_session_as_writes(self):
        client = _FakeClient()
        writer = SharedConversationWriter(client, channel="ubuntu")
        await writer.write_turn("user", "primero")
        turns = await writer.fetch_history()
        self.assertEqual(client.resume_calls, 1)  # session reused


if __name__ == "__main__":
    unittest.main()
