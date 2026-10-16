"""Tests for Agent Contract — Phase 4 of GREEN Foundation."""
from __future__ import annotations

import time
import unittest

from core.green.agent_contract import (
    AgentContext,
    AgentError,
    AgentRequest,
    AgentResult,
    AgentStatus,
    BaseAgent,
)


class TestAgentRequest(unittest.TestCase):
    def test_defaults(self):
        r = AgentRequest(task="do something")
        assert r.task == "do something"
        assert r.parameters == {}
        assert r.max_steps is None

    def test_with_params(self):
        r = AgentRequest(task="t", parameters={"a": 1}, session_id="s", turn_id="t")
        assert r.parameters == {"a": 1}
        assert r.session_id == "s"


class TestAgentContext(unittest.TestCase):
    def test_step_counting(self):
        ctx = AgentContext()
        ctx.record_step()
        ctx.record_step()
        assert ctx.step_count == 2

    def test_tool_call_counting(self):
        ctx = AgentContext()
        ctx.record_tool_call()
        assert ctx.tool_call_count == 1

    def test_failure_tracking(self):
        ctx = AgentContext()
        ctx.record_failure()
        ctx.record_failure()
        assert ctx.failure_count == 2
        assert ctx.consecutive_failures == 2

    def test_success_resets_consecutive(self):
        ctx = AgentContext()
        ctx.record_failure()
        ctx.record_failure()
        ctx.record_success()
        assert ctx.failure_count == 2
        assert ctx.consecutive_failures == 0

    def test_elapsed_seconds(self):
        ctx = AgentContext()
        time.sleep(0.01)
        assert ctx.elapsed_seconds > 0

    def test_unique_request_ids(self):
        c1 = AgentContext()
        c2 = AgentContext()
        assert c1.request_id != c2.request_id


class TestAgentResult(unittest.TestCase):
    def test_success_result(self):
        r = AgentResult(status=AgentStatus.COMPLETED, output="done", steps_used=3)
        assert r.status == AgentStatus.COMPLETED
        assert r.output == "done"
        assert r.steps_used == 3

    def test_failure_result(self):
        r = AgentResult(
            status=AgentStatus.FAILED,
            error=AgentError(error_type="ValueError", message="bad"),
        )
        assert r.error is not None
        assert r.error.error_type == "ValueError"

    def test_all_statuses(self):
        for s in AgentStatus:
            r = AgentResult(status=s)
            assert r.status == s


class _TestAgent(BaseAgent):
    def __init__(self, result=None, error=None):
        super().__init__("test_agent", capabilities=["test.run"])
        self._result = result
        self._error = error

    def can_handle(self, request):
        return "test" in request.task

    def _do_execute(self, request, context):
        context.record_step()
        if self._error:
            raise self._error
        return self._result


class TestBaseAgent(unittest.TestCase):
    def test_name(self):
        agent = _TestAgent()
        assert agent.name == "test_agent"

    def test_capabilities(self):
        agent = _TestAgent()
        assert agent.capabilities == ["test.run"]

    def test_initial_status(self):
        agent = _TestAgent()
        assert agent.status() == AgentStatus.CREATED

    def test_can_handle(self):
        agent = _TestAgent()
        assert agent.can_handle(AgentRequest(task="run test"))
        assert not agent.can_handle(AgentRequest(task="other"))

    def test_execute_success(self):
        agent = _TestAgent(result="output_data")
        result = agent.execute(AgentRequest(task="test"))
        assert result.status == AgentStatus.COMPLETED
        assert result.output == "output_data"
        assert result.steps_used == 1
        assert result.duration_ms > 0
        assert agent.status() == AgentStatus.COMPLETED

    def test_execute_failure(self):
        agent = _TestAgent(error=RuntimeError("broke"))
        result = agent.execute(AgentRequest(task="test"))
        assert result.status == AgentStatus.FAILED
        assert result.error is not None
        assert result.error.error_type == "RuntimeError"
        assert agent.status() == AgentStatus.FAILED

    def test_cancel(self):
        agent = _TestAgent()
        agent.cancel()
        assert agent.status() == AgentStatus.CANCELLED

    def test_unimplemented_do_execute(self):
        agent = BaseAgent("bare")
        result = agent.execute(AgentRequest(task="test"))
        assert result.status == AgentStatus.FAILED
        assert result.error.error_type == "NotImplementedError"


if __name__ == "__main__":
    unittest.main()
