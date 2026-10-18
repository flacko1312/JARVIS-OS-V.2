"""Block 1 tests for JARVIS Headless V1.

Validates:
- HeadlessClient implements JarvisClient Protocol
- HEADLESS_ACTIONS tool profile is correct
- get_tool_declarations(headless=True) returns only allowed tools
- JarvisLive accepts headless=True without importing PyQt
- headless_conversation_store_path is independent from desktop
- No PyQt import contamination when using headless path
"""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class TestHeadlessClient(unittest.TestCase):
    """HeadlessClient implements JarvisClient Protocol."""

    def test_implements_jarvis_client_protocol(self):
        from core.jarvis_client import JarvisClient
        from headless_client import HeadlessClient

        client = HeadlessClient()
        self.assertIsInstance(client, JarvisClient)

    def test_initial_state(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        self.assertFalse(client.muted)
        self.assertIsNone(client.current_file)
        self.assertIsNone(client.on_text_command)
        self.assertEqual(client._state, "STANDBY")

    def test_mute_toggle(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        self.assertFalse(client.muted)
        result = client.toggle_mute()
        self.assertTrue(result)
        self.assertTrue(client.muted)
        result = client.toggle_mute()
        self.assertFalse(result)
        self.assertFalse(client.muted)

    def test_muted_setter(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.muted = True
        self.assertTrue(client.muted)
        client.muted = False
        self.assertFalse(client.muted)

    def test_set_state(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.set_state("LISTENING")
        self.assertEqual(client._state, "LISTENING")
        client.set_state("standby")
        self.assertEqual(client._state, "STANDBY")

    def test_write_log_no_crash(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.write_log("SYS: test message")
        client.write_log("")

    def test_noop_methods_no_crash(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.show_subtitle("hello")
        client.clear_subtitle()
        client.set_theme("dark")
        client.set_graphics_quality("low")
        client.sync_voice_display("Puck")
        client.handle_ui_command("some_action")

    def test_voice_combo_returns_selector(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        combo = client._voice_combo
        self.assertEqual(combo.currentIndex(), 0)
        self.assertIsNone(combo.itemData(0))
        self.assertEqual(combo.currentText(), "")

    def test_on_text_command_settable(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        called = []
        client.on_text_command = called.append
        client.on_text_command("test")
        self.assertEqual(called, ["test"])

    def test_on_conversation_toggle_settable(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        called = []
        client.on_conversation_toggle = lambda: called.append(True) or True
        client.on_conversation_toggle()
        self.assertEqual(called, [True])


class TestHeadlessToolProfile(unittest.TestCase):
    """HEADLESS_ACTIONS allowlist and get_tool_declarations(headless=True)."""

    def test_headless_actions_defined(self):
        from main import HEADLESS_ACTIONS

        self.assertIsInstance(HEADLESS_ACTIONS, frozenset)
        self.assertGreater(len(HEADLESS_ACTIONS), 0)

    def test_headless_actions_are_subset_of_all_tools(self):
        from main import HEADLESS_ACTIONS, TOOL_DECLARATIONS

        all_names = {d["name"] for d in TOOL_DECLARATIONS}
        missing = HEADLESS_ACTIONS - all_names
        self.assertEqual(missing, set(), f"HEADLESS_ACTIONS contains unknown tools: {missing}")

    def test_headless_excludes_windows_tools(self):
        from main import HEADLESS_ACTIONS, LOCAL_MACHINE_ONLY_ACTIONS

        overlap = HEADLESS_ACTIONS & LOCAL_MACHINE_ONLY_ACTIONS
        self.assertEqual(overlap, set(), f"Headless must not include Windows-only tools: {overlap}")

    def test_headless_excludes_dangerous_tools(self):
        from main import HEADLESS_ACTIONS

        forbidden = {
            "browser_control", "screen_process", "code_helper",
            "dev_agent", "agent_task", "game_updater",
        }
        overlap = HEADLESS_ACTIONS & forbidden
        self.assertEqual(overlap, set(), f"Headless must not include: {overlap}")

    def test_headless_includes_required_lilith_tools(self):
        from main import HEADLESS_ACTIONS

        required = {
            "lilith_memory_search",
            "lilith_memory_store",
            "lilith_memory_delete",
            "lilith_home_action",
            "lilith_routine",
        }
        missing = required - HEADLESS_ACTIONS
        self.assertEqual(missing, set(), f"Missing required LILITH tools: {missing}")

    def test_headless_exact_inventory(self):
        from main import HEADLESS_ACTIONS

        EXPECTED_HEADLESS_TOOLS = {
            "lilith_memory_search",
            "lilith_memory_store",
            "lilith_memory_delete",
            "lilith_home_action",
            "lilith_routine",
        }
        self.assertEqual(
            HEADLESS_ACTIONS,
            EXPECTED_HEADLESS_TOOLS,
            f"Extra: {HEADLESS_ACTIONS - EXPECTED_HEADLESS_TOOLS}, "
            f"Missing: {EXPECTED_HEADLESS_TOOLS - HEADLESS_ACTIONS}",
        )

    def test_get_tool_declarations_headless(self):
        from main import HEADLESS_ACTIONS, get_tool_declarations

        declarations = get_tool_declarations(headless=True)
        names = {d["name"] for d in declarations}
        self.assertEqual(names, HEADLESS_ACTIONS)

    def test_get_tool_declarations_default_unchanged(self):
        from main import TOOL_DECLARATIONS, get_tool_declarations

        declarations = get_tool_declarations()
        self.assertEqual(len(declarations), len(TOOL_DECLARATIONS))

    def test_get_tool_declarations_cloud_safe_unchanged(self):
        from main import CLOUD_SAFE_ACTIONS, get_tool_declarations

        declarations = get_tool_declarations(cloud_safe=True)
        names = {d["name"] for d in declarations}
        self.assertEqual(names, CLOUD_SAFE_ACTIONS)

    def test_headless_flag_wins_over_cloud_safe(self):
        from main import HEADLESS_ACTIONS, get_tool_declarations

        declarations = get_tool_declarations(headless=True, cloud_safe=True)
        names = {d["name"] for d in declarations}
        self.assertEqual(names, HEADLESS_ACTIONS)


class TestJarvisLiveHeadless(unittest.TestCase):
    """JarvisLive accepts headless flag and configures correctly."""

    def test_jarvis_live_accepts_headless(self):
        from headless_client import HeadlessClient
        from main import JarvisLive

        client = HeadlessClient()
        jarvis = JarvisLive(client, "Puck", headless=True)
        self.assertTrue(jarvis.headless)

    def test_jarvis_live_headless_has_correct_tools(self):
        from headless_client import HeadlessClient
        from main import HEADLESS_ACTIONS, JarvisLive

        client = HeadlessClient()
        jarvis = JarvisLive(client, "Puck", headless=True)
        names = {d["name"] for d in jarvis.tool_declarations}
        self.assertEqual(names, HEADLESS_ACTIONS)

    def test_jarvis_live_default_has_all_tools(self):
        from headless_client import HeadlessClient
        from main import TOOL_DECLARATIONS, JarvisLive

        client = HeadlessClient()
        jarvis = JarvisLive(client, "Puck")
        self.assertFalse(jarvis.headless)
        self.assertEqual(len(jarvis.tool_declarations), len(TOOL_DECLARATIONS))

    def test_jarvis_live_headless_conversation_store(self):
        import tempfile
        from headless_client import HeadlessClient
        from main import JarvisLive

        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "conversation_state_headless.json"
            jarvis = JarvisLive(
                HeadlessClient(),
                "Puck",
                headless=True,
                conversation_store_path=store_path,
            )
            self.assertIsNotNone(jarvis._conversation_store)
            self.assertEqual(jarvis._conversation_store.path, store_path)


class TestHeadlessConversationStorePath(unittest.TestCase):
    """Headless conversation store is separate from desktop."""

    def test_paths_differ(self):
        from headless_main import headless_conversation_store_path
        from memory.conversation_store import default_store_path

        desktop = default_store_path()
        headless = headless_conversation_store_path()
        self.assertNotEqual(desktop, headless)
        self.assertIn("headless", str(headless))

    def test_headless_path_in_memory_dir(self):
        from headless_main import headless_conversation_store_path

        path = headless_conversation_store_path()
        self.assertEqual(path.parent.name, "memory")


class TestNoPyQtContamination(unittest.TestCase):
    """Importing headless modules must not pull in PyQt."""

    def test_headless_client_no_pyqt(self):
        pyqt_modules = {k for k in sys.modules if "PyQt" in k}
        import headless_client  # noqa: F401
        new_pyqt = {k for k in sys.modules if "PyQt" in k} - pyqt_modules
        self.assertEqual(new_pyqt, set(), f"headless_client imported PyQt: {new_pyqt}")

    def test_headless_main_module_no_pyqt(self):
        pyqt_before = {k for k in sys.modules if "PyQt" in k}
        from headless_main import headless_conversation_store_path  # noqa: F401
        new_pyqt = {k for k in sys.modules if "PyQt" in k} - pyqt_before
        self.assertEqual(new_pyqt, set(), f"headless_main imported PyQt: {new_pyqt}")


if __name__ == "__main__":
    unittest.main()
