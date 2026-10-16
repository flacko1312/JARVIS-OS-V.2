"""Tests for Tool Registry — Phase 3 of GREEN Foundation."""
from __future__ import annotations

import unittest

from core.green.tool_registry import (
    RiskLevel,
    ToolDefinition,
    ToolDomain,
    ToolRegistry,
    ToolRegistryError,
    catalogue_from_declarations,
)


def _dummy_handler(**kwargs):
    return "ok"


class TestToolRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()

    def test_register_and_get(self):
        tool = ToolDefinition(name="test_tool", handler=_dummy_handler)
        self.registry.register(tool)
        assert self.registry.get("test_tool") is tool

    def test_get_missing(self):
        assert self.registry.get("nonexistent") is None

    def test_contains(self):
        self.registry.register(ToolDefinition(name="x"))
        assert self.registry.contains("x")
        assert not self.registry.contains("y")

    def test_duplicate_rejection(self):
        self.registry.register(ToolDefinition(name="dup"))
        with self.assertRaises(ToolRegistryError):
            self.registry.register(ToolDefinition(name="dup"))

    def test_empty_name_rejected(self):
        with self.assertRaises(ToolRegistryError):
            self.registry.register(ToolDefinition(name=""))

    def test_invalid_schema_rejected(self):
        with self.assertRaises(ToolRegistryError):
            self.registry.register(ToolDefinition(name="bad", schema="not a dict"))  # type: ignore[arg-type]

    def test_invalid_capability_rejected(self):
        with self.assertRaises(ToolRegistryError):
            self.registry.register(ToolDefinition(name="bad", capabilities=[""]))

    def test_list_all(self):
        self.registry.register(ToolDefinition(name="a"))
        self.registry.register(ToolDefinition(name="b"))
        assert len(self.registry.list()) == 2

    def test_list_by_domain(self):
        self.registry.register(ToolDefinition(name="a", domain=ToolDomain.WEB))
        self.registry.register(ToolDefinition(name="b", domain=ToolDomain.FILES))
        self.registry.register(ToolDefinition(name="c", domain=ToolDomain.WEB))
        web_tools = self.registry.list(domain=ToolDomain.WEB)
        assert len(web_tools) == 2

    def test_list_enabled_only(self):
        self.registry.register(ToolDefinition(name="on", enabled=True))
        self.registry.register(ToolDefinition(name="off", enabled=False))
        assert len(self.registry.list(enabled_only=True)) == 1

    def test_validate_warnings(self):
        self.registry.register(ToolDefinition(name="no_desc"))
        warnings = self.registry.validate()
        assert any("missing description" in w for w in warnings)
        assert any("missing handler" in w for w in warnings)
        assert any("missing domain" in w for w in warnings)

    def test_validate_clean(self):
        self.registry.register(ToolDefinition(
            name="good", description="A tool", handler=_dummy_handler,
            domain=ToolDomain.SYSTEM,
        ))
        assert len(self.registry.validate()) == 0

    def test_remove(self):
        self.registry.register(ToolDefinition(name="rm"))
        assert self.registry.remove("rm")
        assert not self.registry.contains("rm")
        assert not self.registry.remove("rm")

    def test_count(self):
        assert self.registry.count() == 0
        self.registry.register(ToolDefinition(name="x"))
        assert self.registry.count() == 1

    def test_names_sorted(self):
        self.registry.register(ToolDefinition(name="z"))
        self.registry.register(ToolDefinition(name="a"))
        assert self.registry.names() == ["a", "z"]

    def test_disabled_tool_accessible(self):
        self.registry.register(ToolDefinition(name="dis", enabled=False))
        assert self.registry.get("dis") is not None

    def test_parity_with_declarations(self):
        decls = [
            {"name": "open_app", "description": "Opens apps", "parameters": {"type": "OBJECT"}},
            {"name": "web_search", "description": "Search"},
        ]
        reg = catalogue_from_declarations(decls)
        assert reg.contains("open_app")
        assert reg.contains("web_search")
        assert reg.count() == 2

    def test_catalogue_skips_empty_names(self):
        decls = [{"name": ""}, {"description": "no name"}]
        reg = catalogue_from_declarations(decls)
        assert reg.count() == 0

    def test_no_direct_authority_bypass(self):
        tool = ToolDefinition(name="test", handler=_dummy_handler)
        self.registry.register(tool)
        # The registry stores metadata; it never calls the handler itself
        retrieved = self.registry.get("test")
        assert retrieved is not None
        assert retrieved.handler is _dummy_handler
        # Verify the registry has no execute method
        assert not hasattr(self.registry, "execute")

    def test_deterministic_metadata(self):
        tool = ToolDefinition(
            name="dt", description="d", domain=ToolDomain.WEB,
            risk_level=RiskLevel.MEDIUM, side_effects=True,
        )
        self.registry.register(tool)
        t = self.registry.get("dt")
        assert t.risk_level == RiskLevel.MEDIUM
        assert t.side_effects is True


if __name__ == "__main__":
    unittest.main()
