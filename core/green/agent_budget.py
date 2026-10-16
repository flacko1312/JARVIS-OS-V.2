"""Agent Budgets — reusable execution limits for agent runs.

Provides step, tool-call, failure, consecutive-failure, and runtime limits.
Budget exhaustion terminates cleanly with BUDGET_EXHAUSTED.
Does not suddenly change current production agent behavior — initial
integration should use values preserving existing behavior.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("jarvis.green.budget")


class BudgetLimit(Enum):
    STEPS = "max_steps"
    TOOL_CALLS = "max_tool_calls"
    FAILURES = "max_failures"
    CONSECUTIVE_FAILURES = "max_consecutive_failures"
    RUNTIME_SECONDS = "max_runtime_seconds"


@dataclass
class BudgetExhaustion:
    """Structured reason for budget exhaustion."""

    exhausted: bool
    limit: BudgetLimit | None = None
    reason: str = ""
    used: int | float = 0
    allowed: int | float = 0


class AgentBudget:
    """Tracks and enforces execution limits."""

    def __init__(
        self,
        max_steps: int | None = None,
        max_tool_calls: int | None = None,
        max_failures: int | None = None,
        max_consecutive_failures: int | None = None,
        max_runtime_seconds: float | None = None,
    ) -> None:
        self._limits = {
            BudgetLimit.STEPS: max_steps,
            BudgetLimit.TOOL_CALLS: max_tool_calls,
            BudgetLimit.FAILURES: max_failures,
            BudgetLimit.CONSECUTIVE_FAILURES: max_consecutive_failures,
            BudgetLimit.RUNTIME_SECONDS: max_runtime_seconds,
        }

        self._steps = 0
        self._tool_calls = 0
        self._failures = 0
        self._consecutive_failures = 0
        self._started_at = time.time()

    def consume_step(self) -> BudgetExhaustion:
        self._steps += 1
        return self._check(BudgetLimit.STEPS, self._steps)

    def consume_tool_call(self) -> BudgetExhaustion:
        self._tool_calls += 1
        return self._check(BudgetLimit.TOOL_CALLS, self._tool_calls)

    def record_failure(self) -> BudgetExhaustion:
        self._failures += 1
        self._consecutive_failures += 1
        fail_check = self._check(BudgetLimit.FAILURES, self._failures)
        if fail_check.exhausted:
            return fail_check
        return self._check(BudgetLimit.CONSECUTIVE_FAILURES, self._consecutive_failures)

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def check(self) -> BudgetExhaustion:
        """Check all limits without consuming anything."""
        for limit, current in [
            (BudgetLimit.STEPS, self._steps),
            (BudgetLimit.TOOL_CALLS, self._tool_calls),
            (BudgetLimit.FAILURES, self._failures),
            (BudgetLimit.CONSECUTIVE_FAILURES, self._consecutive_failures),
        ]:
            result = self._check(limit, current)
            if result.exhausted:
                return result

        runtime_limit = self._limits.get(BudgetLimit.RUNTIME_SECONDS)
        if runtime_limit is not None:
            elapsed = time.time() - self._started_at
            if elapsed >= runtime_limit:
                return BudgetExhaustion(
                    exhausted=True,
                    limit=BudgetLimit.RUNTIME_SECONDS,
                    reason=f"runtime {elapsed:.1f}s >= {runtime_limit}s",
                    used=elapsed,
                    allowed=runtime_limit,
                )

        return BudgetExhaustion(exhausted=False)

    def remaining(self) -> dict[str, int | float | None]:
        """Return remaining budget for each limit."""
        result = {}
        for limit in BudgetLimit:
            max_val = self._limits.get(limit)
            if max_val is None:
                result[limit.value] = None
                continue
            if limit == BudgetLimit.STEPS:
                result[limit.value] = max(0, max_val - self._steps)
            elif limit == BudgetLimit.TOOL_CALLS:
                result[limit.value] = max(0, max_val - self._tool_calls)
            elif limit == BudgetLimit.FAILURES:
                result[limit.value] = max(0, max_val - self._failures)
            elif limit == BudgetLimit.CONSECUTIVE_FAILURES:
                result[limit.value] = max(0, max_val - self._consecutive_failures)
            elif limit == BudgetLimit.RUNTIME_SECONDS:
                elapsed = time.time() - self._started_at
                result[limit.value] = max(0.0, max_val - elapsed)
        return result

    def exhaustion_reason(self) -> str | None:
        """Return human-readable reason if exhausted, else None."""
        result = self.check()
        return result.reason if result.exhausted else None

    def _check(self, limit: BudgetLimit, current: int | float) -> BudgetExhaustion:
        max_val = self._limits.get(limit)
        if max_val is None:
            return BudgetExhaustion(exhausted=False)
        if current >= max_val:
            return BudgetExhaustion(
                exhausted=True,
                limit=limit,
                reason=f"{limit.value}: {current} >= {max_val}",
                used=current,
                allowed=max_val,
            )
        return BudgetExhaustion(exhausted=False)
