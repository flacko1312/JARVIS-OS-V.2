"""Budget Guard — runtime integration of Loop Guards with Agent Budgets.

Connects the existing LoopGuard to agent execution via the Agent Contract.
Provides per-agent budget tracking (step limits, time limits, tool call limits)
and loop detection integration.

Feature flag: JARVIS_BUDGET_GUARD_ENABLED (default off).
All enforcement is observational — it reports but does not kill agents.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from core.green.loop_guard import LoopGuard, LoopDetection
from core.green.agent_contract import AgentContext, AgentRequest, AgentStatus

logger = logging.getLogger("jarvis.green.budget_guard")

BUDGET_GUARD_ENABLED = os.environ.get("JARVIS_BUDGET_GUARD_ENABLED", "0") == "1"


@dataclass
class AgentBudget:
    """Budget limits for a single agent run."""
    max_steps: int = 20
    max_tool_calls: int = 50
    max_runtime_seconds: float = 300.0
    max_consecutive_failures: int = 5


@dataclass
class BudgetStatus:
    """Current budget consumption snapshot."""
    steps_used: int = 0
    steps_remaining: int = 0
    tool_calls_used: int = 0
    tool_calls_remaining: int = 0
    elapsed_seconds: float = 0.0
    time_remaining_seconds: float = 0.0
    consecutive_failures: int = 0
    exhausted: bool = False
    exhaustion_reason: str = ""
    loop_detected: bool = False
    loop_reason: str = ""


class BudgetGuard:
    """Tracks agent execution against budget limits and loop detection.

    Usage:
        guard = BudgetGuard(budget=AgentBudget(max_steps=10))
        guard.start()
        for step in agent_steps:
            guard.record_step(tool="web_search", arguments={...})
            status = guard.check()
            if status.exhausted or status.loop_detected:
                # report and stop
                break
    """

    def __init__(
        self,
        budget: AgentBudget | None = None,
        loop_guard: LoopGuard | None = None,
    ) -> None:
        self._budget = budget or AgentBudget()
        self._loop_guard = loop_guard or LoopGuard()
        self._started_at: float | None = None
        self._steps = 0
        self._tool_calls = 0
        self._consecutive_failures = 0

    def start(self) -> None:
        self._started_at = time.time()
        self._steps = 0
        self._tool_calls = 0
        self._consecutive_failures = 0
        self._loop_guard.reset()

    def record_step(
        self,
        *,
        tool: str = "",
        arguments: dict[str, Any] | None = None,
        error_category: str = "",
        progress_marker: str = "",
        success: bool = True,
    ) -> LoopDetection:
        """Record a step and check loop guard. Returns loop detection result."""
        self._steps += 1
        self._tool_calls += 1
        if success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        return self._loop_guard.check_operation(
            action="step",
            tool=tool,
            arguments=arguments,
            error_category=error_category,
            progress_marker=progress_marker,
        )

    def check(self) -> BudgetStatus:
        """Check current budget status."""
        elapsed = (time.time() - self._started_at) if self._started_at else 0.0

        status = BudgetStatus(
            steps_used=self._steps,
            steps_remaining=max(0, self._budget.max_steps - self._steps),
            tool_calls_used=self._tool_calls,
            tool_calls_remaining=max(0, self._budget.max_tool_calls - self._tool_calls),
            elapsed_seconds=elapsed,
            time_remaining_seconds=max(0.0, self._budget.max_runtime_seconds - elapsed),
            consecutive_failures=self._consecutive_failures,
        )

        if self._steps >= self._budget.max_steps:
            status.exhausted = True
            status.exhaustion_reason = "max_steps"
        elif self._tool_calls >= self._budget.max_tool_calls:
            status.exhausted = True
            status.exhaustion_reason = "max_tool_calls"
        elif elapsed >= self._budget.max_runtime_seconds:
            status.exhausted = True
            status.exhaustion_reason = "max_runtime"
        elif self._consecutive_failures >= self._budget.max_consecutive_failures:
            status.exhausted = True
            status.exhaustion_reason = "max_consecutive_failures"

        return status

    @property
    def budget(self) -> AgentBudget:
        return self._budget

    @property
    def loop_guard(self) -> LoopGuard:
        return self._loop_guard


DEFAULT_BUDGETS: dict[str, AgentBudget] = {
    "agent_executor": AgentBudget(max_steps=20, max_tool_calls=50, max_runtime_seconds=300),
    "dev_agent": AgentBudget(max_steps=30, max_tool_calls=100, max_runtime_seconds=600),
    "deep_research": AgentBudget(max_steps=15, max_tool_calls=40, max_runtime_seconds=180),
}


def get_budget_guard(agent_id: str) -> BudgetGuard | None:
    """Get a BudgetGuard configured for a specific agent."""
    if not BUDGET_GUARD_ENABLED:
        return None
    budget = DEFAULT_BUDGETS.get(agent_id, AgentBudget())
    return BudgetGuard(budget=budget)
