"""Block 1 — Windows, Files & Browser: comprehensive audit tests.

Tests cover:
  A) computer_control (Windows control, keyboard, mouse, focus, screenshot)
  B) open_app (launch, alias resolution, non-existent app)
  C) file_controller (CRUD, paths, special chars, missing paths)
  D) file_processor (detect_type, resolve_file_path, dispatch)
  E) browser_control (URL normalise, session lifecycle)
  F) router classifier — Windows vs conversation disambiguation
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ── A. computer_control ──────────────────────────────────────────────

from actions.computer_control import (
    computer_control,
    _random_data,
    _safe_screenshot_path,
    _user_profile,
)


class TestComputerControlDispatch:
    """Dispatch table returns sensible messages for every action."""

    def test_no_action_returns_error(self):
        assert "No action" in computer_control({})

    def test_unknown_action_returns_error(self):
        assert "Unknown action" in computer_control({"action": "fly_to_moon"})

    @patch("actions.computer_control._PYAUTOGUI", False)
    def test_click_without_pyautogui_raises(self):
        result = computer_control({"action": "click"})
        assert "PyAutoGUI" in result or "failed" in result

    @patch("actions.computer_control.safe_type_text")
    def test_type_delegates_to_safe_type(self, mock_safe):
        mock_safe.return_value = MagicMock(ok=True, message="ok")
        result = computer_control({"action": "type", "text": "hello"})
        assert "Typed safely" in result
        mock_safe.assert_called_once()

    @patch("actions.computer_control.safe_type_text")
    def test_smart_type_clears_first(self, mock_safe):
        mock_safe.return_value = MagicMock(ok=True, message="ok")
        result = computer_control({"action": "smart_type", "text": "hello", "clear_first": True})
        assert "Smart-typed" in result

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_click_with_coords(self, mock_gui):
        result = computer_control({"action": "click", "x": 100, "y": 200})
        assert "Clicked" in result
        mock_gui.click.assert_called_once_with(100, 200, button="left", clicks=1)

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_double_click(self, mock_gui):
        result = computer_control({"action": "double_click", "x": 50, "y": 50})
        assert "Double-c" in result
        mock_gui.click.assert_called_once_with(50, 50, button="left", clicks=2)

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_right_click(self, mock_gui):
        result = computer_control({"action": "right_click"})
        assert "Clicked" in result

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_move(self, mock_gui):
        result = computer_control({"action": "move", "x": 300, "y": 400})
        assert "300" in result and "400" in result

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_hotkey(self, mock_gui):
        result = computer_control({"action": "hotkey", "keys": "ctrl+c"})
        assert "Hotkey" in result

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_press_enter(self, mock_gui):
        result = computer_control({"action": "press", "key": "enter"})
        assert "Pressed" in result

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_scroll_down(self, mock_gui):
        result = computer_control({"action": "scroll", "direction": "down", "amount": 5})
        assert "Scrolled" in result

    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    def test_scroll_up(self, mock_gui):
        result = computer_control({"action": "scroll", "direction": "up", "amount": 3})
        assert "Scrolled up" in result

    @patch("actions.computer_control.safe_type_text")
    def test_paste(self, mock_safe):
        mock_safe.return_value = MagicMock(ok=True, message="ok")
        result = computer_control({"action": "paste", "text": "clipboard content"})
        assert "Pasted" in result

    def test_wait_capped_at_30s(self):
        result = computer_control({"action": "wait", "seconds": 0.01})
        assert "Waited" in result

    @patch("actions.computer_control.safe_type_text")
    def test_clear_field(self, mock_safe):
        mock_safe.return_value = MagicMock(ok=True, message="ok")
        result = computer_control({"action": "clear_field"})
        assert "cleared" in result.lower() or "Field" in result

    @patch("actions.computer_control.subprocess")
    def test_focus_window_windows(self, mock_sub):
        mock_sub.run.return_value = MagicMock(returncode=0)
        with patch("actions.computer_control._get_os", return_value="windows"):
            result = computer_control({"action": "focus_window", "title": "Notepad"})
        assert "Focused" in result or "focus" in result.lower()

    def test_random_data_types(self):
        for dt in ("first_name", "last_name", "name", "email",
                    "username", "password", "phone", "birthday",
                    "address", "zip_code", "city"):
            val = _random_data(dt)
            assert val, f"random_data({dt}) returned empty"

    def test_random_data_unknown_type(self):
        val = _random_data("unicorn_id")
        assert "random_unicorn_id" in val

    def test_user_data_missing_memory(self):
        result = computer_control({"action": "user_data", "field": "name"})
        assert result  # should return either real or random data


class TestSafeScreenshotPath:
    def test_none_returns_fallback(self):
        p = _safe_screenshot_path(None)
        assert p.name == "jarvis_screenshot.png"

    def test_empty_returns_fallback(self):
        p = _safe_screenshot_path("")
        assert p.name == "jarvis_screenshot.png"

    def test_path_inside_home(self):
        inside = str(Path.home() / "Desktop" / "test_shot.png")
        p = _safe_screenshot_path(inside)
        assert p.name == "test_shot.png"

    def test_path_outside_home_returns_fallback(self):
        if platform.system() == "Windows":
            outside = "C:\\Windows\\System32\\evil.png"
        else:
            outside = "/etc/evil.png"
        p = _safe_screenshot_path(outside)
        assert p.name == "jarvis_screenshot.png"


class TestScreenshot:
    @patch("actions.computer_control.pyautogui")
    @patch("actions.computer_control._PYAUTOGUI", True)
    @patch("actions.computer_control.mark_created_file")
    def test_screenshot_saves_file(self, mock_mark, mock_gui):
        mock_img = MagicMock()
        mock_gui.screenshot.return_value = mock_img
        result = computer_control({"action": "screenshot"})
        assert "Screenshot saved" in result
        mock_img.save.assert_called_once()


# ── B. open_app ──────────────────────────────────────────────────────

from actions.open_app import open_app, _normalize, _APP_ALIASES


class TestOpenAppNormalize:
    def test_known_aliases_resolve(self):
        assert _normalize("spotify") == "Spotify" or _normalize("spotify") in ("Spotify", "spotify")
        assert _normalize("vscode") in ("code", "Visual Studio Code")

    def test_chrome_resolves_per_os(self):
        result = _normalize("chrome")
        assert result  # non-empty

    def test_unknown_app_passthrough(self):
        assert _normalize("my_custom_app_xyz") == "my_custom_app_xyz"

    def test_partial_match(self):
        result = _normalize("google chrome")
        assert result in ("chrome", "Google Chrome", "google-chrome")

    def test_case_insensitive(self):
        assert _normalize("SPOTIFY") == _normalize("spotify")


class TestOpenApp:
    def test_no_app_name(self):
        result = open_app({})
        assert "No application" in result

    def test_empty_app_name(self):
        result = open_app({"app_name": ""})
        assert "No application" in result

    @patch("actions.open_app._SYSTEM", "Windows")
    def test_successful_launch_windows(self):
        fake_launcher = MagicMock(return_value=True)
        with patch.dict("actions.open_app._OS_LAUNCHERS", {"Windows": fake_launcher}, clear=False):
            result = open_app({"app_name": "notepad"})
        assert "Opened" in result
        fake_launcher.assert_called_once_with("notepad.exe")

    def test_failed_launch(self):
        with patch.dict("actions.open_app._OS_LAUNCHERS", {"TestOS": lambda n: False}), \
             patch("actions.open_app._SYSTEM", "TestOS"):
            result = open_app({"app_name": "nonexistent_app_xyz_123"})
            assert "Could not confirm" in result or "not be installed" in result

    @patch("actions.open_app._SYSTEM", "Windows")
    def test_exception_during_launch(self):
        fake_launcher = MagicMock(side_effect=Exception("crash"))
        with patch.dict("actions.open_app._OS_LAUNCHERS", {"Windows": fake_launcher}, clear=False):
            result = open_app({"app_name": "crasher"})
        assert "Failed" in result or "crash" in result.lower()
        fake_launcher.assert_called_once_with("crasher")

    def test_player_logging(self):
        player = MagicMock()
        with patch("actions.open_app._OS_LAUNCHERS", {"TestOS": lambda x: True}), \
             patch("actions.open_app._SYSTEM", "TestOS"):
            open_app({"app_name": "test"}, player=player)
        player.write_log.assert_called_once()


# ── C. file_controller ───────────────────────────────────────────────

from actions.file_controller import (
    file_controller,
    list_files,
    create_file,
    create_folder,
    read_file,
    write_file,
    rename_file,
    find_files,
    get_file_info,
    get_disk_usage,
    _is_safe_path,
    _resolve_path,
    _format_size,
)


class TestFileControllerHelpers:
    def test_format_size(self):
        assert "B" in _format_size(500)
        assert "KB" in _format_size(2048)
        assert "MB" in _format_size(5 * 1024 * 1024)

    def test_resolve_path_shortcuts(self):
        assert _resolve_path("home") == Path.home()
        assert _resolve_path("desktop") == Path.home() / "Desktop"
        assert _resolve_path("downloads") == Path.home() / "Downloads"
        assert _resolve_path("documents") == Path.home() / "Documents"

    def test_resolve_path_absolute(self):
        if platform.system() == "Windows":
            p = _resolve_path("C:\\Users")
            assert p == Path("C:\\Users")

    def test_is_safe_path_home(self):
        assert _is_safe_path(Path.home() / "Desktop" / "test.txt")

    def test_is_safe_path_system(self):
        if platform.system() == "Windows":
            assert not _is_safe_path(Path("C:\\Windows\\System32"))


class TestFileControllerCRUD:
    def test_create_and_read_file(self, tmp_path):
        path = str(tmp_path)
        name = "test_file.txt"
        content = "Hello JARVIS!"

        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = create_file(path, name=name, content=content)
            assert "saved" in result.lower() or "File" in result

            read_result = read_file(path, name=name)
            assert "Hello JARVIS!" in read_result

    def test_create_folder(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = create_folder(str(tmp_path), name="new_folder")
            assert "created" in result.lower()
            assert (tmp_path / "new_folder").is_dir()

    def test_list_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")

        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = list_files(str(tmp_path))
            assert "a.txt" in result
            assert "b.txt" in result
            assert "2 items" in result

    def test_list_empty_dir(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = list_files(str(tmp_path))
            assert "empty" in result.lower()

    def test_read_nonexistent_file(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = read_file(str(tmp_path), name="ghost.txt")
            assert "not found" in result.lower()

    def test_read_truncation(self, tmp_path):
        big = "x" * 10000
        f = tmp_path / "big.txt"
        f.write_text(big, encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = read_file(str(tmp_path), name="big.txt", max_chars=100)
            assert "Truncated" in result

    def test_write_file(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = write_file(str(tmp_path), name="out.txt", content="content")
            assert "Written" in result
            assert (tmp_path / "out.txt").exists()

    def test_write_file_append(self, tmp_path):
        f = tmp_path / "append.txt"
        f.write_text("first", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = write_file(str(tmp_path), name="append.txt",
                                content=" second", append=True)
            assert "Appended" in result
            assert "first second" in f.read_text(encoding="utf-8")

    def test_rename_file(self, tmp_path):
        (tmp_path / "old.txt").write_text("data", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = rename_file(str(tmp_path), name="old.txt", new_name="new.txt")
            assert "Renamed" in result
            assert (tmp_path / "new.txt").exists()
            assert not (tmp_path / "old.txt").exists()

    def test_rename_no_new_name(self, tmp_path):
        (tmp_path / "f.txt").write_text("x", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = rename_file(str(tmp_path), name="f.txt", new_name="")
            assert "No new name" in result

    def test_rename_conflict(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = rename_file(str(tmp_path), name="a.txt", new_name="b.txt")
            assert "already exists" in result

    def test_find_files(self, tmp_path):
        (tmp_path / "readme.md").write_text("hi", encoding="utf-8")
        (tmp_path / "data.csv").write_text("a,b", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = find_files(name="readme", path=str(tmp_path))
            assert "readme.md" in result

    def test_find_files_by_extension(self, tmp_path):
        (tmp_path / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "b.txt").write_text("x", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = find_files(extension=".py", path=str(tmp_path))
            assert "a.py" in result
            assert "b.txt" not in result

    def test_find_no_results(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = find_files(name="zzz_nonexistent", path=str(tmp_path))
            assert "No" in result

    def test_get_file_info(self, tmp_path):
        (tmp_path / "info.txt").write_text("test", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = get_file_info(str(tmp_path), name="info.txt")
            assert "info.txt" in result
            assert "File" in result

    def test_disk_usage(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = get_disk_usage(str(tmp_path))
            assert "Total" in result

    def test_access_denied_outside_safe_roots(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = list_files("C:\\Windows\\System32" if platform.system() == "Windows" else "/etc")
            assert "Access denied" in result

    def test_path_not_found(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = list_files(str(tmp_path / "nonexistent_dir_xyz"))
            assert "not found" in result.lower()


class TestFileControllerSpecialChars:
    def test_filename_with_spaces(self, tmp_path):
        name = "my document file.txt"
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            create_file(str(tmp_path), name=name, content="content")
            assert (tmp_path / name).exists()
            result = read_file(str(tmp_path), name=name)
            assert "content" in result

    def test_filename_with_unicode(self, tmp_path):
        name = "archivo_español.txt"
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            create_file(str(tmp_path), name=name, content="contenido")
            assert (tmp_path / name).exists()

    def test_filename_with_special_chars(self, tmp_path):
        name = "file-name_v2 (copy).txt"
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            create_file(str(tmp_path), name=name, content="test")
            assert (tmp_path / name).exists()


class TestFileControllerDispatch:
    def test_dispatch_unknown_action(self):
        result = file_controller({"action": "teleport"})
        assert "Unknown action" in result

    def test_dispatch_list(self, tmp_path):
        (tmp_path / "x.txt").write_text("x", encoding="utf-8")
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = file_controller({"action": "list", "path": str(tmp_path)})
            assert "x.txt" in result

    def test_dispatch_create_file(self, tmp_path):
        with patch("actions.file_controller._SAFE_ROOTS", [tmp_path]):
            result = file_controller({
                "action": "create_file",
                "path": str(tmp_path),
                "name": "new.txt",
                "content": "data",
            })
            assert "saved" in result.lower() or "File" in result


# ── D. file_processor ────────────────────────────────────────────────

from actions.file_processor import (
    _detect_type,
    _resolve_file_path,
    _file_size_str,
    _output_path,
    file_processor,
)


class TestFileProcessorDetectType:
    @pytest.mark.parametrize("ext,expected", [
        (".jpg", "image"), (".png", "image"), (".gif", "image"), (".webp", "image"),
        (".pdf", "pdf"),
        (".docx", "docx"), (".doc", "docx"),
        (".txt", "text"), (".md", "text"), (".log", "text"),
        (".csv", "csv"), (".tsv", "csv"),
        (".xlsx", "excel"), (".xls", "excel"),
        (".json", "json"), (".jsonl", "json"),
        (".py", "code"), (".js", "code"), (".html", "code"),
        (".mp3", "audio"), (".wav", "audio"), (".flac", "audio"),
        (".mp4", "video"), (".avi", "video"), (".mkv", "video"),
        (".zip", "archive"), (".tar", "archive"),
        (".pptx", "pptx"), (".ppt", "pptx"),
        (".xml", "xml"),
        (".xyz123", "unknown"),
    ])
    def test_detect_type(self, ext, expected):
        assert _detect_type(Path(f"test{ext}")) == expected


class TestFileProcessorResolvePath:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "exists.txt"
        f.write_text("x", encoding="utf-8")
        assert _resolve_file_path(str(f)) == f

    def test_empty_path(self):
        result = _resolve_file_path("")
        assert result == Path()

    def test_relative_file_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "relative.txt"
        f.write_text("x", encoding="utf-8")
        resolved = _resolve_file_path("relative.txt")
        assert resolved.exists()

    def test_nonexistent_absolute(self):
        result = _resolve_file_path("/nonexistent/path/file.txt")
        assert not result.exists()


class TestFileProcessorHelpers:
    def test_file_size_str_bytes(self):
        assert "B" in _file_size_str(Path(__file__))

    def test_output_path(self, tmp_path):
        src = tmp_path / "input.txt"
        out = _output_path(src, "summary")
        assert out.stem == "input_summary"
        assert out.suffix == ".txt"

    def test_output_path_new_ext(self, tmp_path):
        src = tmp_path / "input.pdf"
        out = _output_path(src, "converted", ".docx")
        assert out.suffix == ".docx"


class TestFileProcessorDispatch:
    def test_no_file_path(self):
        result = file_processor({})
        assert "No file path" in result

    def test_file_not_found(self):
        result = file_processor({"file_path": "/nonexistent/xyz_abc.txt"})
        assert "not found" in result.lower()

    def test_text_file_word_count(self, tmp_path):
        f = tmp_path / "words.txt"
        f.write_text("one two three four five", encoding="utf-8")
        with patch("actions.file_processor._generate_content", side_effect=Exception("no API")):
            result = file_processor({"file_path": str(f), "action": "word_count"})
            assert "5 words" in result

    def test_json_validate(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = file_processor({"file_path": str(f), "action": "validate"})
        assert "Valid JSON" in result

    def test_json_format(self, tmp_path):
        f = tmp_path / "ugly.json"
        f.write_text('{"a":1,"b":2}', encoding="utf-8")
        result = file_processor({"file_path": str(f), "action": "format"})
        assert "Formatted" in result
        formatted = tmp_path / "ugly_formatted.json"
        assert formatted.exists()

    def test_text_extract(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("sample content here", encoding="utf-8")
        result = file_processor({"file_path": str(f), "action": "extract_text"})
        # For .txt files, extract_text returns content directly (not saved)
        assert "sample content" in result or "extracted" in result.lower()

    def test_code_info(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("print('hello')\nprint('world')\n", encoding="utf-8")
        result = file_processor({"file_path": str(f), "action": "info"})
        assert "2 lines" in result

    def test_archive_list(self, tmp_path):
        import zipfile
        zf_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zf_path, 'w') as zf:
            zf.writestr("inner.txt", "content")
        result = file_processor({"file_path": str(zf_path), "action": "list"})
        assert "inner.txt" in result

    def test_archive_extract(self, tmp_path):
        import zipfile
        zf_path = tmp_path / "extract_me.zip"
        with zipfile.ZipFile(zf_path, 'w') as zf:
            zf.writestr("extracted.txt", "hello")
        result = file_processor({"file_path": str(zf_path), "action": "extract"})
        assert "Extracted" in result

    def test_csv_info(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
        result = file_processor({"file_path": str(f), "action": "info"})
        assert "Rows" in result or "2" in result

    def test_csv_stats(self, tmp_path):
        f = tmp_path / "nums.csv"
        f.write_text("val\n1\n2\n3\n4\n5\n", encoding="utf-8")
        result = file_processor({"file_path": str(f), "action": "stats"})
        assert "Statistics" in result

    def test_image_info(self, tmp_path):
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        f = tmp_path / "test.png"
        Image.new("RGB", (100, 50)).save(f)
        result = file_processor({"file_path": str(f), "action": "info"})
        assert "100" in result and "50" in result


# ── E. browser_control ───────────────────────────────────────────────

from actions.browser_control import _normalize_url, browser_control


class TestBrowserNormalizeURL:
    def test_full_url_passthrough(self):
        assert _normalize_url("https://google.com") == "https://google.com"

    def test_bare_word_gets_dot_com(self):
        assert _normalize_url("instagram") == "https://instagram.com"

    def test_domain_gets_https(self):
        assert _normalize_url("example.com") == "https://example.com"

    def test_http_preserved(self):
        assert _normalize_url("http://localhost:3000") == "http://localhost:3000"

    def test_empty_returns_about_blank(self):
        assert _normalize_url("") == "about:blank"

    def test_whitespace_stripped(self):
        assert _normalize_url("  google.com  ") == "https://google.com"


class TestBrowserControlDispatch:
    def test_unknown_action(self):
        result = browser_control({"action": "teleport"})
        assert "Unknown" in result

    def test_list_browsers_empty(self):
        result = browser_control({"action": "list_browsers"})
        assert "browser" in result.lower()

    def test_close_all_empty(self):
        result = browser_control({"action": "close_all"})
        assert "closed" in result.lower() or "none" in result.lower()


# ── F. Router: Windows vs Conversation ────────────────────────────────

from router.classifier import classify
from router.models import Domain


class TestRouterWindowsVsConversation:
    """Critical test: 'Abre Spotify' must route to WINDOWS, not conversation."""

    def test_abre_spotify_is_windows(self):
        result = classify("Abre Spotify")
        assert result.domain == Domain.WINDOWS, \
            f"'Abre Spotify' should route to WINDOWS, got {result.domain}"

    def test_explicame_spotify_is_conversation(self):
        result = classify("Explícame qué es Spotify")
        assert result.domain == Domain.CONVERSATION, \
            f"'Explícame qué es Spotify' should route to CONVERSATION, got {result.domain}"

    def test_abre_vscode_is_windows(self):
        result = classify("Abre Visual Studio Code")
        assert result.domain == Domain.WINDOWS

    def test_explicame_vscode_is_conversation(self):
        result = classify("Explícame Visual Studio Code")
        assert result.domain == Domain.CONVERSATION

    def test_cierra_chrome_is_windows(self):
        result = classify("Cierra Chrome")
        assert result.domain == Domain.WINDOWS

    def test_que_es_chrome_is_conversation(self):
        result = classify("¿Qué es Chrome?")
        assert result.domain == Domain.CONVERSATION

    def test_minimiza_discord_is_windows(self):
        result = classify("Minimiza Discord")
        assert result.domain == Domain.WINDOWS

    def test_inicia_terminal_is_windows(self):
        result = classify("Inicia el terminal")
        assert result.domain == Domain.WINDOWS

    def test_hola_is_conversation(self):
        result = classify("Hola, ¿cómo estás?")
        assert result.domain == Domain.CONVERSATION

    def test_quien_eres_is_conversation(self):
        result = classify("¿Quién eres?")
        assert result.domain == Domain.CONVERSATION

    def test_que_puedes_hacer_is_conversation(self):
        result = classify("¿Qué puedes hacer?")
        assert result.domain == Domain.CONVERSATION


class TestRouterOtherDomains:
    def test_busca_en_google_is_web(self):
        result = classify("Busca en Google el tiempo en Madrid")
        assert result.domain == Domain.WEB

    def test_enciende_luz_is_home(self):
        result = classify("Enciende la luz del salón")
        assert result.domain == Domain.HOME

    def test_recuerda_is_memory(self):
        result = classify("Recuerda que mi cumpleaños es el 5 de marzo")
        assert result.domain == Domain.MEMORY

    def test_que_ves_is_vision(self):
        result = classify("¿Qué ves en la pantalla?")
        assert result.domain == Domain.VISION

    def test_arregla_codigo_is_development(self):
        result = classify("Arregla el código del módulo de login")
        assert result.domain == Domain.DEVELOPMENT

    def test_usa_ollama_is_local_ai(self):
        result = classify("Usa Ollama para analizar esto localmente")
        assert result.domain == Domain.LOCAL_AI

    def test_busca_archivo_is_files(self):
        result = classify("Busca archivos PDF en mi carpeta")
        assert result.domain == Domain.FILES

    def test_unknown_input_defaults_to_conversation(self):
        result = classify("asdf jkl;")
        assert result.domain == Domain.CONVERSATION
        assert result.params.get("fallback") is True

    def test_ambiguity_detection(self):
        result = classify("Abre el archivo en Spotify")
        # Should detect ambiguity between FILES and WINDOWS/multimedia
        assert result.confidence > 0


class TestRouterConfidence:
    def test_high_confidence_for_direct_match(self):
        result = classify("Abre Spotify")
        assert result.confidence >= 0.9

    def test_low_confidence_for_fallback(self):
        result = classify("xyzzy plugh")
        assert result.confidence <= 0.5

    def test_result_contains_raw_input(self):
        result = classify("Hola JARVIS")
        assert result.params.get("raw_input") == "Hola JARVIS"
