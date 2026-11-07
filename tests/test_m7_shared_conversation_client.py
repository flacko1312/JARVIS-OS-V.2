"""M7 Windows: contract-only tests, without network or audio devices."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from lilith_client.client import LilithClient


class _CaptureClient(LilithClient):
    def __init__(self):
        self.calls = []

    async def _request(self, method, path, *, json=None):
        self.calls.append((method, path, json))
        if method == "GET":
            return {"ok": True, "turns": [{"sequence": 4, "text": "hola"}]}
        return {"ok": True, "session": {"session_id": "core-id"}}


class TestM7WindowsClient(unittest.IsolatedAsyncioTestCase):
    async def test_create_session(self):
        client = _CaptureClient()
        await client.create_shared_conversation_session()
        self.assertEqual(
            client.calls,
            [("POST", "/api/v1/shared-conversations/sessions", None)],
        )

    async def test_resume_session(self):
        client = _CaptureClient()
        await client.resume_shared_conversation_session()
        self.assertEqual(
            client.calls,
            [("POST", "/api/v1/shared-conversations/sessions/resume", None)],
        )

    async def test_append_has_channel_role_and_no_client_owned_actor(self):
        client = _CaptureClient()
        values = {
            "session_id": str(uuid4()),
            "turn_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "channel": "windows",
            "role": "user",
            "text": "continuar conversacion",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        await client.append_shared_conversation_turn(**values)
        method, path, payload = client.calls[0]
        self.assertEqual((method, path), ("POST", "/api/v1/shared-conversations/turns"))
        self.assertEqual(payload, values)
        self.assertNotIn("actor_id", payload)
        self.assertNotIn("sequence", payload)
        self.assertNotIn("side_effect_reviewed", payload)

    async def test_recent_turns(self):
        client = _CaptureClient()
        session_id = str(uuid4())
        turns = await client.get_shared_conversation_turns(session_id, limit=15)
        self.assertEqual(turns, [{"sequence": 4, "text": "hola"}])
        self.assertEqual(
            client.calls,
            [("GET", f"/api/v1/shared-conversations/sessions/{session_id}/turns?limit=15", None)],
        )


if __name__ == "__main__":
    unittest.main()
