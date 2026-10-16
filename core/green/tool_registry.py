"""Tool Registry — central catalogue of JARVIS tools.

Organizes and validates tool metadata. Does NOT authorize or execute tools.
Execution always goes through existing JARVIS authority guards.

JARVIS remains fully functional when the tool registry is disabled.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("jarvis.green.registry")

TOOL_REGISTRY_ENABLED = os.environ.get("JARVIS_TOOL_REGISTRY_ENABLED", "0") == "1"


class ToolDomain(Enum):
    WINDOWS = "windows"
    FILES = "files"
    VISION = "vision"
    MEMORY = "memory"
    HOME = "home"
    DEVELOPMENT = "development"
    KNOWLEDGE = "knowledge"
    WEB = "web"
    GMAIL = "gmail"
    MULTIMEDIA = "multimedia"
    REMINDERS = "reminders"
    PRESENTATIONS = "presentations"
    DATE_TIME = "date_time"
    SYSTEM = "system"
    LILITH = "lilith"
    UI = "ui"
    AGENT = "agent"


class RiskLevel(Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ToolDefinition:
    """Metadata for a registered JARVIS tool."""

    name: str
    description: str = ""
    schema: dict[str, Any] = field(default_factory=dict)
    domain: ToolDomain | None = None

    handler: Callable[..., Any] | None = None

    capabilities: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    side_effects: bool = False

    requires_approval: bool = False
    timeout_seconds: float | None = None

    enabled: bool = True
    source: str = "jarvis"
    version: str = "1.0"


class ToolRegistryError(Exception):
    pass


class ToolRegistry:
    """Central catalogue of JARVIS tools.

    The registry discovers and organizes tools. It does NOT authorize
    or execute them — that remains with JARVIS authority guards.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name:
            raise ToolRegistryError("tool name is required")
        if tool.name in self._tools:
            raise ToolRegistryError(f"duplicate tool name: {tool.name!r}")
        if tool.schema and not isinstance(tool.schema, dict):
            raise ToolRegistryError(f"invalid schema for {tool.name!r}: must be dict")
        for cap in tool.capabilities:
            if not isinstance(cap, str) or not cap.strip():
                raise ToolRegistryError(f"invalid capability {cap!r} on tool {tool.name!r}")
        self._tools[tool.name] = tool
        logger.debug("registered tool: %s (domain=%s)", tool.name, tool.domain)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list(self, *, domain: ToolDomain | None = None, enabled_only: bool = False) -> list[ToolDefinition]:
        tools = list(self._tools.values())
        if domain is not None:
            tools = [t for t in tools if t.domain == domain]
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        return tools

    def contains(self, name: str) -> bool:
        return name in self._tools

    def validate(self) -> list[str]:
        """Return a list of validation warnings."""
        warnings = []
        for tool in self._tools.values():
            if not tool.description:
                warnings.append(f"{tool.name}: missing description")
            if tool.handler is None:
                warnings.append(f"{tool.name}: missing handler")
            if tool.domain is None:
                warnings.append(f"{tool.name}: missing domain")
        return warnings

    def remove(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def count(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools.keys())


def catalogue_from_declarations(declarations: list[dict[str, Any]]) -> ToolRegistry:
    """Build a ToolRegistry from JARVIS TOOL_DECLARATIONS format.

    This creates metadata-only entries (no handlers) for parity checking.
    """
    registry = ToolRegistry()
    for decl in declarations:
        name = decl.get("name", "")
        if not name:
            continue
        tool = ToolDefinition(
            name=name,
            description=decl.get("description", ""),
            schema=decl.get("parameters", {}),
        )
        registry.register(tool)
    return registry
