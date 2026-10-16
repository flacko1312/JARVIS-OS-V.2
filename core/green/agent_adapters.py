"""Agent Contract adapters — wrap existing JARVIS agents with structured lifecycle.

These adapters observe and structure agent execution without changing behavior.
The existing agents continue to execute through their original paths; the adapters
provide AgentContract-compatible status, timing, and error reporting.

Design:
- Adapters are opt-in wrappers, not replacements.
- Existing agent code is imported lazily and called unchanged.
- Structured AgentResult/AgentError are produced from raw return values.
- Cancellation support depends on the underlying agent's capabilities.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from core.green.agent_contract import (
    AgentContext,
    AgentRequest,
    AgentStatus,
    BaseAgent,
)

logger = logging.getLogger("jarvis.green.adapters")


class AgentExecutorAdapter(BaseAgent):
    """Wraps agent.executor.AgentExecutor with structured lifecycle."""

    def __init__(self) -> None:
        super().__init__(
            name="agent_executor",
            capabilities=["planning", "tool_use", "replanning"],
        )
        self._cancel_event: threading.Event | None = None

    def _do_execute(self, request: AgentRequest, context: AgentContext) -> Any:
        from agent.executor import AgentExecutor

        executor = AgentExecutor()
        self._cancel_event = threading.Event()

        result = executor.execute(
            goal=request.task or "",
            cancel_flag=self._cancel_event,
        )
        return result

    def cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        super().cancel()


class DevAgentAdapter(BaseAgent):
    """Wraps actions.dev_agent.dev_agent with structured lifecycle."""

    def __init__(self) -> None:
        super().__init__(
            name="dev_agent",
            capabilities=["code_generation", "code_editing", "development"],
        )

    def _do_execute(self, request: AgentRequest, context: AgentContext) -> Any:
        from actions.dev_agent import dev_agent

        result = dev_agent(
            parameters=request.parameters or {},
            player=None,
        )
        return result or ""


class DeepResearchAdapter(BaseAgent):
    """Wraps actions.deep_research.deep_research with structured lifecycle."""

    def __init__(self) -> None:
        super().__init__(
            name="deep_research",
            capabilities=["web_search", "analysis", "report_generation"],
        )

    def _do_execute(self, request: AgentRequest, context: AgentContext) -> Any:
        from actions.deep_research import deep_research

        result = deep_research(
            parameters=request.parameters or {},
        )
        return result or ""


AGENT_ADAPTERS: dict[str, type[BaseAgent]] = {
    "agent_executor": AgentExecutorAdapter,
    "dev_agent": DevAgentAdapter,
    "deep_research": DeepResearchAdapter,
}


def get_adapter(agent_id: str) -> BaseAgent | None:
    cls = AGENT_ADAPTERS.get(agent_id)
    return cls() if cls else None


def list_adapters() -> list[str]:
    return sorted(AGENT_ADAPTERS.keys())
