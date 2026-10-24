"""Tests for the Headless system prompt — ensures it matches the current tool profile."""
import ast
import re
import unittest


def _read_main():
    with open("main.py", encoding="utf-8") as f:
        return f.read()


class TestHeadlessSystemRules(unittest.TestCase):
    """Verify HEADLESS_SYSTEM_RULES reflects the current tool profile."""

    EXPECTED_TOOLS = {
        "web_search", "date_time", "system_status", "disk_status", "docker_status",
        "infrastructure_status", "service_logs", "process_list", "process_info",
        "systemd_status", "systemd_action", "systemd_list_failed", "journal_read",
        "lilith_memory_search", "lilith_memory_store", "lilith_memory_delete",
        "lilith_home_action", "lilith_home_status", "lilith_health",
        "lilith_routine", "open_capabilities_catalog",
    }

    def _get_rules_text(self):
        src = _read_main()
        match = re.search(
            r'HEADLESS_SYSTEM_RULES\s*=\s*"""(.*?)"""\s*\.strip\(\)',
            src, re.DOTALL,
        )
        self.assertIsNotNone(match, "HEADLESS_SYSTEM_RULES not found in main.py")
        return match.group(1)

    def test_contains_all_16_tools(self):
        rules = self._get_rules_text()
        for tool in self.EXPECTED_TOOLS:
            self.assertIn(tool, rules, f"Tool '{tool}' missing from HEADLESS_SYSTEM_RULES")

    def test_does_not_contain_old_5_tool_list(self):
        rules = self._get_rules_text()
        old_pattern = (
            "lilith_memory_search, lilith_memory_store, lilith_memory_delete, "
            "lilith_home_action,\nand lilith_routine."
        )
        self.assertNotIn(old_pattern, rules,
                         "Old 5-tool list still present in HEADLESS_SYSTEM_RULES")

    def test_does_not_prohibit_date_time(self):
        rules = self._get_rules_text()
        self.assertNotIn("do not call date_time", rules.lower(),
                         "Stale 'do not call date_time' prohibition found")
        self.assertNotIn("not exposed in this headless", rules.lower(),
                         "Stale 'not exposed' prohibition found")

    def test_mandates_date_time(self):
        rules = self._get_rules_text()
        self.assertIn("date_time", rules)
        self.assertTrue(
            "mandatory" in rules.lower() or "must" in rules.lower()
            or "MANDATORY" in rules,
            "HEADLESS_SYSTEM_RULES should mandate date_time for time/date",
        )

    def test_matches_headless_actions(self):
        """HEADLESS_ACTIONS frozenset should match the tools named in the prompt."""
        src = _read_main()
        match = re.search(
            r'HEADLESS_ACTIONS\s*=\s*frozenset\(\{([^}]+)\}\)', src, re.DOTALL,
        )
        self.assertIsNotNone(match, "HEADLESS_ACTIONS not found")
        actions = set(re.findall(r'"([^"]+)"', match.group(1)))
        self.assertEqual(actions, self.EXPECTED_TOOLS,
                         f"HEADLESS_ACTIONS mismatch: extra={actions - self.EXPECTED_TOOLS}, "
                         f"missing={self.EXPECTED_TOOLS - actions}")

    def test_no_approval_tools_in_prompt(self):
        rules = self._get_rules_text()
        self.assertNotIn("request_approval", rules)
        self.assertNotIn("resolve_approval", rules)


class TestHeadlessPromptConstruction(unittest.TestCase):
    """Verify the headless code path includes DATE_TIME_AUTHORITY_RULE."""

    def test_headless_includes_date_time_rule(self):
        src = _read_main()
        # Find the headless branch of prompt construction
        match = re.search(
            r'if\s+getattr\(self,\s*"headless".*?parts\s*=\s*\[(.*?)\]',
            src, re.DOTALL,
        )
        self.assertIsNotNone(match, "Headless prompt parts block not found")
        parts_block = match.group(1)
        self.assertIn("DATE_TIME_AUTHORITY_RULE", parts_block,
                       "DATE_TIME_AUTHORITY_RULE missing from headless prompt parts")

    def test_date_time_rule_no_windows_ref(self):
        src = _read_main()
        match = re.search(
            r'DATE_TIME_AUTHORITY_RULE\s*=\s*"""(.*?)"""',
            src, re.DOTALL,
        )
        self.assertIsNotNone(match)
        rule_text = match.group(1)
        self.assertNotIn("Windows host", rule_text,
                         "DATE_TIME_AUTHORITY_RULE still references 'Windows host'")


if __name__ == "__main__":
    unittest.main()
