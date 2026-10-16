"""Tests for Budget Guard — Phase 6 of GREEN runtime integration."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from core.green.budget_guard import (
    AgentBudget,
    BudgetGuard,
    BudgetStatus,
    DEFAULT_BUDGETS,
    get_budget_guard,
    BUDGET_GUARD_ENABLED,
)
from core.green.loop_guard import LoopGuard

_FLAG = "core.green.budget_guard.BUDGET_GUARD_ENABLED"


class TestBudgetGuardBasic(unittest.TestCase):
    def test_initial_check_not_exhausted(self):
        guard = BudgetGuard(budget=AgentBudget(max_steps=10))
        guard.start()
        status = guard.check()
        assert not status.exhausted
        assert status.steps_remaining == 10

    def test_step_counting(self):
        guard = BudgetGuard(budget=AgentBudget(max_steps=5))
        guard.start()
        guard.record_step(tool="web_search", arguments={"q": "test"})
        guard.record_step(tool="file_read", arguments={"path": "/tmp"})
        status = guard.check()
        assert status.steps_used == 2
        assert status.steps_remaining == 3
        assert status.tool_calls_used == 2

    def test_step_exhaustion(self):
        guard = BudgetGuard(budget=AgentBudget(max_steps=2))
        guard.start()
        guard.record_step(tool="a")
        guard.record_step(tool="b")
        status = guard.check()
        assert status.exhausted
        assert status.exhaustion_reason == "max_steps"

    def test_tool_call_exhaustion(self):
        guard = BudgetGuard(budget=AgentBudget(max_steps=100, max_tool_calls=3))
        guard.start()
        guard.record_step(tool="a")
        guard.record_step(tool="b")
        guard.record_step(tool="c")
        status = guard.check()
        assert status.exhausted
        assert status.exhaustion_reason == "max_tool_calls"

    def test_consecutive_failure_exhaustion(self):
        guard = BudgetGuard(budget=AgentBudget(max_consecutive_failures=3))
        guard.start()
        guard.record_step(tool="a", success=False, error_category="err1")
        guard.record_step(tool="b", success=False, error_category="err2")
        guard.record_step(tool="c", success=False, error_category="err3")
        status = guard.check()
        assert status.exhausted
        assert status.exhaustion_reason == "max_consecutive_failures"

    def test_success_resets_consecutive_failures(self):
        guard = BudgetGuard(budget=AgentBudget(max_consecutive_failures=3))
        guard.start()
        guard.record_step(tool="a", success=False)
        guard.record_step(tool="b", success=False)
        guard.record_step(tool="c", success=True)
        status = guard.check()
        assert not status.exhausted
        assert status.consecutive_failures == 0

    def test_time_exhaustion(self):
        guard = BudgetGuard(budget=AgentBudget(max_runtime_seconds=0.01))
        guard.start()
        time.sleep(0.02)
        status = guard.check()
        assert status.exhausted
        assert status.exhaustion_reason == "max_runtime"


class TestLoopIntegration(unittest.TestCase):
    def test_loop_detection_through_budget(self):
        guard = BudgetGuard(
            budget=AgentBudget(max_steps=100),
            loop_guard=LoopGuard(max_same_operation=3),
        )
        guard.start()
        guard.record_step(tool="web_search", arguments={"q": "test"})
        guard.record_step(tool="web_search", arguments={"q": "test"})
        detection = guard.record_step(tool="web_search", arguments={"q": "test"})
        assert detection.detected

    def test_no_loop_with_variety(self):
        guard = BudgetGuard(
            budget=AgentBudget(max_steps=100),
            loop_guard=LoopGuard(max_same_operation=3),
        )
        guard.start()
        d1 = guard.record_step(tool="web_search", arguments={"q": "a"})
        d2 = guard.record_step(tool="file_read", arguments={"path": "b"})
        d3 = guard.record_step(tool="web_search", arguments={"q": "c"})
        assert not d1.detected
        assert not d2.detected
        assert not d3.detected

    def test_error_loop_detection(self):
        guard = BudgetGuard(
            budget=AgentBudget(max_steps=100),
            loop_guard=LoopGuard(max_same_error=3),
        )
        guard.start()
        guard.record_step(tool="a", arguments={"x": 1}, error_category="timeout")
        guard.record_step(tool="b", arguments={"x": 2}, error_category="timeout")
        detection = guard.record_step(tool="c", arguments={"x": 3}, error_category="timeout")
        assert detection.detected
        assert "timeout" in detection.reason


class TestDefaultBudgets(unittest.TestCase):
    def test_all_agents_have_defaults(self):
        assert "agent_executor" in DEFAULT_BUDGETS
        assert "dev_agent" in DEFAULT_BUDGETS
        assert "deep_research" in DEFAULT_BUDGETS

    def test_dev_agent_has_higher_limits(self):
        assert DEFAULT_BUDGETS["dev_agent"].max_steps > DEFAULT_BUDGETS["agent_executor"].max_steps

    def test_research_has_lower_time(self):
        assert DEFAULT_BUDGETS["deep_research"].max_runtime_seconds < DEFAULT_BUDGETS["dev_agent"].max_runtime_seconds


class TestGetBudgetGuard(unittest.TestCase):
    @patch(_FLAG, False)
    def test_disabled_returns_none(self):
        assert get_budget_guard("agent_executor") is None

    @patch(_FLAG, True)
    def test_known_agent(self):
        guard = get_budget_guard("agent_executor")
        assert guard is not None
        assert guard.budget.max_steps == 20

    @patch(_FLAG, True)
    def test_unknown_agent_gets_default(self):
        guard = get_budget_guard("unknown_agent")
        assert guard is not None
        assert guard.budget.max_steps == 20  # default AgentBudget


class TestBudgetGuardReset(unittest.TestCase):
    def test_start_resets_state(self):
        guard = BudgetGuard(budget=AgentBudget(max_steps=10))
        guard.start()
        guard.record_step(tool="a")
        guard.record_step(tool="b")
        guard.start()  # reset
        status = guard.check()
        assert status.steps_used == 0
        assert status.steps_remaining == 10


class TestBudgetStatusFields(unittest.TestCase):
    def test_all_fields_present(self):
        status = BudgetStatus()
        assert hasattr(status, "steps_used")
        assert hasattr(status, "steps_remaining")
        assert hasattr(status, "tool_calls_used")
        assert hasattr(status, "tool_calls_remaining")
        assert hasattr(status, "elapsed_seconds")
        assert hasattr(status, "time_remaining_seconds")
        assert hasattr(status, "consecutive_failures")
        assert hasattr(status, "exhausted")
        assert hasattr(status, "exhaustion_reason")
        assert hasattr(status, "loop_detected")
        assert hasattr(status, "loop_reason")


if __name__ == "__main__":
    unittest.main()
