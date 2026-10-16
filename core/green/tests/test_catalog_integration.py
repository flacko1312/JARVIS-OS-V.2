"""Integration tests for capability catalog wired into JARVIS runtime."""
from __future__ import annotations

import asyncio
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import main
from core.green.capability_catalog import (
    _CATALOG_PATH,
    build_inventory,
    open_catalog,
    refresh_catalog,
    write_catalog,
)


class TestToolDeclarationExists(unittest.TestCase):
    def test_open_capabilities_catalog_in_declarations(self):
        names = [d["name"] for d in main.TOOL_DECLARATIONS]
        assert "open_capabilities_catalog" in names

    def test_declaration_schema_valid(self):
        decl = next(
            d for d in main.TOOL_DECLARATIONS if d["name"] == "open_capabilities_catalog"
        )
        assert "description" in decl
        assert "parameters" in decl
        params = decl["parameters"]
        assert params["type"] == "OBJECT"
        assert "action" in params["properties"]
        assert params["properties"]["action"]["type"] == "STRING"
        assert set(params["properties"]["action"]["enum"]) == {"open", "refresh"}

    def test_declaration_has_spanish_triggers(self):
        decl = next(
            d for d in main.TOOL_DECLARATIONS if d["name"] == "open_capabilities_catalog"
        )
        desc = decl["description"]
        assert "habilidades" in desc
        assert "capacidades" in desc
        assert "funciones" in desc

    def test_declaration_says_no_read_aloud(self):
        decl = next(
            d for d in main.TOOL_DECLARATIONS if d["name"] == "open_capabilities_catalog"
        )
        assert "NOT read" in decl["description"] or "not read" in decl["description"].lower()

    def test_in_get_tool_declarations(self):
        all_decls = main.get_tool_declarations(cloud_safe=False)
        names = [d["name"] for d in all_decls]
        assert "open_capabilities_catalog" in names

    def test_not_cloud_safe(self):
        cloud_decls = main.get_tool_declarations(cloud_safe=True)
        names = [d["name"] for d in cloud_decls]
        assert "open_capabilities_catalog" not in names


class TestToolDispatchWorks(unittest.TestCase):
    def test_refresh_action(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            with patch("core.green.capability_catalog._CATALOG_PATH", path):
                result_path = refresh_catalog()
                assert result_path.exists()
                content = result_path.read_text(encoding="utf-8")
                assert "# JARVIS" in content

    def test_open_action_vscode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            path.write_text("# Test", encoding="utf-8")
            with patch("core.green.capability_catalog.shutil.which", return_value="code"), \
                 patch("core.green.capability_catalog.subprocess.Popen") as mock_popen:
                result = open_catalog(path)
                assert "VS Code" in result
                mock_popen.assert_called_once()

    def test_open_action_notepad_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            path.write_text("# Test", encoding="utf-8")
            def which_side_effect(name):
                return "notepad" if name == "notepad" else None
            with patch("core.green.capability_catalog.shutil.which", side_effect=which_side_effect), \
                 patch("core.green.capability_catalog.subprocess.Popen") as mock_popen:
                result = open_catalog(path)
                assert "Notepad" in result


class TestCatalogRefreshIsCalled(unittest.TestCase):
    def test_refresh_produces_valid_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            result_path = write_catalog(path)
            assert result_path == path
            content = path.read_text(encoding="utf-8")
            assert "# JARVIS" in content
            assert "✅ AVAILABLE" in content
            assert "LILITH" in content

    def test_refresh_includes_all_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            write_catalog(path)
            content = path.read_text(encoding="utf-8")
            assert "## Windows" in content
            assert "## LILITH" in content
            assert "## Memory" in content or "## Memoria" in content


class TestArbitraryPathCannotBeSupplied(unittest.TestCase):
    def test_tool_schema_has_no_path_parameter(self):
        decl = next(
            d for d in main.TOOL_DECLARATIONS if d["name"] == "open_capabilities_catalog"
        )
        props = decl["parameters"]["properties"]
        assert "path" not in props
        assert "file" not in props
        assert "file_path" not in props

    def test_catalog_path_is_hardcoded_in_docs(self):
        assert "docs" in str(_CATALOG_PATH)
        assert "JARVIS_CAPABILITIES.md" in _CATALOG_PATH.name


class TestToolIsReadOnly(unittest.TestCase):
    def test_no_side_effects_beyond_file_write(self):
        inv = build_inventory()
        for cat in inv.categories:
            for entry in cat.entries:
                if "catalog" in entry.name.lower() or "catálogo" in entry.name.lower():
                    assert not entry.side_effects

    def test_open_does_not_modify_tool_registry(self):
        before_count = len(main.TOOL_DECLARATIONS)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            write_catalog(path)
        after_count = len(main.TOOL_DECLARATIONS)
        assert before_count == after_count


class TestNoCapabilityExecutedWhileDisplaying(unittest.TestCase):
    def test_catalog_generation_does_not_call_tools(self):
        with patch("core.green.capability_catalog.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc1234")
            inv = build_inventory()
            # Only subprocess call should be git rev-parse for commit hash
            for call in mock_run.call_args_list:
                cmd = call[0][0] if call[0] else call[1].get("args", [])
                assert "git" in str(cmd), f"Unexpected subprocess call: {cmd}"


class TestExistingDeclarationsUnchanged(unittest.TestCase):
    def test_original_47_tools_still_present(self):
        expected = {
            "date_time", "open_app", "web_search", "weather_report",
            "check_messages", "prepare_message_reply", "send_message",
            "email_control", "reminder", "youtube_video", "media_control",
            "screen_process", "computer_settings", "browser_control",
            "file_controller", "desktop_control", "code_helper", "dev_agent",
            "agent_task", "computer_control", "game_updater", "flight_finder",
            "graphics_quality", "jarvis_ui_control", "deep_research",
            "create_presentation", "task_status", "file_processor",
            "save_memory", "local_memory_search",
            "lilith_memory_search", "lilith_memory_store", "lilith_memory_delete",
            "lilith_home_action", "lilith_request_approval", "lilith_resolve_approval",
            "lilith_health", "lilith_runtime_status",
            "lilith_docs_list", "lilith_docs_read", "lilith_docs_search",
            "lilith_source_list", "lilith_source_read", "lilith_source_search",
            "lilith_git_status", "lilith_command_submit", "lilith_routine",
        }
        names = {d["name"] for d in main.TOOL_DECLARATIONS}
        missing = expected - names
        assert missing == set(), f"Original tools missing: {missing}"

    def test_total_count_is_48(self):
        assert len(main.TOOL_DECLARATIONS) == 48


if __name__ == "__main__":
    unittest.main()
