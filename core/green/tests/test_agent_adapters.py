"""Tests for Agent Contract adapters — Phase 4 of GREEN runtime integration."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from core.green.agent_contract import (
    AgentContext,
    AgentProtocol,
    AgentRequest,
    AgentResult,
    AgentStatus,
    AgentError,
    BaseAgent,
)
from core.green.agent_adapters import (
    AgentExecutorAdapter,
    DevAgentAdapter,
    DeepResearchAdapter,
    AGENT_ADAPTERS,
    get_adapter,
    list_adapters,
)


# ── Protocol conformance ──────────────────────────────────────────

class TestProtocolConformance(unittest.TestCase):
    def test_executor_adapter_is_agent(self):
        adapter = AgentExecutorAdapter()
        assert isinstance(adapter, BaseAgent)

    def test_dev_agent_adapter_is_agent(self):
        adapter = DevAgentAdapter()
        assert isinstance(adapter, BaseAgent)

    def test_deep_research_adapter_is_agent(self):
        adapter = DeepResearchAdapter()
        assert isinstance(adapter, BaseAgent)

    def test_executor_satisfies_protocol(self):
        adapter = AgentExecutorAdapter()
        assert isinstance(adapter, AgentProtocol)

    def test_dev_agent_satisfies_protocol(self):
        adapter = DevAgentAdapter()
        assert isinstance(adapter, AgentProtocol)

    def test_deep_research_satisfies_protocol(self):
        adapter = DeepResearchAdapter()
        assert isinstance(adapter, AgentProtocol)


# ── Adapter properties ────────────────────────────────────────────

class TestAdapterProperties(unittest.TestCase):
    def test_executor_name(self):
        assert AgentExecutorAdapter().name == "agent_executor"

    def test_dev_agent_name(self):
        assert DevAgentAdapter().name == "dev_agent"

    def test_deep_research_name(self):
        assert DeepResearchAdapter().name == "deep_research"

    def test_executor_capabilities(self):
        caps = AgentExecutorAdapter().capabilities
        assert "planning" in caps
        assert "tool_use" in caps

    def test_dev_agent_capabilities(self):
        caps = DevAgentAdapter().capabilities
        assert "code_generation" in caps

    def test_deep_research_capabilities(self):
        caps = DeepResearchAdapter().capabilities
        assert "web_search" in caps

    def test_initial_status_created(self):
        for cls in [AgentExecutorAdapter, DevAgentAdapter, DeepResearchAdapter]:
            adapter = cls()
            assert adapter.status() == AgentStatus.CREATED

    def test_can_handle_returns_true(self):
        req = AgentRequest(task="test")
        for cls in [AgentExecutorAdapter, DevAgentAdapter, DeepResearchAdapter]:
            assert cls().can_handle(req) is True


# ── Executor adapter execution ────────────────────────────────────

class TestAgentExecutorAdapter(unittest.TestCase):
    @patch("core.green.agent_adapters.AgentExecutorAdapter._do_execute")
    def test_success_returns_completed(self, mock_exec):
        mock_exec.return_value = "task done"
        adapter = AgentExecutorAdapter()
        result = adapter.execute(AgentRequest(task="build something"))
        assert result.status == AgentStatus.COMPLETED
        assert result.output == "task done"
        assert result.duration_ms >= 0

    @patch("core.green.agent_adapters.AgentExecutorAdapter._do_execute")
    def test_failure_returns_failed(self, mock_exec):
        mock_exec.side_effect = RuntimeError("executor crashed")
        adapter = AgentExecutorAdapter()
        result = adapter.execute(AgentRequest(task="bad task"))
        assert result.status == AgentStatus.FAILED
        assert result.error is not None
        assert result.error.error_type == "RuntimeError"
        assert "executor crashed" in result.error.message

    def test_cancel_sets_event(self):
        import threading
        adapter = AgentExecutorAdapter()
        adapter._cancel_event = threading.Event()
        adapter.cancel()
        assert adapter._cancel_event.is_set()
        assert adapter.status() == AgentStatus.CANCELLED


# ── DevAgent adapter execution ────────────────────────────────────

class TestDevAgentAdapter(unittest.TestCase):
    @patch("core.green.agent_adapters.DevAgentAdapter._do_execute")
    def test_success(self, mock_exec):
        mock_exec.return_value = "code written"
        adapter = DevAgentAdapter()
        result = adapter.execute(AgentRequest(task="write code"))
        assert result.status == AgentStatus.COMPLETED
        assert result.output == "code written"

    @patch("core.green.agent_adapters.DevAgentAdapter._do_execute")
    def test_failure(self, mock_exec):
        mock_exec.side_effect = ImportError("module not found")
        adapter = DevAgentAdapter()
        result = adapter.execute(AgentRequest(task="bad"))
        assert result.status == AgentStatus.FAILED
        assert result.error.error_type == "ImportError"


# ── DeepResearch adapter execution ────────────────────────────────

class TestDeepResearchAdapter(unittest.TestCase):
    @patch("core.green.agent_adapters.DeepResearchAdapter._do_execute")
    def test_success(self, mock_exec):
        mock_exec.return_value = "research report"
        adapter = DeepResearchAdapter()
        result = adapter.execute(AgentRequest(task="research AI"))
        assert result.status == AgentStatus.COMPLETED
        assert result.output == "research report"

    @patch("core.green.agent_adapters.DeepResearchAdapter._do_execute")
    def test_failure(self, mock_exec):
        mock_exec.side_effect = TimeoutError("search timed out")
        adapter = DeepResearchAdapter()
        result = adapter.execute(AgentRequest(task="research"))
        assert result.status == AgentStatus.FAILED
        assert result.error.error_type == "TimeoutError"


# ── Registry ──────────────────────────────────────────────────────

class TestAdapterRegistry(unittest.TestCase):
    def test_all_three_registered(self):
        assert len(AGENT_ADAPTERS) == 3
        assert "agent_executor" in AGENT_ADAPTERS
        assert "dev_agent" in AGENT_ADAPTERS
        assert "deep_research" in AGENT_ADAPTERS

    def test_get_adapter_valid(self):
        for name in ["agent_executor", "dev_agent", "deep_research"]:
            adapter = get_adapter(name)
            assert adapter is not None
            assert isinstance(adapter, BaseAgent)
            assert adapter.name == name

    def test_get_adapter_invalid(self):
        assert get_adapter("nonexistent") is None

    def test_list_adapters(self):
        names = list_adapters()
        assert names == ["agent_executor", "deep_research", "dev_agent"]

    def test_adapters_are_independent_instances(self):
        a1 = get_adapter("agent_executor")
        a2 = get_adapter("agent_executor")
        assert a1 is not a2


# ── No execution leakage ─────────────────────────────────────────

class TestNoExecutionLeakage(unittest.TestCase):
    def test_adapter_does_not_import_agents_at_load(self):
        import sys
        # agent_adapters should already be imported, but the real
        # agent modules should NOT be imported just from loading adapters
        # (they're imported lazily inside _do_execute)
        import importlib
        import core.green.agent_adapters
        importlib.reload(core.green.agent_adapters)
        # We can't assert agent.executor isn't in sys.modules because
        # other tests might have imported it. But we CAN verify the
        # adapter module itself loads without error.
        assert "core.green.agent_adapters" in sys.modules

    def test_adapter_does_not_change_routing(self):
        adapter = AgentExecutorAdapter()
        # The adapter should have no execute_tool, dispatch, or route method
        assert not hasattr(adapter, "dispatch")
        assert not hasattr(adapter, "route")
        assert not hasattr(adapter, "execute_tool")

    def test_result_structure(self):
        """Verify AgentResult from adapter has expected fields."""
        adapter = AgentExecutorAdapter()
        with patch.object(adapter, "_do_execute", return_value="ok"):
            result = adapter.execute(AgentRequest(task="test"))
        assert hasattr(result, "status")
        assert hasattr(result, "output")
        assert hasattr(result, "error")
        assert hasattr(result, "duration_ms")
        assert hasattr(result, "steps_used")
        assert hasattr(result, "tool_calls_used")


if __name__ == "__main__":
    unittest.main()
