"""Tests for the voice-friendly headless capability catalog."""
import sys
import unittest

sys.path.insert(0, "/home/flako1312/jarvis-headless")

from core.headless_tools import (
    _VOICE_CAPABILITIES,
    _headless_capability_entries,
    build_headless_catalog,
    build_headless_catalog_technical,
    build_headless_catalog_voice_summary,
)

VISUAL_LANGUAGE = [
    "he abierto",
    "ahí encontrarás",
    "pulsa",
    "haz clic",
    "pantalla",
    "ventana",
    "interfaz",
    "botón",
    "menú",
    "pestaña",
]

EXPECTED_TOOLS = {
    "date_time", "system_status", "process_list", "process_info",
    "systemd_status", "systemd_action", "systemd_list_failed", "journal_read",
    "lilith_memory_search", "lilith_memory_store", "lilith_memory_delete",
    "lilith_home_action", "lilith_home_status", "lilith_health",
    "lilith_routine", "open_capabilities_catalog",
}


class TestVoiceCatalog(unittest.TestCase):

    def test_no_visual_language(self):
        catalog = build_headless_catalog()
        lower = catalog.lower()
        for phrase in VISUAL_LANGUAGE:
            self.assertNotIn(phrase, lower, f"Visual language '{phrase}' in voice catalog")

    def test_voice_friendly_has_groups(self):
        catalog = build_headless_catalog()
        for cap in _VOICE_CAPABILITIES:
            self.assertIn(cap["group"], catalog, f"Group '{cap['group']}' missing from catalog")

    def test_voice_friendly_has_examples(self):
        catalog = build_headless_catalog()
        self.assertIn("Ejemplo:", catalog, "No examples found in catalog")
        example_count = catalog.count("Ejemplo:")
        self.assertGreaterEqual(example_count, 10, f"Only {example_count} examples, expected >= 10")

    def test_no_technical_tool_names_in_voice(self):
        catalog = build_headless_catalog()
        for tool in ["systemd_status", "process_info", "journal_read", "lilith_memory_search"]:
            self.assertNotIn(tool, catalog, f"Technical name '{tool}' in voice catalog")

    def test_10_capability_groups(self):
        self.assertEqual(len(_VOICE_CAPABILITIES), 10)

    def test_all_16_tools_covered(self):
        tools_in_caps = set()
        for cap in _VOICE_CAPABILITIES:
            tools_in_caps.update(cap["tools"])
        self.assertEqual(tools_in_caps, EXPECTED_TOOLS)

    def test_entries_count_16(self):
        entries = _headless_capability_entries()
        self.assertEqual(len(entries), 16)

    def test_entries_have_required_keys(self):
        for entry in _headless_capability_entries():
            for key in ("name", "category", "description", "read_only", "confirmation_required", "platform"):
                self.assertIn(key, entry, f"Key '{key}' missing from entry {entry.get('name')}")

    def test_technical_catalog_has_markdown(self):
        tech = build_headless_catalog_technical()
        self.assertIn("# JARVIS Headless", tech)
        self.assertIn("##", tech)
        self.assertIn("READ_ONLY", tech)

    def test_voice_summary_has_all_groups(self):
        summary = build_headless_catalog_voice_summary()
        self.assertIn("fecha y hora", summary)
        self.assertIn("rutinas", summary)
        self.assertIn(" y ", summary)

    def test_each_group_has_description_and_examples(self):
        for cap in _VOICE_CAPABILITIES:
            self.assertTrue(cap["description"], f"Group '{cap['group']}' has no description")
            self.assertGreaterEqual(len(cap["examples"]), 1,
                                    f"Group '{cap['group']}' needs at least 1 example")


if __name__ == "__main__":
    unittest.main()
