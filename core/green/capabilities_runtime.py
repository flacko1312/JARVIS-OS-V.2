"""Capabilities Runtime — unified query surface for JARVIS capability metadata.

Connects tool_metadata, agent_adapters, and capability_catalog into a single
runtime-queryable system. All queries are read-only; this module never changes
routing, authorization, or execution.

Feature flag: JARVIS_CAPABILITIES_RUNTIME_ENABLED (default off).
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.green.capabilities_runtime")

CAPABILITIES_RUNTIME_ENABLED = os.environ.get("JARVIS_CAPABILITIES_RUNTIME_ENABLED", "0") == "1"


@dataclass
class CapabilityInfo:
    """Runtime snapshot of a single capability."""
    tool_name: str
    domain: str
    risk_level: str
    capabilities: list[str] = field(default_factory=list)
    side_effects: bool = False
    agent: str | None = None
    description: str = ""


@dataclass
class AgentCapabilityInfo:
    """Runtime snapshot of an agent adapter's capabilities."""
    agent_id: str
    capabilities: list[str] = field(default_factory=list)
    status: str = "created"


def get_tool_capability(tool_name: str) -> CapabilityInfo | None:
    """Look up runtime capability info for a single tool."""
    if not CAPABILITIES_RUNTIME_ENABLED:
        return None
    try:
        from core.green.tool_metadata import (
            TOOL_DOMAIN_MAP,
            TOOL_RISK_MAP,
            TOOL_CAPABILITIES_MAP,
            TOOL_SIDE_EFFECTS,
        )
        if tool_name not in TOOL_DOMAIN_MAP:
            return None
        return CapabilityInfo(
            tool_name=tool_name,
            domain=TOOL_DOMAIN_MAP[tool_name].value,
            risk_level=TOOL_RISK_MAP.get(tool_name, "LOW").value if hasattr(TOOL_RISK_MAP.get(tool_name), "value") else str(TOOL_RISK_MAP.get(tool_name, "LOW")),
            capabilities=TOOL_CAPABILITIES_MAP.get(tool_name, []),
            side_effects=TOOL_SIDE_EFFECTS.get(tool_name, False),
        )
    except Exception:
        logger.debug("get_tool_capability failed — isolated", exc_info=True)
        return None


def get_agent_capability(agent_id: str) -> AgentCapabilityInfo | None:
    """Look up runtime capability info for an agent adapter."""
    if not CAPABILITIES_RUNTIME_ENABLED:
        return None
    try:
        from core.green.agent_adapters import get_adapter
        adapter = get_adapter(agent_id)
        if adapter is None:
            return None
        return AgentCapabilityInfo(
            agent_id=agent_id,
            capabilities=adapter.capabilities,
            status=adapter.status().value,
        )
    except Exception:
        logger.debug("get_agent_capability failed — isolated", exc_info=True)
        return None


def list_capabilities_by_domain(domain: str) -> list[CapabilityInfo]:
    """List all tools in a given domain."""
    if not CAPABILITIES_RUNTIME_ENABLED:
        return []
    try:
        from core.green.tool_metadata import TOOL_DOMAIN_MAP
        return [
            info
            for name, d in TOOL_DOMAIN_MAP.items()
            if d.value == domain
            for info in [get_tool_capability(name)]
            if info is not None
        ]
    except Exception:
        logger.debug("list_capabilities_by_domain failed — isolated", exc_info=True)
        return []


def list_capabilities_by_tag(tag: str) -> list[CapabilityInfo]:
    """List all tools that have a given capability tag (e.g. 'filesystem.read')."""
    if not CAPABILITIES_RUNTIME_ENABLED:
        return []
    try:
        from core.green.tool_metadata import TOOL_CAPABILITIES_MAP
        return [
            info
            for name, caps in TOOL_CAPABILITIES_MAP.items()
            if tag in caps
            for info in [get_tool_capability(name)]
            if info is not None
        ]
    except Exception:
        logger.debug("list_capabilities_by_tag failed — isolated", exc_info=True)
        return []


def list_all_agents() -> list[AgentCapabilityInfo]:
    """List all available agent adapters with their capabilities."""
    if not CAPABILITIES_RUNTIME_ENABLED:
        return []
    try:
        from core.green.agent_adapters import list_adapters
        return [
            info
            for agent_id in list_adapters()
            for info in [get_agent_capability(agent_id)]
            if info is not None
        ]
    except Exception:
        logger.debug("list_all_agents failed — isolated", exc_info=True)
        return []


def capability_summary() -> dict[str, Any]:
    """Return a summary of the entire capability landscape."""
    if not CAPABILITIES_RUNTIME_ENABLED:
        return {"enabled": False}
    try:
        from core.green.tool_metadata import (
            TOOL_DOMAIN_MAP,
            TOOL_RISK_MAP,
            TOOL_CAPABILITIES_MAP,
            TOOL_SIDE_EFFECTS,
        )
        from core.green.agent_adapters import list_adapters

        domains: dict[str, int] = {}
        for d in TOOL_DOMAIN_MAP.values():
            domains[d.value] = domains.get(d.value, 0) + 1

        all_tags: set[str] = set()
        for caps in TOOL_CAPABILITIES_MAP.values():
            all_tags.update(caps)

        side_effect_count = sum(1 for v in TOOL_SIDE_EFFECTS.values() if v)

        return {
            "enabled": True,
            "total_tools": len(TOOL_DOMAIN_MAP),
            "total_agents": len(list_adapters()),
            "domains": domains,
            "unique_capability_tags": sorted(all_tags),
            "tools_with_side_effects": side_effect_count,
        }
    except Exception:
        logger.debug("capability_summary failed — isolated", exc_info=True)
        return {"enabled": True, "error": "failed to compute summary"}
