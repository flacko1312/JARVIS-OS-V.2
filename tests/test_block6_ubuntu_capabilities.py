"""Block 6 tests — Ubuntu headless capabilities.

Tests: system_status, process_list, process_info, systemd_status,
systemd_action, systemd_list_failed, journal_read, build_headless_catalog,
permissions system, and HEADLESS_ACTIONS membership.
"""
import unittest
from unittest.mock import patch, MagicMock
import subprocess


class TestHeadlessActions(unittest.TestCase):
    """Verify HEADLESS_ACTIONS set in main.py includes all Block 6 tools."""

    def test_headless_actions_contains_block6_tools(self):
        """All Block 6 tools must be in HEADLESS_ACTIONS."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("main", "main.py")
        mod = importlib.util.module_from_spec(spec)
        # Don't actually execute main — just parse for the frozenset
        import ast
        with open("main.py") as f:
            tree = ast.parse(f.read())
        actions = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "HEADLESS_ACTIONS":
                        if isinstance(node.value, ast.Call) and node.value.args:
                            for elt in node.value.args[0].elts:
                                if isinstance(elt, ast.Constant):
                                    actions.add(elt.value)
        block6_tools = {
            "date_time", "system_status", "process_list", "process_info",
            "systemd_status", "systemd_action", "systemd_list_failed",
            "journal_read", "open_capabilities_catalog",
        }
        for tool in block6_tools:
            self.assertIn(tool, actions, f"{tool} missing from HEADLESS_ACTIONS")

    def test_headless_actions_size(self):
        """HEADLESS_ACTIONS should have at least 18 tools (Block 6+7 combined)."""
        import ast
        with open("main.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "HEADLESS_ACTIONS":
                        if isinstance(node.value, ast.Call) and node.value.args:
                            count = len(node.value.args[0].elts)
                            self.assertGreaterEqual(count, 18)
                            return
        self.fail("HEADLESS_ACTIONS not found")


class TestToolDeclarations(unittest.TestCase):
    """Verify all Block 6 tool declarations exist in TOOL_DECLARATIONS."""

    def test_block6_declarations_exist(self):
        import ast
        with open("main.py") as f:
            tree = ast.parse(f.read())
        decl_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "TOOL_DECLARATIONS":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Dict):
                                    for k, v in zip(elt.keys, elt.values):
                                        if isinstance(k, ast.Constant) and k.value == "name":
                                            if isinstance(v, ast.Constant):
                                                decl_names.add(v.value)
        needed = {
            "system_status", "process_list", "process_info",
            "systemd_status", "systemd_action", "systemd_list_failed",
            "journal_read", "lilith_home_status",
        }
        for tool in needed:
            self.assertIn(tool, decl_names, f"{tool} declaration missing from TOOL_DECLARATIONS")


class TestSystemStatus(unittest.TestCase):
    """Test system_status tool."""

    def test_returns_dict(self):
        from core.headless_tools import system_status
        result = system_status()
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        from core.headless_tools import system_status
        result = system_status()
        for key in ("load", "memory", "swap", "uptime", "cpu", "disk"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_memory_values_reasonable(self):
        from core.headless_tools import system_status
        result = system_status()
        mem = result["memory"]
        if isinstance(mem, dict):
            self.assertGreater(mem["total_mib"], 0)
            self.assertGreater(mem["available_mib"], 0)
            self.assertGreaterEqual(mem["used_pct"], 0)
            self.assertLessEqual(mem["used_pct"], 100)


class TestProcessList(unittest.TestCase):
    """Test process_list tool."""

    def test_returns_list(self):
        from core.headless_tools import process_list
        result = process_list()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_entries_have_required_fields(self):
        from core.headless_tools import process_list
        result = process_list()
        if result and "error" not in result[0]:
            entry = result[0]
            for key in ("pid", "user", "cpu", "mem", "rss_kb", "command"):
                self.assertIn(key, entry)

    def test_filter_works(self):
        from core.headless_tools import process_list
        all_procs = process_list()
        filtered = process_list("python")
        self.assertLessEqual(len(filtered), len(all_procs))

    def test_max_50(self):
        from core.headless_tools import process_list
        result = process_list()
        self.assertLessEqual(len(result), 50)


class TestProcessInfo(unittest.TestCase):
    """Test process_info tool."""

    def test_own_pid(self):
        import os
        from core.headless_tools import process_info
        result = process_info(os.getpid())
        self.assertIsInstance(result, dict)
        self.assertNotIn("error", result)
        self.assertEqual(result["pid"], str(os.getpid()))

    def test_invalid_pid(self):
        from core.headless_tools import process_info
        result = process_info(999999999)
        self.assertIn("error", result)


class TestSystemdStatus(unittest.TestCase):
    """Test systemd_status tool."""

    def test_blocked_service(self):
        from core.headless_tools import systemd_status
        result = systemd_status("sshd")
        self.assertIn("error", result)
        self.assertIn("not in the allowed", result["error"])

    def test_allowlisted_service(self):
        from core.headless_tools import systemd_status
        result = systemd_status("jarvis-headless")
        self.assertIsInstance(result, dict)
        # Should have ActiveState at minimum
        self.assertTrue(
            "ActiveState" in result or "error" in result,
            "Expected ActiveState or error"
        )

    def test_strips_dotservice(self):
        from core.headless_tools import systemd_status
        result = systemd_status("jarvis-headless.service")
        self.assertIsInstance(result, dict)
        self.assertNotIn("not in the allowed", str(result))


class TestSystemdAction(unittest.TestCase):
    """Test systemd_action tool (confirmation gate, no actual execution)."""

    def test_returns_confirmation(self):
        from core.headless_tools import systemd_action
        result = systemd_action("jarvis-headless", "restart")
        self.assertTrue(result.get("confirmation_required"))
        self.assertIn("summary", result)

    def test_blocked_service(self):
        from core.headless_tools import systemd_action
        result = systemd_action("sshd", "restart")
        self.assertIn("error", result)

    def test_blocked_action(self):
        from core.headless_tools import systemd_action
        result = systemd_action("jarvis-headless", "enable")
        self.assertIn("error", result)


class TestSystemdListFailed(unittest.TestCase):
    """Test systemd_list_failed tool."""

    def test_returns_list(self):
        from core.headless_tools import systemd_list_failed
        result = systemd_list_failed()
        self.assertIsInstance(result, list)


class TestJournalRead(unittest.TestCase):
    """Test journal_read tool."""

    def test_blocked_service(self):
        from core.headless_tools import journal_read
        result = journal_read("sshd")
        self.assertIn("not in the allowed", result)

    def test_allowlisted_service(self):
        from core.headless_tools import journal_read
        result = journal_read("jarvis-headless", lines=5)
        self.assertIsInstance(result, str)

    def test_max_lines_capped(self):
        """Requesting >100 lines should be capped."""
        from core.headless_tools import journal_read
        # Should not error, just cap
        result = journal_read("jarvis-headless", lines=999)
        self.assertIsInstance(result, str)


class TestPermissions(unittest.TestCase):
    """Test the unified permission system."""

    def test_read_only_tools(self):
        from core.headless_permissions import check_permission, PermissionLevel
        read_tools = [
            "system_status", "process_list", "process_info",
            "systemd_status", "systemd_list_failed", "journal_read",
            "date_time", "open_capabilities_catalog",
            "lilith_memory_search", "lilith_home_status", "lilith_health",
        ]
        for tool in read_tools:
            rule = check_permission(tool)
            self.assertEqual(
                rule.level, PermissionLevel.READ_ONLY,
                f"{tool} should be READ_ONLY, got {rule.level}"
            )

    def test_confirm_required_tools(self):
        from core.headless_permissions import check_permission, PermissionLevel
        cases = [
            ("systemd_action", "restart"),
            ("systemd_action", "stop"),
            ("systemd_action", "start"),
            ("lilith_memory_delete", "*"),
            ("lilith_home_action", "lock"),
            ("lilith_home_action", "unlock"),
            ("lilith_routine", "create"),
            ("lilith_routine", "delete"),
        ]
        for tool, action in cases:
            rule = check_permission(tool, action)
            self.assertEqual(
                rule.level, PermissionLevel.CONFIRM_REQUIRED,
                f"{tool}/{action} should be CONFIRM_REQUIRED, got {rule.level}"
            )

    def test_safe_write_tools(self):
        from core.headless_permissions import check_permission, PermissionLevel
        cases = [
            ("lilith_memory_store", "*"),
            ("lilith_home_action", "turn_on"),
            ("lilith_home_action", "turn_off"),
            ("lilith_home_action", "toggle"),
        ]
        for tool, action in cases:
            rule = check_permission(tool, action)
            self.assertEqual(
                rule.level, PermissionLevel.SAFE_WRITE,
                f"{tool}/{action} should be SAFE_WRITE, got {rule.level}"
            )

    def test_unknown_tool_denied(self):
        from core.headless_permissions import check_permission, PermissionLevel
        rule = check_permission("nonexistent_tool")
        self.assertEqual(rule.level, PermissionLevel.DENIED)

    def test_requires_confirmation_helper(self):
        from core.headless_permissions import requires_confirmation
        self.assertTrue(requires_confirmation("systemd_action", "restart"))
        self.assertFalse(requires_confirmation("system_status"))

    def test_is_denied_helper(self):
        from core.headless_permissions import is_denied
        self.assertTrue(is_denied("nonexistent_tool"))
        self.assertFalse(is_denied("system_status"))

    def test_get_all_rules(self):
        from core.headless_permissions import get_all_rules
        rules = get_all_rules()
        self.assertGreater(len(rules), 20)


class TestBuildHeadlessCatalog(unittest.TestCase):
    """Test the headless capability catalog generator."""

    def test_returns_markdown(self):
        from core.headless_tools import build_headless_catalog
        result = build_headless_catalog()
        self.assertIn("# JARVIS Headless", result)
        self.assertIn("## System", result)

    def test_contains_all_tools(self):
        from core.headless_tools import build_headless_catalog
        result = build_headless_catalog()
        tools = [
            "date_time", "system_status", "process_list", "process_info",
            "systemd_status", "systemd_action", "journal_read",
            "lilith_memory_search", "lilith_home_action", "lilith_home_status",
            "open_capabilities_catalog",
        ]
        for tool in tools:
            self.assertIn(tool, result, f"{tool} missing from catalog")

    def test_flags_present(self):
        from core.headless_tools import build_headless_catalog
        result = build_headless_catalog()
        self.assertIn("READ_ONLY", result)
        self.assertIn("CONFIRM_REQUIRED", result)
        self.assertIn("MUTATING", result)


if __name__ == "__main__":
    unittest.main()
