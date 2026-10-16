"""ExecutionTrace — structured execution-tracing subsystem for JARVIS.

Observational only: traces record metadata about tool calls, agent runs,
routing decisions, and LILITH interactions. They never change routing,
authorization, tool results, or any Gemini/LILITH behavior.

JARVIS remains fully functional when tracing is disabled.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.green.trace")

# Feature flag — honours existing env-var convention
TRACE_ENABLED = os.environ.get("JARVIS_EXECUTION_TRACE_ENABLED", "0") == "1"

# ── Secret redaction ────────────────────────────────────────────────

_SECRET_KEYS = re.compile(
    r"(password|passwd|token|api_key|apikey|authorization|cookie|secret|"
    r"private_key|access_token|refresh_token|credential|bearer)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def redact_secrets(obj: Any, *, _depth: int = 0) -> Any:
    """Return a deep copy of *obj* with secret-looking values replaced.

    Handles nested dicts and lists. Stops at depth 20 to avoid
    accidental infinite recursion on cyclic structures.
    """
    if _depth > 20:
        return _REDACTED
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if _SECRET_KEYS.search(str(k)) else redact_secrets(v, _depth=_depth + 1))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [redact_secrets(item, _depth=_depth + 1) for item in obj]
    return obj


# ── Trace status ────────────────────────────────────────────────────

class TraceStatus(Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BUDGET_EXHAUSTED = "budget_exhausted"
    LOOP_DETECTED = "loop_detected"


# ── ExecutionTrace ──────────────────────────────────────────────────

@dataclass
class ExecutionTrace:
    """A single structured trace record."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    parent_trace_id: str | None = None

    session_id: str | None = None
    turn_id: str | None = None
    function_call_id: str | None = None

    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    duration_ms: float | None = None

    source: str | None = None
    intent: str | None = None
    domain: str | None = None

    router_decision: str | None = None

    provider: str | None = None
    model: str | None = None

    agent: str | None = None

    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)

    authorization_result: str | None = None
    approval_result: str | None = None

    status: TraceStatus = TraceStatus.STARTED
    result_summary: str | None = None

    fallback_used: bool = False

    error_type: str | None = None
    error_message: str | None = None

    def finish(
        self,
        status: TraceStatus = TraceStatus.COMPLETED,
        result_summary: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> ExecutionTrace:
        self.finished_at = time.time()
        self.duration_ms = (self.finished_at - self.started_at) * 1000.0
        self.status = status
        if result_summary is not None:
            self.result_summary = result_summary
        if error_type is not None:
            self.error_type = error_type
        if error_message is not None:
            self.error_message = error_message
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict with secrets redacted from tool_arguments."""
        return {
            "trace_id": self.trace_id,
            "parent_trace_id": self.parent_trace_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "function_call_id": self.function_call_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "source": self.source,
            "intent": self.intent,
            "domain": self.domain,
            "router_decision": self.router_decision,
            "provider": self.provider,
            "model": self.model,
            "agent": self.agent,
            "tool_name": self.tool_name,
            "tool_arguments": redact_secrets(self.tool_arguments),
            "authorization_result": self.authorization_result,
            "approval_result": self.approval_result,
            "status": self.status.value,
            "result_summary": self.result_summary,
            "fallback_used": self.fallback_used,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


# ── Trace Store ─────────────────────────────────────────────────────

class TraceStore:
    """In-memory bounded trace storage.

    Holds at most *max_traces* recent traces. Thread-safety is not
    required because JARVIS is single-threaded async with Qt event-loop
    dispatch, but we keep the API simple enough to add a lock later.
    """

    def __init__(self, max_traces: int = 1000) -> None:
        self._traces: list[ExecutionTrace] = []
        self._max = max_traces

    def record(self, trace: ExecutionTrace) -> None:
        if not TRACE_ENABLED:
            return
        self._traces.append(trace)
        if len(self._traces) > self._max:
            self._traces = self._traces[-self._max:]
        logger.debug("trace recorded: %s [%s]", trace.trace_id, trace.status.value)

    def get(self, trace_id: str) -> ExecutionTrace | None:
        for t in reversed(self._traces):
            if t.trace_id == trace_id:
                return t
        return None

    def by_session(self, session_id: str) -> list[ExecutionTrace]:
        return [t for t in self._traces if t.session_id == session_id]

    def by_turn(self, turn_id: str) -> list[ExecutionTrace]:
        return [t for t in self._traces if t.turn_id == turn_id]

    def children_of(self, parent_trace_id: str) -> list[ExecutionTrace]:
        return [t for t in self._traces if t.parent_trace_id == parent_trace_id]

    def recent(self, n: int = 50) -> list[ExecutionTrace]:
        return list(self._traces[-n:])

    def clear(self) -> None:
        self._traces.clear()

    def __len__(self) -> int:
        return len(self._traces)
