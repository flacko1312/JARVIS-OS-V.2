"""M3 WebSocket transport tests: never contact Core or restart AURORA."""
import asyncio
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from lilith_client.adapter_connector import ADAPTER_ID, AdapterConnector


class _FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []
        self.recv_calls = 0

    async def recv(self):
        self.recv_calls += 1
        if not self.messages:
            raise AssertionError("Unexpected recv() after goodbye")
        return json.dumps(self.messages.pop(0))

    async def send(self, text):
        self.sent.append(json.loads(text))


def _invoke():
    return {
        "type": "invoke",
        "request_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "adapter_id": ADAPTER_ID,
        "capability_id": "windows.system.metrics.read",
        "parameters": {},
        "required_scope": "system.read",
        "deadline": (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
    }


class TestM3WebSocketReceiver(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_ack_and_invoke_use_same_receiver(self):
        msg = _invoke()
        ws = _FakeWebSocket([{"type": "heartbeat_ack", "sequence": 1},
                             msg, {"type": "goodbye"}])
        connector = AdapterConnector()
        with patch.dict(os.environ, {"ADAPTER_INVOKE_READONLY_ENABLED": "true"}), \
             patch("lilith_client.adapter_connector._execute_windows_capability",
                   return_value={"cpu_percent": 9}):
            await asyncio.wait_for(connector._connected_loop(ws), timeout=2)
        self.assertEqual(ws.recv_calls, 3)
        self.assertEqual(connector.stats["heartbeats_acked"], 1)
        results = [item for item in ws.sent if item.get("type") == "result"]
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["request_id"], msg["request_id"])
        self.assertEqual(results[0]["result"], {"cpu_percent": 9})

    async def test_invoke_disabled_preserves_connection_and_returns_denial(self):
        msg = _invoke()
        ws = _FakeWebSocket([msg, {"type": "goodbye"}])
        connector = AdapterConnector()
        with patch.dict(os.environ, {"ADAPTER_INVOKE_READONLY_ENABLED": "false"}):
            await asyncio.wait_for(connector._connected_loop(ws), timeout=2)
        results = [item for item in ws.sent if item.get("type") == "result"]
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["error_code"], "invoke_disabled")
