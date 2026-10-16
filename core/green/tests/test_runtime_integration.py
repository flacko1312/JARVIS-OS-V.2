"""Tests for GREEN runtime bridge — Phases 1+2 (ExecutionTrace + Event Bus)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

from core.green.runtime import (
    get_trace_store,
    get_event_bus,
    trace_tool_start,
    trace_tool_complete,
    trace_tool_failed,
    emit_turn_started,
    emit_turn_completed,
    emit_tool_authorized,
    emit_tool_rejected,
    emit_lilith_requested,
    emit_lilith_completed,
    emit_lilith_failed,
    _emit_safe,
)
from core.green.execution_trace import TraceStatus
from core.green.event_bus import EventType

# Patches must target the SOURCE module where the flag lives,
# since runtime.py reads it dynamically via the module reference.
_TRACE_FLAG = "core.green.execution_trace.TRACE_ENABLED"
_BUS_FLAG = "core.green.event_bus.EVENT_BUS_ENABLED"


class TestTraceToolLifecycle(unittest.TestCase):
    def setUp(self):
        self.store = get_trace_store()
        self.store.clear()

    @patch(_TRACE_FLAG, True)
    def test_start_creates_trace(self):
        trace = trace_tool_start(
            tool_name="open_app",
            tool_arguments={"app_name": "Chrome"},
            function_call_id="fc_123",
            session_id="sess_1",
            turn_id="turn_1",
        )
        assert trace is not None
        assert trace.tool_name == "open_app"
        assert trace.function_call_id == "fc_123"
        assert trace.session_id == "sess_1"
        assert trace.turn_id == "turn_1"
        assert trace.status == TraceStatus.STARTED

    @patch(_TRACE_FLAG, True)
    def test_complete_finishes_trace(self):
        trace = trace_tool_start(
            tool_name="date_time",
            tool_arguments={"action": "current_time"},
        )
        trace_tool_complete(trace, result_summary="12:00:00")
        assert trace.status == TraceStatus.COMPLETED
        assert trace.result_summary == "12:00:00"
        assert trace.duration_ms is not None
        assert trace.duration_ms >= 0

    @patch(_TRACE_FLAG, True)
    def test_failed_records_error(self):
        trace = trace_tool_start(
            tool_name="file_controller",
            tool_arguments={"action": "read"},
        )
        error = FileNotFoundError("not found")
        trace_tool_failed(trace, error=error)
        assert trace.status == TraceStatus.FAILED
        assert trace.error_type == "FileNotFoundError"
        assert "not found" in trace.error_message

    @patch(_TRACE_FLAG, True)
    def test_trace_stored(self):
        before = len(self.store)
        trace_tool_start(
            tool_name="web_search",
            tool_arguments={"query": "test"},
        )
        assert len(self.store) > before

    @patch(_TRACE_FLAG, False)
    def test_disabled_returns_none(self):
        trace = trace_tool_start(
            tool_name="open_app",
            tool_arguments={},
        )
        assert trace is None

    @patch(_TRACE_FLAG, True)
    def test_complete_on_none_is_noop(self):
        trace_tool_complete(None, result_summary="test")

    @patch(_TRACE_FLAG, True)
    def test_failed_on_none_is_noop(self):
        trace_tool_failed(None, error=RuntimeError("boom"))

    @patch(_TRACE_FLAG, True)
    def test_secret_redaction_in_trace(self):
        trace = trace_tool_start(
            tool_name="email_control",
            tool_arguments={"password": "secret123", "action": "connect"},
        )
        assert trace is not None
        assert "secret123" not in str(trace.tool_arguments)
        assert "***REDACTED***" in str(trace.tool_arguments)

    @patch(_TRACE_FLAG, True)
    def test_no_routing_change(self):
        trace = trace_tool_start(
            tool_name="open_app",
            tool_arguments={"app_name": "Chrome"},
        )
        assert trace.router_decision is None
        assert trace.authorization_result is None


class TestEventBusIntegration(unittest.TestCase):
    def setUp(self):
        self.bus = get_event_bus()
        self.received: list = []
        self._handlers_to_clean: list[tuple] = []

    def tearDown(self):
        for event_type, handler in self._handlers_to_clean:
            self.bus.unsubscribe(event_type, handler)

    def _subscribe(self, event_type):
        handler = lambda e: self.received.append(e)
        self.bus.subscribe(event_type, handler)
        self._handlers_to_clean.append((event_type, handler))
        return handler

    @patch(_BUS_FLAG, True)
    def test_turn_started_event(self):
        self._subscribe(EventType.TURN_STARTED)
        emit_turn_started(session_id="s1", turn_id="t1", source="voice")
        assert len(self.received) == 1
        assert self.received[0].data["session_id"] == "s1"

    @patch(_BUS_FLAG, True)
    def test_turn_completed_event(self):
        self._subscribe(EventType.TURN_COMPLETED)
        emit_turn_completed(session_id="s1", turn_id="t1")
        assert len(self.received) == 1

    @patch(_BUS_FLAG, True)
    def test_tool_authorized_event(self):
        self._subscribe(EventType.TOOL_AUTHORIZED)
        emit_tool_authorized(tool_name="open_app", function_call_id="fc1")
        assert len(self.received) == 1
        assert self.received[0].data["tool_name"] == "open_app"

    @patch(_BUS_FLAG, True)
    def test_tool_rejected_event(self):
        self._subscribe(EventType.TOOL_REJECTED)
        emit_tool_rejected(tool_name="computer_control", function_call_id="fc2", reason="qa_blocked")
        assert len(self.received) == 1
        assert self.received[0].data["reason"] == "qa_blocked"

    @patch(_BUS_FLAG, True)
    @patch(_TRACE_FLAG, True)
    def test_tool_started_event_from_trace(self):
        self._subscribe(EventType.TOOL_STARTED)
        store = get_trace_store()
        store.clear()
        trace_tool_start(
            tool_name="web_search",
            tool_arguments={"query": "test"},
        )
        assert len(self.received) == 1
        assert self.received[0].data["tool_name"] == "web_search"

    @patch(_BUS_FLAG, True)
    @patch(_TRACE_FLAG, True)
    def test_tool_completed_event_from_trace(self):
        self._subscribe(EventType.TOOL_COMPLETED)
        trace = trace_tool_start(
            tool_name="date_time",
            tool_arguments={},
        )
        trace_tool_complete(trace, result_summary="ok")
        assert len(self.received) == 1
        assert self.received[0].data["tool_name"] == "date_time"

    @patch(_BUS_FLAG, True)
    @patch(_TRACE_FLAG, True)
    def test_tool_failed_event_from_trace(self):
        self._subscribe(EventType.TOOL_FAILED)
        trace = trace_tool_start(
            tool_name="file_controller",
            tool_arguments={},
        )
        trace_tool_failed(trace, error=RuntimeError("boom"))
        assert len(self.received) == 1
        assert self.received[0].data["error_type"] == "RuntimeError"

    @patch(_BUS_FLAG, False)
    def test_disabled_bus_no_events(self):
        self._subscribe(EventType.TURN_STARTED)
        emit_turn_started(session_id="s1", turn_id="t1")
        assert len(self.received) == 0

    @patch(_BUS_FLAG, True)
    def test_subscriber_failure_isolated(self):
        def bad_handler(e):
            raise RuntimeError("handler crash")
        self.bus.subscribe(EventType.TURN_STARTED, bad_handler)
        self._handlers_to_clean.append((EventType.TURN_STARTED, bad_handler))
        emit_turn_started(session_id="s1", turn_id="t1")

    @patch(_BUS_FLAG, True)
    def test_lilith_events(self):
        self._subscribe(EventType.LILITH_REQUESTED)
        self._subscribe(EventType.LILITH_COMPLETED)
        self._subscribe(EventType.LILITH_FAILED)
        emit_lilith_requested(tool_name="lilith_home_action", function_call_id="fc1")
        emit_lilith_completed(tool_name="lilith_home_action", function_call_id="fc1")
        emit_lilith_failed(tool_name="lilith_routine", function_call_id="fc2", error="timeout")
        assert len(self.received) == 3

    @patch(_BUS_FLAG, True)
    def test_no_recursion(self):
        import core.green.runtime as rt
        call_count = 0
        def recursive_handler(e):
            nonlocal call_count
            call_count += 1
            _emit_safe(EventType.TURN_STARTED, {"nested": True})
        self.bus.subscribe(EventType.TURN_STARTED, recursive_handler)
        self._handlers_to_clean.append((EventType.TURN_STARTED, recursive_handler))
        emit_turn_started(session_id="s1", turn_id="t1")
        assert call_count == 1


class TestMainIntegration(unittest.TestCase):
    def test_main_imports_cleanly(self):
        import main
        assert hasattr(main, '_execute_tool') or hasattr(main.JarvisLive, '_execute_tool')

    def test_tool_declarations_count_unchanged(self):
        import main
        assert len(main.TOOL_DECLARATIONS) == 48

    def test_green_runtime_importable(self):
        from core.green import runtime
        assert hasattr(runtime, 'trace_tool_start')
        assert hasattr(runtime, 'emit_turn_started')


class TestDisabledPreservation(unittest.TestCase):
    @patch(_TRACE_FLAG, False)
    @patch(_BUS_FLAG, False)
    def test_all_disabled_no_side_effects(self):
        store = get_trace_store()
        before = len(store)
        trace = trace_tool_start(tool_name="x", tool_arguments={})
        assert trace is None
        assert len(store) == before
        emit_turn_started(session_id="s", turn_id="t")
        emit_tool_authorized(tool_name="x")
        emit_tool_rejected(tool_name="x")


if __name__ == "__main__":
    unittest.main()
