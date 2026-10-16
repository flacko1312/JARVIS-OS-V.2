"""Tests for Capability Catalog — Visual Capability Catalog of GREEN Foundation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.green.capability_catalog import (
    CapabilityEntry,
    CapabilityCategory,
    CapabilityInventory,
    CapabilityMarkdownRenderer,
    ValidationStatus,
    build_inventory,
    render_markdown,
    write_catalog,
    open_catalog,
    _CATALOG_PATH,
)


class TestValidationStatus(unittest.TestCase):
    def test_all_statuses_distinct(self):
        statuses = [
            ValidationStatus.AVAILABLE,
            ValidationStatus.PENDING_PHYSICAL,
            ValidationStatus.DISABLED,
            ValidationStatus.UNAVAILABLE,
            ValidationStatus.REQUIRES_APPROVAL,
            ValidationStatus.DELEGATED,
        ]
        assert len(set(statuses)) == 6

    def test_statuses_contain_emoji(self):
        assert "✅" in ValidationStatus.AVAILABLE
        assert "🟡" in ValidationStatus.PENDING_PHYSICAL
        assert "⛔" in ValidationStatus.DISABLED
        assert "❌" in ValidationStatus.UNAVAILABLE
        assert "⚠️" in ValidationStatus.REQUIRES_APPROVAL
        assert "🔒" in ValidationStatus.DELEGATED


class TestCapabilityEntry(unittest.TestCase):
    def test_defaults(self):
        entry = CapabilityEntry(name="Test")
        assert entry.name == "Test"
        assert entry.status == ValidationStatus.AVAILABLE
        assert entry.authority == "JARVIS"
        assert entry.tools == []
        assert entry.search_terms == []
        assert not entry.side_effects
        assert not entry.requires_approval

    def test_full_entry(self):
        entry = CapabilityEntry(
            name="File control",
            description="Manage files",
            status=ValidationStatus.AVAILABLE,
            category="Files",
            tools=["file_controller"],
            authority="JARVIS",
            side_effects=True,
            requires_approval=False,
            search_terms=["archivo", "file"],
            can=["Open files", "List files"],
            examples=["Abre el archivo"],
        )
        assert entry.tools == ["file_controller"]
        assert "archivo" in entry.search_terms
        assert len(entry.can) == 2


class TestCapabilityCategory(unittest.TestCase):
    def test_empty_category(self):
        cat = CapabilityCategory(name="Test")
        assert cat.entries == []

    def test_category_with_entries(self):
        cat = CapabilityCategory(
            name="Windows",
            entries=[
                CapabilityEntry(name="A"),
                CapabilityEntry(name="B"),
            ],
        )
        assert len(cat.entries) == 2


class TestCapabilityInventory(unittest.TestCase):
    def test_empty_inventory(self):
        inv = CapabilityInventory()
        inv.compute_summary()
        assert inv.total_tools == 0
        assert inv.available_count == 0

    def test_add_category(self):
        inv = CapabilityInventory()
        cat = CapabilityCategory(name="Test")
        inv.add_category(cat)
        assert len(inv.categories) == 1

    def test_compute_summary(self):
        inv = CapabilityInventory()
        cat = CapabilityCategory(name="Mixed", entries=[
            CapabilityEntry(name="A", tools=["t1"], status=ValidationStatus.AVAILABLE),
            CapabilityEntry(name="B", tools=["t2"], status=ValidationStatus.DISABLED),
            CapabilityEntry(name="C", tools=["t3"], status=ValidationStatus.PENDING_PHYSICAL),
            CapabilityEntry(name="D", tools=["t4"], requires_approval=True, authority="LILITH"),
        ])
        inv.add_category(cat)
        inv.compute_summary()
        assert inv.total_tools == 4
        assert inv.available_count == 2  # A + D (D defaults to AVAILABLE)
        assert inv.disabled_count == 1
        assert inv.pending_validation_count == 1
        assert inv.high_risk_count == 1
        assert inv.lilith_delegated_count == 1

    def test_tool_deduplication(self):
        inv = CapabilityInventory()
        cat = CapabilityCategory(name="Overlap", entries=[
            CapabilityEntry(name="A", tools=["shared_tool", "t1"]),
            CapabilityEntry(name="B", tools=["shared_tool", "t2"]),
        ])
        inv.add_category(cat)
        inv.compute_summary()
        assert inv.total_tools == 3  # shared_tool, t1, t2


class TestCapabilityMarkdownRenderer(unittest.TestCase):
    def setUp(self):
        self.renderer = CapabilityMarkdownRenderer()

    def test_render_empty_inventory(self):
        inv = CapabilityInventory(generated_at="2026-10-16 12:00:00")
        md = self.renderer.render(inv)
        assert "# JARVIS" in md
        assert "Generated: 2026-10-16" in md
        assert "auto-generated" in md

    def test_render_with_entries(self):
        inv = CapabilityInventory(generated_at="2026-10-16")
        cat = CapabilityCategory(name="Windows", entries=[
            CapabilityEntry(
                name="Open apps",
                status=ValidationStatus.AVAILABLE,
                tools=["open_app"],
                can=["Open applications"],
                examples=["Abre Chrome."],
                search_terms=["abrir", "open"],
            ),
        ])
        inv.add_category(cat)
        inv.compute_summary()
        md = self.renderer.render(inv)
        assert "## Windows" in md
        assert "### Open apps" in md
        assert "✅ AVAILABLE" in md
        assert "`open_app`" in md
        assert "Abre Chrome." in md
        assert "abrir" in md

    def test_render_includes_commit(self):
        inv = CapabilityInventory(generated_at="2026-10-16", commit="abc1234")
        md = self.renderer.render(inv)
        assert "`abc1234`" in md

    def test_render_side_effects_and_approval(self):
        inv = CapabilityInventory(generated_at="now")
        cat = CapabilityCategory(name="Risky", entries=[
            CapabilityEntry(
                name="Danger",
                side_effects=True,
                requires_approval=True,
                physical_validation="🟡 Pending",
                dependencies=["dep1", "dep2"],
            ),
        ])
        inv.add_category(cat)
        md = self.renderer.render(inv)
        assert "Side effects" in md
        assert "Approval required" in md
        assert "Physical validation" in md
        assert "dep1, dep2" in md

    def test_render_lilith_authority(self):
        inv = CapabilityInventory(generated_at="now")
        cat = CapabilityCategory(name="LILITH", entries=[
            CapabilityEntry(name="Home", authority="LILITH"),
        ])
        inv.add_category(cat)
        md = self.renderer.render(inv)
        assert "**Authority**: LILITH" in md

    def test_render_agent_field(self):
        inv = CapabilityInventory(generated_at="now")
        cat = CapabilityCategory(name="Agents", entries=[
            CapabilityEntry(name="Task", agent="Planner"),
        ])
        inv.add_category(cat)
        md = self.renderer.render(inv)
        assert "**Agent**: Planner" in md


class TestBuildInventory(unittest.TestCase):
    def test_builds_successfully(self):
        inv = build_inventory()
        assert isinstance(inv, CapabilityInventory)
        assert len(inv.categories) > 0
        assert inv.total_tools > 0
        assert inv.generated_at != ""

    def test_all_47_tools_covered(self):
        expected_tools = {
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
        inv = build_inventory()
        found_tools: set[str] = set()
        for cat in inv.categories:
            for entry in cat.entries:
                found_tools.update(entry.tools)
        missing = expected_tools - found_tools
        assert missing == set(), f"Tools not in catalog: {missing}"

    def test_categories_are_reasonable(self):
        inv = build_inventory()
        cat_names = [c.name for c in inv.categories]
        assert any("Windows" in n for n in cat_names)
        assert any("LILITH" in n for n in cat_names)
        assert any("Memory" in n or "Memoria" in n for n in cat_names)

    def test_summary_counts_are_positive(self):
        inv = build_inventory()
        assert inv.available_count > 0
        assert inv.total_tools >= 47

    def test_lilith_entries_have_lilith_authority(self):
        inv = build_inventory()
        for cat in inv.categories:
            if "LILITH" in cat.name:
                for entry in cat.entries:
                    assert entry.authority == "LILITH", (
                        f"{entry.name} in LILITH category should have LILITH authority"
                    )

    def test_search_terms_are_spanish_and_english(self):
        inv = build_inventory()
        all_terms: list[str] = []
        for cat in inv.categories:
            for entry in cat.entries:
                all_terms.extend(entry.search_terms)
        has_spanish = any(t in all_terms for t in ["abrir", "buscar", "archivo", "volumen"])
        has_english = any(t in all_terms for t in ["open", "search", "file", "volume"])
        assert has_spanish, "Should have Spanish search terms"
        assert has_english, "Should have English search terms"


class TestRenderMarkdown(unittest.TestCase):
    def test_render_produces_string(self):
        md = render_markdown()
        assert isinstance(md, str)
        assert "# JARVIS" in md
        assert len(md) > 1000

    def test_render_with_custom_inventory(self):
        inv = CapabilityInventory(generated_at="custom")
        md = render_markdown(inv)
        assert "Generated: custom" in md


class TestWriteCatalog(unittest.TestCase):
    def test_write_to_temp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_catalog.md"
            result = write_catalog(path)
            assert result == path
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert "# JARVIS" in content
            assert "auto-generated" in content

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sub" / "dir" / "catalog.md"
            result = write_catalog(path)
            assert result == path
            assert path.exists()


class TestOpenCatalog(unittest.TestCase):
    @patch("core.green.capability_catalog.shutil.which")
    @patch("core.green.capability_catalog.subprocess.Popen")
    def test_opens_vscode_when_available(self, mock_popen, mock_which):
        mock_which.return_value = "code"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            path.write_text("# Test", encoding="utf-8")
            result = open_catalog(path)
            assert "VS Code" in result
            mock_popen.assert_called_once()

    @patch("core.green.capability_catalog.shutil.which")
    @patch("core.green.capability_catalog.subprocess.Popen")
    def test_falls_back_to_notepad(self, mock_popen, mock_which):
        def which_side_effect(name):
            if name == "code":
                return None
            if name == "notepad":
                return "notepad"
            return None
        mock_which.side_effect = which_side_effect
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            path.write_text("# Test", encoding="utf-8")
            result = open_catalog(path)
            assert "Notepad" in result

    @patch("core.green.capability_catalog.shutil.which")
    @patch("core.green.capability_catalog.subprocess.Popen")
    def test_falls_back_on_vscode_oserror(self, mock_popen, mock_which):
        def which_side_effect(name):
            if name == "code":
                return "code"
            if name == "notepad":
                return "notepad"
            return None
        mock_which.side_effect = which_side_effect
        mock_popen.side_effect = [OSError("fail"), MagicMock()]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.md"
            path.write_text("# Test", encoding="utf-8")
            result = open_catalog(path)
            assert "Notepad" in result

    def test_generates_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.md"
            with patch("core.green.capability_catalog.shutil.which", return_value=None), \
                 patch("core.green.capability_catalog.os.startfile", side_effect=AttributeError):
                result = open_catalog(path)
            assert path.exists()

    def test_no_arbitrary_paths_outside_docs(self):
        assert "docs" in str(_CATALOG_PATH)
        assert "JARVIS_CAPABILITIES.md" in str(_CATALOG_PATH)


class TestSecurityConstraints(unittest.TestCase):
    def test_no_secrets_in_rendered_output(self):
        md = render_markdown()
        md_lower = md.lower()
        for forbidden in ["password", "api_key", "token", "secret", "credential", "private_key"]:
            for line in md.split("\n"):
                if forbidden in line.lower():
                    assert "search" in line.lower() or "redact" in line.lower() or \
                           forbidden not in line.lower().replace("search:", ""), \
                        f"Suspicious content in catalog: {line.strip()}"

    def test_catalog_path_is_in_docs(self):
        assert _CATALOG_PATH.parent.name == "docs"


if __name__ == "__main__":
    unittest.main()
