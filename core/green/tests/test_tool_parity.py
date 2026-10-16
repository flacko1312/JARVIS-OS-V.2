"""Tests for Tool Registry shadow parity — Phase 3 of GREEN runtime integration."""
from __future__ import annotations

import unittest

import main
from core.green.tool_metadata import (
    TOOL_DOMAIN_MAP,
    TOOL_RISK_MAP,
    TOOL_CAPABILITIES_MAP,
    TOOL_SIDE_EFFECTS,
    enrich_registry_from_declarations,
    check_parity,
)
from core.green.tool_registry import (
    ToolDomain,
    RiskLevel,
    ToolRegistry,
    catalogue_from_declarations,
)


class TestParityCheck(unittest.TestCase):
    def test_full_parity(self):
        report = check_parity(main.TOOL_DECLARATIONS)
        assert report["parity"], (
            f"Parity failed:\n"
            f"  missing_in_metadata: {report['missing_in_metadata']}\n"
            f"  extra_in_metadata: {report['extra_in_metadata']}"
        )

    def test_declaration_count_matches(self):
        report = check_parity(main.TOOL_DECLARATIONS)
        assert report["declaration_count"] == 48
        assert report["metadata_count"] == 48

    def test_no_missing_risk_mapping(self):
        report = check_parity(main.TOOL_DECLARATIONS)
        assert report["missing_risk_mapping"] == []

    def test_no_missing_capabilities_mapping(self):
        report = check_parity(main.TOOL_DECLARATIONS)
        assert report["missing_capabilities_mapping"] == []

    def test_no_missing_side_effects_mapping(self):
        report = check_parity(main.TOOL_DECLARATIONS)
        assert report["missing_side_effects_mapping"] == []


class TestEnrichedRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = enrich_registry_from_declarations(main.TOOL_DECLARATIONS)

    def test_all_tools_registered(self):
        assert self.registry.count() == 48

    def test_tools_have_domains(self):
        for tool in self.registry.list():
            assert tool.domain is not None, f"{tool.name} missing domain"

    def test_tools_have_descriptions(self):
        for tool in self.registry.list():
            assert tool.description, f"{tool.name} missing description"

    def test_tools_have_schemas(self):
        for tool in self.registry.list():
            assert tool.schema, f"{tool.name} missing schema"

    def test_tools_have_capabilities(self):
        for tool in self.registry.list():
            assert len(tool.capabilities) > 0, f"{tool.name} missing capabilities"

    def test_lilith_tools_have_lilith_domain(self):
        for tool in self.registry.list(domain=ToolDomain.LILITH):
            assert tool.name.startswith("lilith_"), (
                f"Non-lilith tool {tool.name} in LILITH domain"
            )

    def test_read_only_tools_no_side_effects(self):
        for tool in self.registry.list():
            if tool.risk_level == RiskLevel.READ_ONLY:
                assert not tool.side_effects, (
                    f"READ_ONLY tool {tool.name} marked as having side effects"
                )

    def test_high_risk_tools_have_side_effects(self):
        for tool in self.registry.list():
            if tool.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                assert tool.side_effects, (
                    f"HIGH/CRITICAL tool {tool.name} should have side effects"
                )


class TestCatalogueFromDeclarations(unittest.TestCase):
    def test_basic_catalogue(self):
        registry = catalogue_from_declarations(main.TOOL_DECLARATIONS)
        assert registry.count() == 48

    def test_names_match(self):
        registry = catalogue_from_declarations(main.TOOL_DECLARATIONS)
        decl_names = sorted(d["name"] for d in main.TOOL_DECLARATIONS)
        reg_names = registry.names()
        assert decl_names == reg_names


class TestRegistryNoExecution(unittest.TestCase):
    def test_no_execute_method(self):
        registry = enrich_registry_from_declarations(main.TOOL_DECLARATIONS)
        assert not hasattr(registry, "execute")

    def test_no_handler_set(self):
        registry = enrich_registry_from_declarations(main.TOOL_DECLARATIONS)
        for tool in registry.list():
            assert tool.handler is None, (
                f"{tool.name} should not have a handler in shadow mode"
            )


class TestDomainConsistency(unittest.TestCase):
    def test_every_declared_tool_mapped(self):
        for decl in main.TOOL_DECLARATIONS:
            name = decl["name"]
            assert name in TOOL_DOMAIN_MAP, f"{name} not in TOOL_DOMAIN_MAP"
            assert name in TOOL_RISK_MAP, f"{name} not in TOOL_RISK_MAP"
            assert name in TOOL_CAPABILITIES_MAP, f"{name} not in TOOL_CAPABILITIES_MAP"
            assert name in TOOL_SIDE_EFFECTS, f"{name} not in TOOL_SIDE_EFFECTS"

    def test_no_extra_metadata(self):
        decl_names = {d["name"] for d in main.TOOL_DECLARATIONS}
        for name in TOOL_DOMAIN_MAP:
            assert name in decl_names, f"Extra in TOOL_DOMAIN_MAP: {name}"

    def test_domain_values_valid(self):
        for name, domain in TOOL_DOMAIN_MAP.items():
            assert isinstance(domain, ToolDomain), f"{name}: invalid domain {domain}"

    def test_risk_values_valid(self):
        for name, risk in TOOL_RISK_MAP.items():
            assert isinstance(risk, RiskLevel), f"{name}: invalid risk {risk}"


if __name__ == "__main__":
    unittest.main()
