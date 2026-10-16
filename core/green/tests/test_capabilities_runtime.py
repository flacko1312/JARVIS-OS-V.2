"""Tests for Capabilities Runtime — Phase 5 of GREEN runtime integration."""
from __future__ import annotations

import unittest
from unittest.mock import patch

_FLAG = "core.green.capabilities_runtime.CAPABILITIES_RUNTIME_ENABLED"


class TestDisabledIsNoop(unittest.TestCase):
    @patch(_FLAG, False)
    def test_get_tool_capability_disabled(self):
        from core.green.capabilities_runtime import get_tool_capability
        assert get_tool_capability("open_app") is None

    @patch(_FLAG, False)
    def test_get_agent_capability_disabled(self):
        from core.green.capabilities_runtime import get_agent_capability
        assert get_agent_capability("agent_executor") is None

    @patch(_FLAG, False)
    def test_list_by_domain_disabled(self):
        from core.green.capabilities_runtime import list_capabilities_by_domain
        assert list_capabilities_by_domain("windows") == []

    @patch(_FLAG, False)
    def test_list_by_tag_disabled(self):
        from core.green.capabilities_runtime import list_capabilities_by_tag
        assert list_capabilities_by_tag("filesystem.read") == []

    @patch(_FLAG, False)
    def test_list_all_agents_disabled(self):
        from core.green.capabilities_runtime import list_all_agents
        assert list_all_agents() == []

    @patch(_FLAG, False)
    def test_summary_disabled(self):
        from core.green.capabilities_runtime import capability_summary
        result = capability_summary()
        assert result == {"enabled": False}


class TestToolCapabilityLookup(unittest.TestCase):
    @patch(_FLAG, True)
    def test_known_tool(self):
        from core.green.capabilities_runtime import get_tool_capability
        info = get_tool_capability("open_app")
        assert info is not None
        assert info.tool_name == "open_app"
        assert info.domain == "windows"
        assert info.side_effects is True
        assert len(info.capabilities) > 0

    @patch(_FLAG, True)
    def test_unknown_tool(self):
        from core.green.capabilities_runtime import get_tool_capability
        assert get_tool_capability("nonexistent_tool") is None

    @patch(_FLAG, True)
    def test_read_only_tool(self):
        from core.green.capabilities_runtime import get_tool_capability
        info = get_tool_capability("date_time")
        assert info is not None
        assert info.side_effects is False

    @patch(_FLAG, True)
    def test_lilith_tool(self):
        from core.green.capabilities_runtime import get_tool_capability
        info = get_tool_capability("lilith_home_action")
        assert info is not None
        assert info.domain == "lilith"


class TestAgentCapabilityLookup(unittest.TestCase):
    @patch(_FLAG, True)
    def test_known_agent(self):
        from core.green.capabilities_runtime import get_agent_capability
        info = get_agent_capability("agent_executor")
        assert info is not None
        assert info.agent_id == "agent_executor"
        assert "planning" in info.capabilities

    @patch(_FLAG, True)
    def test_unknown_agent(self):
        from core.green.capabilities_runtime import get_agent_capability
        assert get_agent_capability("nonexistent") is None

    @patch(_FLAG, True)
    def test_all_agents(self):
        from core.green.capabilities_runtime import list_all_agents
        agents = list_all_agents()
        assert len(agents) == 3
        ids = [a.agent_id for a in agents]
        assert "agent_executor" in ids
        assert "dev_agent" in ids
        assert "deep_research" in ids


class TestDomainQuery(unittest.TestCase):
    @patch(_FLAG, True)
    def test_windows_domain(self):
        from core.green.capabilities_runtime import list_capabilities_by_domain
        tools = list_capabilities_by_domain("windows")
        assert len(tools) >= 3
        names = [t.tool_name for t in tools]
        assert "open_app" in names

    @patch(_FLAG, True)
    def test_empty_domain(self):
        from core.green.capabilities_runtime import list_capabilities_by_domain
        tools = list_capabilities_by_domain("nonexistent_domain")
        assert tools == []


class TestTagQuery(unittest.TestCase):
    @patch(_FLAG, True)
    def test_filesystem_read(self):
        from core.green.capabilities_runtime import list_capabilities_by_tag
        tools = list_capabilities_by_tag("filesystem.read")
        assert len(tools) >= 1
        names = [t.tool_name for t in tools]
        assert "file_controller" in names

    @patch(_FLAG, True)
    def test_memory_write(self):
        from core.green.capabilities_runtime import list_capabilities_by_tag
        tools = list_capabilities_by_tag("memory.write")
        names = [t.tool_name for t in tools]
        assert "save_memory" in names
        assert "lilith_memory_store" in names

    @patch(_FLAG, True)
    def test_nonexistent_tag(self):
        from core.green.capabilities_runtime import list_capabilities_by_tag
        assert list_capabilities_by_tag("nonexistent.tag") == []


class TestCapabilitySummary(unittest.TestCase):
    @patch(_FLAG, True)
    def test_summary_structure(self):
        from core.green.capabilities_runtime import capability_summary
        s = capability_summary()
        assert s["enabled"] is True
        assert s["total_tools"] == 48
        assert s["total_agents"] == 3
        assert isinstance(s["domains"], dict)
        assert len(s["domains"]) > 0
        assert isinstance(s["unique_capability_tags"], list)
        assert s["tools_with_side_effects"] > 0

    @patch(_FLAG, True)
    def test_all_domains_present(self):
        from core.green.capabilities_runtime import capability_summary
        s = capability_summary()
        assert "windows" in s["domains"]
        assert "lilith" in s["domains"]
        assert "web" in s["domains"]

    @patch(_FLAG, True)
    def test_tags_sorted(self):
        from core.green.capabilities_runtime import capability_summary
        s = capability_summary()
        tags = s["unique_capability_tags"]
        assert tags == sorted(tags)


class TestNoExecution(unittest.TestCase):
    @patch(_FLAG, True)
    def test_lookup_does_not_execute_tool(self):
        from core.green.capabilities_runtime import get_tool_capability
        info = get_tool_capability("computer_control")
        assert info is not None
        # Lookup returns metadata only, no execution happened

    @patch(_FLAG, True)
    def test_agent_lookup_does_not_execute(self):
        from core.green.capabilities_runtime import get_agent_capability
        info = get_agent_capability("agent_executor")
        assert info is not None
        assert info.status == "created"


if __name__ == "__main__":
    unittest.main()
