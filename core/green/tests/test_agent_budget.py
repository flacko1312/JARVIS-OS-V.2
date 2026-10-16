"""Tests for Agent Budgets — Phase 7 of GREEN Foundation."""
from __future__ import annotations

import time
import unittest

from core.green.agent_budget import AgentBudget, BudgetLimit


class TestAgentBudget(unittest.TestCase):
    def test_step_limit(self):
        budget = AgentBudget(max_steps=3)
        assert not budget.consume_step().exhausted
        assert not budget.consume_step().exhausted
        result = budget.consume_step()
        assert result.exhausted
        assert result.limit == BudgetLimit.STEPS

    def test_tool_call_limit(self):
        budget = AgentBudget(max_tool_calls=2)
        assert not budget.consume_tool_call().exhausted
        result = budget.consume_tool_call()
        assert result.exhausted
        assert result.limit == BudgetLimit.TOOL_CALLS

    def test_failure_limit(self):
        budget = AgentBudget(max_failures=2)
        assert not budget.record_failure().exhausted
        result = budget.record_failure()
        assert result.exhausted
        assert result.limit == BudgetLimit.FAILURES

    def test_consecutive_failure_limit(self):
        budget = AgentBudget(max_consecutive_failures=2)
        assert not budget.record_failure().exhausted
        result = budget.record_failure()
        assert result.exhausted
        assert result.limit == BudgetLimit.CONSECUTIVE_FAILURES

    def test_consecutive_resets_on_success(self):
        budget = AgentBudget(max_consecutive_failures=3)
        budget.record_failure()
        budget.record_failure()
        budget.record_success()
        assert not budget.record_failure().exhausted
        assert not budget.record_failure().exhausted
        result = budget.record_failure()
        assert result.exhausted

    def test_runtime_limit(self):
        budget = AgentBudget(max_runtime_seconds=0.05)
        assert not budget.check().exhausted
        time.sleep(0.06)
        result = budget.check()
        assert result.exhausted
        assert result.limit == BudgetLimit.RUNTIME_SECONDS

    def test_successful_completion_before_budget(self):
        budget = AgentBudget(max_steps=10, max_tool_calls=10)
        for _ in range(3):
            budget.consume_step()
            budget.consume_tool_call()
        assert not budget.check().exhausted

    def test_remaining(self):
        budget = AgentBudget(max_steps=5, max_tool_calls=3)
        budget.consume_step()
        budget.consume_tool_call()
        rem = budget.remaining()
        assert rem["max_steps"] == 4
        assert rem["max_tool_calls"] == 2

    def test_remaining_no_limit(self):
        budget = AgentBudget()
        rem = budget.remaining()
        assert rem["max_steps"] is None

    def test_exhaustion_reason(self):
        budget = AgentBudget(max_steps=1)
        assert budget.exhaustion_reason() is None
        budget.consume_step()
        reason = budget.exhaustion_reason()
        assert reason is not None
        assert "max_steps" in reason

    def test_no_limits_never_exhausted(self):
        budget = AgentBudget()
        for _ in range(100):
            budget.consume_step()
            budget.consume_tool_call()
        assert not budget.check().exhausted

    def test_combined_limits(self):
        budget = AgentBudget(max_steps=5, max_failures=2)
        budget.consume_step()
        budget.record_failure()
        result = budget.record_failure()
        assert result.exhausted
        assert result.limit == BudgetLimit.FAILURES


if __name__ == "__main__":
    unittest.main()
