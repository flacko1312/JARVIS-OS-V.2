"""Block 7 tests — LILITH/domótica expansion.

Tests: permission enforcement on home_action and routine handlers,
toggle support, lilith_home_status wiring, permission system coverage.
"""
import ast
import unittest


class TestHomeActionToggleSupport(unittest.TestCase):
    """Verify toggle is now a supported home action."""

    def test_toggle_in_enum(self):
        """The tool declaration should list toggle in the enum."""
        with open("main.py") as f:
            content = f.read()
        self.assertIn('"toggle"', content)
        self.assertIn('"enum": ["turn_on", "turn_off", "toggle"]', content)

    def test_toggle_in_handler(self):
        """The handler should accept toggle as a valid action."""
        with open("main.py") as f:
            content = f.read()
        self.assertIn('("turn_on", "turn_off", "toggle")', content)


class TestPermissionEnforcementWiring(unittest.TestCase):
    """Verify permission checks are wired into LILITH handlers."""

    def test_home_action_has_permission_check(self):
        with open("main.py") as f:
            content = f.read()
        # Find the home_action handler section
        idx = content.find('elif name == "lilith_home_action":')
        self.assertGreater(idx, 0)
        handler_block = content[idx:idx + 2000]
        self.assertIn("check_permission", handler_block)
        self.assertIn("PermissionLevel.DENIED", handler_block)

    def test_routine_has_permission_check(self):
        with open("main.py") as f:
            content = f.read()
        idx = content.find('elif name == "lilith_routine":')
        self.assertGreater(idx, 0)
        handler_block = content[idx:idx + 2000]
        self.assertIn("check_permission", handler_block)
        self.assertIn("PermissionLevel.DENIED", handler_block)


class TestPermissionRulesCoverage(unittest.TestCase):
    """Verify all LILITH tools have permission rules."""

    def test_home_action_rules(self):
        from core.headless_permissions import check_permission, PermissionLevel
        safe = ["turn_on", "turn_off", "toggle"]
        for action in safe:
            rule = check_permission("lilith_home_action", action)
            self.assertEqual(rule.level, PermissionLevel.SAFE_WRITE, f"{action} should be SAFE_WRITE")

        confirm = ["lock", "unlock"]
        for action in confirm:
            rule = check_permission("lilith_home_action", action)
            self.assertEqual(rule.level, PermissionLevel.CONFIRM_REQUIRED, f"{action} should need confirmation")

    def test_routine_rules(self):
        from core.headless_permissions import check_permission, PermissionLevel
        read_ops = ["list", "get", "history"]
        for op in read_ops:
            rule = check_permission("lilith_routine", op)
            self.assertEqual(rule.level, PermissionLevel.READ_ONLY, f"routine/{op} should be READ_ONLY")

        confirm_ops = ["create", "update", "enable", "disable", "delete"]
        for op in confirm_ops:
            rule = check_permission("lilith_routine", op)
            self.assertEqual(rule.level, PermissionLevel.CONFIRM_REQUIRED, f"routine/{op} should need confirmation")

    def test_memory_rules(self):
        from core.headless_permissions import check_permission, PermissionLevel
        rule = check_permission("lilith_memory_search")
        self.assertEqual(rule.level, PermissionLevel.READ_ONLY)
        rule = check_permission("lilith_memory_store")
        self.assertEqual(rule.level, PermissionLevel.SAFE_WRITE)
        rule = check_permission("lilith_memory_delete")
        self.assertEqual(rule.level, PermissionLevel.CONFIRM_REQUIRED)

    def test_health_rule(self):
        from core.headless_permissions import check_permission, PermissionLevel
        rule = check_permission("lilith_health")
        self.assertEqual(rule.level, PermissionLevel.READ_ONLY)

    def test_home_status_rule(self):
        from core.headless_permissions import check_permission, PermissionLevel
        rule = check_permission("lilith_home_status")
        self.assertEqual(rule.level, PermissionLevel.READ_ONLY)


class TestLilithHomeStatusDeclaration(unittest.TestCase):
    """Verify lilith_home_status tool declaration exists."""

    def test_declaration_exists(self):
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
        self.assertIn("lilith_home_status", decl_names)

    def test_handler_exists(self):
        with open("main.py") as f:
            content = f.read()
        self.assertIn('elif name == "lilith_home_status":', content)

    def test_in_headless_actions(self):
        with open("main.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "HEADLESS_ACTIONS":
                        if isinstance(node.value, ast.Call) and node.value.args:
                            names = {
                                e.value for e in node.value.args[0].elts
                                if isinstance(e, ast.Constant)
                            }
                            self.assertIn("lilith_home_status", names)
                            return
        self.fail("HEADLESS_ACTIONS not found")


class TestToggleVerification(unittest.TestCase):
    """Verify toggle state verification doesn't require expected state."""

    def test_toggle_expected_none(self):
        with open("main.py") as f:
            content = f.read()
        self.assertIn('if action_name == "toggle":', content)
        self.assertIn("expected = None", content)
        self.assertIn("if expected is None or current == expected:", content)
        self.assertIn("if expected is None:", content)


if __name__ == "__main__":
    unittest.main()
