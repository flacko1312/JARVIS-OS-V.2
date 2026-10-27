"""Tests for actions.file_controller — path safety, alias resolution, and dispatch."""

from pathlib import Path
from unittest.mock import patch

import pytest

from actions.file_controller import (
    UnsafePathError,
    _alias_key,
    _is_safe_path,
    _resolve_path,
    file_controller,
    list_files,
    read_file,
    create_file,
)


class TestAliasKey:
    def test_strips_accents(self):
        assert _alias_key("Imágenes") == "imagenes"

    def test_lowercases_and_strips(self):
        assert _alias_key("  Desktop  ") == "desktop"

    def test_handles_empty(self):
        assert _alias_key("") == ""


class TestSafePathResolution:
    def test_safe_path_inside_allowed_root(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", {tmp_path}):
            assert _is_safe_path(tmp_path / "child.txt")

    def test_unsafe_path_outside_roots(self, tmp_path):
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        with patch("actions.file_controller._SAFE_ROOTS", {sandbox}):
            assert not _is_safe_path(tmp_path / "outside.txt")

    def test_resolve_path_rejects_traversal(self):
        with pytest.raises(UnsafePathError):
            _resolve_path("../../etc/passwd")


class TestListFiles:
    def test_list_directory_contents(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", {tmp_path}):
            result = list_files(str(tmp_path))
        assert "a.txt" in result
        assert "b.txt" in result


class TestReadFile:
    def test_read_text_file(self, tmp_path):
        target = tmp_path / "readme.txt"
        target.write_text("content here", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", {tmp_path}):
            result = read_file(str(target))
        assert "content here" in result


class TestCreateFile:
    def test_create_new_file(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", {tmp_path}):
            result = create_file(str(tmp_path), name="hello.txt", content="Hello AURORA")
        target = tmp_path / "hello.txt"
        assert target.exists()
        assert "Hello AURORA" in target.read_text(encoding="utf-8")


class TestDispatch:
    def test_list_action_dispatches(self, tmp_path):
        (tmp_path / "x.txt").write_text("x", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", {tmp_path}):
            result = file_controller({"action": "list", "path": str(tmp_path)})
        assert "x.txt" in result

    def test_unknown_action_returns_error(self):
        result = file_controller({"action": "explode_universe"})
        assert "no reconocid" in result.lower() or "unknown" in result.lower() or result
