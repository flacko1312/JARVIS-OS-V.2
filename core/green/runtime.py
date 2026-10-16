"""GREEN Runtime Bridge — connects GREEN observability to the live JARVIS runtime.

This module provides the single integration surface between the existing JARVIS
execution path and GREEN infrastructure (ExecutionTrace, Event Bus). It is
imported lazily from main.py and instruments the existing dispatch without
changing any authorization, routing, or result.

Design:
- All methods are safe to call regardless of feature-flag state.
- If tracing/events are disabled, calls are no-ops.
- Exceptions inside GREEN instrumentation are caught and logged — they
  never disrupt the user-facing tool execution.
- No import of main.py internals — receives everything via arguments.
"""
from __future__ import annotations

import logging
from typing import Any

import core.green.execution_trace as _trace_mod
import core.green.event_bus as _bus_mod

from core.green.execution_trace import (
    ExecutionTrace,
    TraceStatus,
    TraceStore,
    redact_secrets,
)
from core.green.event_bus import (
    Event,
    EventBus,
    EventType,
)

logger = logging.getLogger("jarvis.green.runtime")

# ── Singleton instances ─────────────────────────────────────────────

_trace_store = TraceStore(max_traces=2000)
_event_bus = EventBus()

# Prevent trace→event→trace recursion
_emitting = False


def get_trace_store() -> TraceStore:
    return _trace_store


def get_event_bus() -> EventBus:
    return _event_bus


# ── Tool execution instrumentation ─────────────────────────────────

def trace_tool_start(
    *,
    tool_name: str,
    tool_arguments: dict[str, Any],
    function_call_id: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
) -> ExecutionTrace | None:
    """Create and record a STARTED trace for a tool call. Returns the trace or None."""
    if not _trace_mod.TRACE_ENABLED:
        return None
    try:
        trace = ExecutionTrace(
            tool_name=tool_name,
            tool_arguments=redact_secrets(tool_arguments),
            function_call_id=function_call_id,
            session_id=session_id,
            turn_id=turn_id,
            status=TraceStatus.STARTED,
        )
        _trace_store.record(trace)
        _emit_safe(EventType.TOOL_STARTED, {
            "trace_id": trace.trace_id,
            "tool_name": tool_name,
            "function_call_id": function_call_id,
        })
        return trace
    except Exception:
        logger.debug("trace_tool_start failed — isolated", exc_info=True)
        return None


def trace_tool_complete(
    trace: ExecutionTrace | None,
    *,
    result_summary: str | None = None,
) -> None:
    """Finish a trace as COMPLETED and emit event."""
    if trace is None:
        return
    try:
        trace.finish(
            status=TraceStatus.COMPLETED,
            result_summary=result_summary,
        )
        _trace_store.record(trace)
        _emit_safe(EventType.TOOL_COMPLETED, {
            "trace_id": trace.trace_id,
            "tool_name": trace.tool_name,
            "duration_ms": trace.duration_ms,
        })
    except Exception:
        logger.debug("trace_tool_complete failed — isolated", exc_info=True)


def trace_tool_failed(
    trace: ExecutionTrace | None,
    *,
    error: Exception | None = None,
    error_message: str | None = None,
) -> None:
    """Finish a trace as FAILED and emit event."""
    if trace is None:
        return
    try:
        err_type = type(error).__name__ if error else "Unknown"
        err_msg = error_message or (str(error) if error else "Unknown error")
        trace.finish(
            status=TraceStatus.FAILED,
            error_type=err_type,
            error_message=err_msg,
        )
        _trace_store.record(trace)
        _emit_safe(EventType.TOOL_FAILED, {
            "trace_id": trace.trace_id,
            "tool_name": trace.tool_name,
            "error_type": err_type,
            "duration_ms": trace.duration_ms,
        })
    except Exception:
        logger.debug("trace_tool_failed failed — isolated", exc_info=True)


def emit_turn_started(
    *,
    session_id: str | None = None,
    turn_id: str | None = None,
    source: str | None = None,
) -> None:
    """Emit a TURN_STARTED event."""
    _emit_safe(EventType.TURN_STARTED, {
        "session_id": session_id,
        "turn_id": turn_id,
        "source": source,
    })


def emit_turn_completed(
    *,
    session_id: str | None = None,
    turn_id: str | None = None,
) -> None:
    """Emit a TURN_COMPLETED event."""
    _emit_safe(EventType.TURN_COMPLETED, {
        "session_id": session_id,
        "turn_id": turn_id,
    })


def emit_tool_authorized(
    *,
    tool_name: str,
    function_call_id: str | None = None,
) -> None:
    """Emit TOOL_AUTHORIZED after qa_guard passes."""
    _emit_safe(EventType.TOOL_AUTHORIZED, {
        "tool_name": tool_name,
        "function_call_id": function_call_id,
    })


def emit_tool_rejected(
    *,
    tool_name: str,
    function_call_id: str | None = None,
    reason: str | None = None,
) -> None:
    """Emit TOOL_REJECTED when qa_guard or cloud-safe blocks."""
    _emit_safe(EventType.TOOL_REJECTED, {
        "tool_name": tool_name,
        "function_call_id": function_call_id,
        "reason": reason,
    })


def emit_lilith_requested(
    *,
    tool_name: str,
    function_call_id: str | None = None,
) -> None:
    """Emit LILITH_REQUESTED when a LILITH bridge call starts."""
    _emit_safe(EventType.LILITH_REQUESTED, {
        "tool_name": tool_name,
        "function_call_id": function_call_id,
    })


def emit_lilith_completed(
    *,
    tool_name: str,
    function_call_id: str | None = None,
) -> None:
    """Emit LILITH_COMPLETED when a LILITH bridge call succeeds."""
    _emit_safe(EventType.LILITH_COMPLETED, {
        "tool_name": tool_name,
        "function_call_id": function_call_id,
    })


def emit_lilith_failed(
    *,
    tool_name: str,
    function_call_id: str | None = None,
    error: str | None = None,
) -> None:
    """Emit LILITH_FAILED when a LILITH bridge call fails."""
    _emit_safe(EventType.LILITH_FAILED, {
        "tool_name": tool_name,
        "function_call_id": function_call_id,
        "error": error,
    })


# ── Internal ────────────────────────────────────────────────────────

def _emit_safe(event_type: EventType, data: dict[str, Any]) -> None:
    """Emit an event with recursion and exception protection."""
    global _emitting
    if not _bus_mod.EVENT_BUS_ENABLED:
        return
    if _emitting:
        return
    try:
        _emitting = True
        _event_bus.emit(Event(
            event_type=event_type,
            data=data,
            source="jarvis.green.runtime",
        ))
    except Exception:
        logger.debug("event emission failed — isolated", exc_info=True)
    finally:
        _emitting = False
