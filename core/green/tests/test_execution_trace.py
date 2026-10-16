"""Tests for ExecutionTrace — Phase 1 of GREEN Foundation."""
from __future__ import annotations

import os
import time
import unittest

from core.green.execution_trace import (
    TRACE_ENABLED,
    ExecutionTrace,
    TraceStatus,
    TraceStore,
    redact_secrets,
)


class TestRedactSecrets(unittest.TestCase):
    def test_redacts_password(self):
        d = {"password": "hunter2", "user": "alice"}
        result = redact_secrets(d)
        assert result["password"] == "***REDACTED***"
        assert result["user"] == "alice"

    def test_redacts_nested_dict(self):
        d = {"outer": {"api_key": "abc123", "safe": "ok"}}
        result = redact_secrets(d)
        assert result["outer"]["api_key"] == "***REDACTED***"
        assert result["outer"]["safe"] == "ok"

    def test_redacts_in_list(self):
        d = {"items": [{"token": "xyz"}, {"name": "fine"}]}
        result = redact_secrets(d)
        assert result["items"][0]["token"] == "***REDACTED***"
        assert result["items"][1]["name"] == "fine"

    def test_handles_none(self):
        assert redact_secrets(None) is None

    def test_handles_scalar(self):
        assert redact_secrets(42) == 42
        assert redact_secrets("hello") == "hello"

    def test_depth_limit(self):
        deep = {"a": None}
        current = deep
        for _ in range(25):
            new = {"nested": current}
            current = new
        result = redact_secrets(current)
        assert isinstance(result, dict)

    def test_case_insensitive(self):
        d = {"Authorization": "Bearer xyz", "API_KEY": "secret"}
        result = redact_secrets(d)
        assert result["Authorization"] == "***REDACTED***"
        assert result["API_KEY"] == "***REDACTED***"


class TestExecutionTrace(unittest.TestCase):
    def test_unique_trace_ids(self):
        t1 = ExecutionTrace()
        t2 = ExecutionTrace()
        assert t1.trace_id != t2.trace_id

    def test_parent_child_correlation(self):
        parent = ExecutionTrace()
        child = ExecutionTrace(parent_trace_id=parent.trace_id)
        assert child.parent_trace_id == parent.trace_id

    def test_session_turn_correlation(self):
        t = ExecutionTrace(session_id="s1", turn_id="t1", function_call_id="fc1")
        assert t.session_id == "s1"
        assert t.turn_id == "t1"
        assert t.function_call_id == "fc1"

    def test_timing(self):
        t = ExecutionTrace()
        time.sleep(0.01)
        t.finish()
        assert t.finished_at is not None
        assert t.duration_ms is not None
        assert t.duration_ms > 0
        assert t.status == TraceStatus.COMPLETED

    def test_finish_success(self):
        t = ExecutionTrace()
        t.finish(result_summary="done")
        assert t.status == TraceStatus.COMPLETED
        assert t.result_summary == "done"

    def test_finish_failure(self):
        t = ExecutionTrace()
        t.finish(
            status=TraceStatus.FAILED,
            error_type="RuntimeError",
            error_message="something broke",
        )
        assert t.status == TraceStatus.FAILED
        assert t.error_type == "RuntimeError"
        assert t.error_message == "something broke"

    def test_to_dict_redacts(self):
        t = ExecutionTrace(tool_arguments={"api_key": "secret123", "query": "hello"})
        d = t.to_dict()
        assert d["tool_arguments"]["api_key"] == "***REDACTED***"
        assert d["tool_arguments"]["query"] == "hello"

    def test_to_dict_status_string(self):
        t = ExecutionTrace()
        d = t.to_dict()
        assert d["status"] == "started"

    def test_default_status_started(self):
        t = ExecutionTrace()
        assert t.status == TraceStatus.STARTED

    def test_all_statuses(self):
        for s in TraceStatus:
            t = ExecutionTrace()
            t.finish(status=s)
            assert t.status == s

    def test_malformed_optional_data(self):
        t = ExecutionTrace(
            tool_arguments=None,  # type: ignore[arg-type]
            session_id=None,
            turn_id=None,
        )
        d = t.to_dict()
        assert d["tool_arguments"] is None


class TestTraceStore(unittest.TestCase):
    def setUp(self):
        os.environ["JARVIS_EXECUTION_TRACE_ENABLED"] = "1"
        import core.green.execution_trace as mod
        self._orig = mod.TRACE_ENABLED
        mod.TRACE_ENABLED = True

    def tearDown(self):
        import core.green.execution_trace as mod
        mod.TRACE_ENABLED = self._orig
        os.environ.pop("JARVIS_EXECUTION_TRACE_ENABLED", None)

    def test_record_and_get(self):
        store = TraceStore()
        t = ExecutionTrace()
        store.record(t)
        assert store.get(t.trace_id) is t
        assert len(store) == 1

    def test_get_missing(self):
        store = TraceStore()
        assert store.get("nonexistent") is None

    def test_by_session(self):
        store = TraceStore()
        t1 = ExecutionTrace(session_id="s1")
        t2 = ExecutionTrace(session_id="s2")
        t3 = ExecutionTrace(session_id="s1")
        store.record(t1)
        store.record(t2)
        store.record(t3)
        assert len(store.by_session("s1")) == 2

    def test_by_turn(self):
        store = TraceStore()
        t1 = ExecutionTrace(turn_id="t1")
        t2 = ExecutionTrace(turn_id="t2")
        store.record(t1)
        store.record(t2)
        assert len(store.by_turn("t1")) == 1

    def test_children_of(self):
        store = TraceStore()
        parent = ExecutionTrace()
        child1 = ExecutionTrace(parent_trace_id=parent.trace_id)
        child2 = ExecutionTrace(parent_trace_id=parent.trace_id)
        other = ExecutionTrace()
        store.record(parent)
        store.record(child1)
        store.record(child2)
        store.record(other)
        assert len(store.children_of(parent.trace_id)) == 2

    def test_max_traces_eviction(self):
        store = TraceStore(max_traces=5)
        for _ in range(10):
            store.record(ExecutionTrace())
        assert len(store) == 5

    def test_recent(self):
        store = TraceStore()
        traces = [ExecutionTrace() for _ in range(10)]
        for t in traces:
            store.record(t)
        recent = store.recent(3)
        assert len(recent) == 3
        assert recent[-1] is traces[-1]

    def test_clear(self):
        store = TraceStore()
        store.record(ExecutionTrace())
        store.clear()
        assert len(store) == 0

    def test_disabled_does_not_record(self):
        import core.green.execution_trace as mod
        mod.TRACE_ENABLED = False
        store = TraceStore()
        store.record(ExecutionTrace())
        assert len(store) == 0

    def test_no_behavioral_change_when_enabled(self):
        store = TraceStore()
        t = ExecutionTrace(tool_name="test_tool", tool_arguments={"a": 1})
        store.record(t)
        assert t.tool_name == "test_tool"
        assert t.tool_arguments == {"a": 1}


if __name__ == "__main__":
    unittest.main()
