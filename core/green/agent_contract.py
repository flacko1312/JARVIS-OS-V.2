"""Agent Contract — common interface for JARVIS agents.

Wraps existing agents (planner, executor, dev_agent, deep_research,
code_helper) with a standard lifecycle without replacing them.
Does NOT implement a new autonomous router or change which agent
Gemini currently chooses.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("jarvis.green.agent")


class AgentStatus(Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BUDGET_EXHAUSTED = "budget_exhausted"
    LOOP_DETECTED = "loop_detected"


@dataclass
class AgentRequest:
    """Input to an agent run."""

    task: str
    parameters: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    turn_id: str | None = None
    parent_trace_id: str | None = None
    max_steps: int | None = None
    max_runtime_seconds: float | None = None


@dataclass
class AgentContext:
    """Runtime context available to an agent."""

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.time)
    step_count: int = 0
    tool_call_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0

    def record_step(self) -> None:
        self.step_count += 1

    def record_tool_call(self) -> None:
        self.tool_call_count += 1

    def record_failure(self) -> None:
        self.failure_count += 1
        self.consecutive_failures += 1

    def record_success(self) -> None:
        self.consecutive_failures = 0

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at


@dataclass
class AgentError:
    """Structured error from an agent."""

    error_type: str
    message: str
    recoverable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Output from an agent run."""

    status: AgentStatus
    output: Any = None
    summary: str | None = None
    error: AgentError | None = None

    steps_used: int = 0
    tool_calls_used: int = 0
    duration_ms: float = 0.0

    trace_id: str | None = None
    budget_remaining: dict[str, Any] | None = None
    loop_guard_outcome: str | None = None


@runtime_checkable
class AgentProtocol(Protocol):
    """Common interface for all JARVIS agents."""

    @property
    def name(self) -> str: ...

    def can_handle(self, request: AgentRequest) -> bool: ...

    def execute(self, request: AgentRequest) -> AgentResult: ...

    def cancel(self) -> None: ...

    def status(self) -> AgentStatus: ...


class BaseAgent:
    """Base implementation of the agent contract.

    Subclass to create adapters around existing JARVIS agents.
    """

    def __init__(self, name: str, capabilities: list[str] | None = None) -> None:
        self._name = name
        self._status = AgentStatus.CREATED
        self._capabilities = capabilities or []
        self._context: AgentContext | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    def can_handle(self, request: AgentRequest) -> bool:
        return True

    def execute(self, request: AgentRequest) -> AgentResult:
        self._context = AgentContext()
        self._status = AgentStatus.RUNNING
        started = time.time()
        try:
            output = self._do_execute(request, self._context)
            self._status = AgentStatus.COMPLETED
            return AgentResult(
                status=AgentStatus.COMPLETED,
                output=output,
                steps_used=self._context.step_count,
                tool_calls_used=self._context.tool_call_count,
                duration_ms=(time.time() - started) * 1000.0,
            )
        except Exception as exc:
            self._status = AgentStatus.FAILED
            return AgentResult(
                status=AgentStatus.FAILED,
                error=AgentError(
                    error_type=type(exc).__name__,
                    message=str(exc),
                ),
                steps_used=self._context.step_count if self._context else 0,
                tool_calls_used=self._context.tool_call_count if self._context else 0,
                duration_ms=(time.time() - started) * 1000.0,
            )

    def _do_execute(self, request: AgentRequest, context: AgentContext) -> Any:
        raise NotImplementedError

    def cancel(self) -> None:
        self._status = AgentStatus.CANCELLED

    def status(self) -> AgentStatus:
        return self._status
