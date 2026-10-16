"""Tests for Event Bus — Phase 2 of GREEN Foundation."""
from __future__ import annotations

import os
import unittest

from core.green.event_bus import Event, EventBus, EventType


class TestEvent(unittest.TestCase):
    def test_valid_construction(self):
        e = Event(event_type=EventType.TOOL_STARTED, data={"tool": "test"})
        assert e.event_type == EventType.TOOL_STARTED
        assert e.data == {"tool": "test"}
        assert e.timestamp > 0

    def test_rejects_invalid_type(self):
        with self.assertRaises(TypeError):
            Event(event_type="not_an_enum")  # type: ignore[arg-type]

    def test_default_data(self):
        e = Event(event_type=EventType.TURN_STARTED)
        assert e.data == {}


class TestEventBus(unittest.TestCase):
    def setUp(self):
        import core.green.event_bus as mod
        self._orig = mod.EVENT_BUS_ENABLED
        mod.EVENT_BUS_ENABLED = True
        self.bus = EventBus()

    def tearDown(self):
        import core.green.event_bus as mod
        mod.EVENT_BUS_ENABLED = self._orig

    def test_subscribe_and_emit(self):
        received = []
        self.bus.subscribe(EventType.TOOL_STARTED, lambda e: received.append(e))
        event = Event(event_type=EventType.TOOL_STARTED, data={"tool": "x"})
        self.bus.emit(event)
        assert len(received) == 1
        assert received[0] is event

    def test_unsubscribe(self):
        received = []
        handler = lambda e: received.append(e)
        self.bus.subscribe(EventType.TOOL_STARTED, handler)
        self.bus.unsubscribe(EventType.TOOL_STARTED, handler)
        self.bus.emit(Event(event_type=EventType.TOOL_STARTED))
        assert len(received) == 0

    def test_unsubscribe_missing(self):
        self.bus.unsubscribe(EventType.TOOL_STARTED, lambda e: None)

    def test_zero_subscribers(self):
        self.bus.emit(Event(event_type=EventType.TURN_STARTED))

    def test_multiple_subscribers(self):
        results = []
        self.bus.subscribe(EventType.TOOL_COMPLETED, lambda e: results.append("a"))
        self.bus.subscribe(EventType.TOOL_COMPLETED, lambda e: results.append("b"))
        self.bus.emit(Event(event_type=EventType.TOOL_COMPLETED))
        assert results == ["a", "b"]

    def test_subscriber_exception_isolated(self):
        results = []

        def bad_handler(e: Event) -> None:
            raise RuntimeError("boom")

        def good_handler(e: Event) -> None:
            results.append("ok")

        self.bus.subscribe(EventType.TOOL_FAILED, bad_handler)
        self.bus.subscribe(EventType.TOOL_FAILED, good_handler)
        self.bus.emit(Event(event_type=EventType.TOOL_FAILED))
        assert results == ["ok"]

    def test_duplicate_subscription_ignored(self):
        handler = lambda e: None
        self.bus.subscribe(EventType.TURN_STARTED, handler)
        self.bus.subscribe(EventType.TURN_STARTED, handler)
        assert self.bus.handler_count(EventType.TURN_STARTED) == 1

    def test_handler_count(self):
        assert self.bus.handler_count(EventType.TURN_STARTED) == 0
        self.bus.subscribe(EventType.TURN_STARTED, lambda e: None)
        assert self.bus.handler_count(EventType.TURN_STARTED) == 1

    def test_clear(self):
        self.bus.subscribe(EventType.TURN_STARTED, lambda e: None)
        self.bus.clear()
        assert self.bus.handler_count(EventType.TURN_STARTED) == 0

    def test_disabled_does_not_emit(self):
        import core.green.event_bus as mod
        mod.EVENT_BUS_ENABLED = False
        received = []
        self.bus.subscribe(EventType.TOOL_STARTED, lambda e: received.append(e))
        self.bus.emit(Event(event_type=EventType.TOOL_STARTED))
        assert len(received) == 0

    def test_different_event_types_independent(self):
        results_a = []
        results_b = []
        self.bus.subscribe(EventType.TOOL_STARTED, lambda e: results_a.append(1))
        self.bus.subscribe(EventType.TOOL_COMPLETED, lambda e: results_b.append(1))
        self.bus.emit(Event(event_type=EventType.TOOL_STARTED))
        assert len(results_a) == 1
        assert len(results_b) == 0

    def test_event_source(self):
        received = []
        self.bus.subscribe(EventType.TRACE_COMPLETED, lambda e: received.append(e))
        self.bus.emit(Event(event_type=EventType.TRACE_COMPLETED, source="test"))
        assert received[0].source == "test"


if __name__ == "__main__":
    unittest.main()
