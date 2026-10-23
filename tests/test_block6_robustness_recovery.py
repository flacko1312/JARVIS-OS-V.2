"""Block 6 regression tests for bounded cleanup and recovery paths."""

from __future__ import annotations

import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from actions.browser_control import _BrowserSession
from api.websocket_client import WebSocketClient


class BrowserLifecycleTests(unittest.TestCase):
    def test_close_stops_event_loop_and_joins_worker_thread(self):
        session = _BrowserSession("test")
        session._async_init = AsyncMock()
        session.start()
        worker = session._thread

        self.assertIsNotNone(worker)
        self.assertTrue(worker.is_alive())
        session.close()

        self.assertFalse(worker.is_alive())
        self.assertIsNone(session._thread)
        self.assertIsNone(session._loop)

    def test_startup_failure_is_reported_and_does_not_leave_worker(self):
        session = _BrowserSession("test")
        session._async_init = AsyncMock(side_effect=RuntimeError("playwright unavailable"))

        with self.assertRaisesRegex(RuntimeError, "failed to start"):
            session.start()

        self.assertFalse(any(
            thread.is_alive() and thread.name == "BrowserThread-test"
            for thread in threading.enumerate()
        ))


class WebSocketCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_is_non_blocking_when_event_queue_is_full(self):
        socket = MagicMock()
        socket.send_json = AsyncMock()
        client = WebSocketClient(socket)
        for index in range(client._events.maxsize):
            client._events.put_nowait({"index": index})

        await asyncio.wait_for(client.close(), timeout=0.1)

        drained = [client._events.get_nowait() for _ in range(client._events.qsize())]
        self.assertIsNone(drained[-1])

    async def test_sender_exits_after_close_sentinel(self):
        socket = MagicMock()
        socket.send_json = AsyncMock()
        client = WebSocketClient(socket)
        sender = asyncio.create_task(client.send_events())

        await client.close()
        await asyncio.wait_for(sender, timeout=0.1)

        socket.send_json.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
