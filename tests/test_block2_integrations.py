"""Block 2 — Gmail, Multimedia, Reminders, Presentations.

Tests use mocks for all external services (Gmail API, Spotify, OS schedulers,
Gemini, python-pptx). Tests requiring real credentials, apps, or hardware
are marked PHYSICAL TEST REQUIRED via skip decorators.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# A — GMAIL (email_control.py)
# ---------------------------------------------------------------------------

class TestGmailCredentialDiscovery(unittest.TestCase):
    """_discover_gmail_client_path, _valid_gmail_client_file."""

    def test_valid_client_file_accepted(self):
        from actions.email_control import _valid_gmail_client_file

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({
                "installed": {
                    "client_id": "test.apps.googleusercontent.com",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }, f)
            f.flush()
            self.assertTrue(_valid_gmail_client_file(Path(f.name)))
        os.unlink(f.name)

    def test_invalid_file_rejected(self):
        from actions.email_control import _valid_gmail_client_file

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"web": {"client_id": "x"}}, f)
            f.flush()
            self.assertFalse(_valid_gmail_client_file(Path(f.name)))
        os.unlink(f.name)

    def test_missing_file_rejected(self):
        from actions.email_control import _valid_gmail_client_file
        self.assertFalse(_valid_gmail_client_file(Path("/nonexistent/file.json")))


class TestGmailHelpers(unittest.TestCase):
    """Utility functions in email_control."""

    def test_decode_header_value_plain(self):
        from actions.email_control import _decode_header_value
        self.assertEqual(_decode_header_value("Hello World"), "Hello World")

    def test_decode_header_value_empty(self):
        from actions.email_control import _decode_header_value
        self.assertEqual(_decode_header_value(""), "")
        self.assertEqual(_decode_header_value(None), "")

    def test_headers_map(self):
        from actions.email_control import _headers_map

        payload = {"headers": [
            {"name": "From", "value": "alice@example.com"},
            {"name": "Subject", "value": "Test"},
            {"name": "Date", "value": "Mon, 1 Jan 2024"},
        ]}
        result = _headers_map(payload)
        self.assertEqual(result["from"], "alice@example.com")
        self.assertEqual(result["subject"], "Test")

    def test_headers_map_empty(self):
        from actions.email_control import _headers_map
        self.assertEqual(_headers_map({}), {})

    def test_decode_gmail_data(self):
        from actions.email_control import _decode_gmail_data
        import base64

        original = "Hello, JARVIS!"
        encoded = base64.urlsafe_b64encode(original.encode()).decode().rstrip("=")
        self.assertEqual(_decode_gmail_data(encoded), original)

    def test_decode_gmail_data_empty(self):
        from actions.email_control import _decode_gmail_data
        self.assertEqual(_decode_gmail_data(""), "")
        self.assertEqual(_decode_gmail_data(None), "")

    def test_html_to_text(self):
        from actions.email_control import _html_to_text
        result = _html_to_text("<p>Hello <b>World</b></p>")
        self.assertIn("Hello", result)
        self.assertIn("World", result)

    def test_gmail_body_prefers_plain(self):
        from actions.email_control import _gmail_body
        import base64

        plain_data = base64.urlsafe_b64encode(b"Plain text body").decode()
        html_data = base64.urlsafe_b64encode(b"<p>HTML body</p>").decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": plain_data}},
                {"mimeType": "text/html", "body": {"data": html_data}},
            ],
        }
        result = _gmail_body(payload)
        self.assertIn("Plain text body", result)

    def test_gmail_body_falls_back_to_html(self):
        from actions.email_control import _gmail_body
        import base64

        html_data = base64.urlsafe_b64encode(b"<p>Only HTML</p>").decode()
        payload = {
            "mimeType": "text/html",
            "body": {"data": html_data},
        }
        result = _gmail_body(payload)
        self.assertIn("Only HTML", result)

    def test_normalize_recipients_csv(self):
        from actions.email_control import _normalize_recipients
        result = _normalize_recipients("alice@a.com, bob@b.com")
        self.assertIn("alice@a.com", result)
        self.assertIn("bob@b.com", result)

    def test_normalize_recipients_deduplicates(self):
        from actions.email_control import _normalize_recipients
        result = _normalize_recipients("a@a.com, A@a.com")
        self.assertEqual(result.count("@"), 1)

    def test_normalize_recipients_list_input(self):
        from actions.email_control import _normalize_recipients
        result = _normalize_recipients(["alice@a.com", "bob@b.com"])
        self.assertIn("alice@a.com", result)

    def test_bounded_limit(self):
        from actions.email_control import _bounded_limit
        self.assertEqual(_bounded_limit(5), 5)
        self.assertEqual(_bounded_limit(0), 1)
        self.assertEqual(_bounded_limit(100), 30)
        self.assertEqual(_bounded_limit(None), 10)
        self.assertEqual(_bounded_limit("abc"), 10)


class TestGmailFormatRows(unittest.TestCase):

    def test_format_rows_empty(self):
        from actions.email_control import _format_rows
        result = _format_rows([], "Inbox")
        self.assertIn("no matching messages", result)

    def test_format_rows_with_data(self):
        from actions.email_control import _format_rows
        rows = [{"id": "1", "sender": "a@a.com", "subject": "Hi", "date": "Jan 1", "read": False}]
        result = _format_rows(rows, "Inbox")
        self.assertIn("UNREAD", result)
        self.assertIn("a@a.com", result)
        self.assertIn("1 message(s)", result)

    def test_parse_rows(self):
        from actions.email_control import _parse_rows, _FIELD_SEPARATOR, _RECORD_SEPARATOR
        raw = _FIELD_SEPARATOR.join(["123", "sender@x.com", "Subject", "Jan 1", "false"]) + _RECORD_SEPARATOR
        rows = _parse_rows(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "123")
        self.assertFalse(rows[0]["read"])


class TestEmailControlDispatch(unittest.TestCase):
    """email_control() dispatch table and action aliases."""

    def test_unknown_action(self):
        from actions.email_control import email_control
        result = email_control({"action": "nonexistent"})
        self.assertIn("Unknown email action", result)

    def test_action_aliases(self):
        from actions.email_control import email_control
        with patch("actions.email_control._gmail_list", return_value="inbox ok") as mock_list:
            result = email_control({"action": "list"})
            self.assertEqual(result, "inbox ok")

    def test_inbox_requires_provider(self):
        from actions.email_control import email_control
        result = email_control({"action": "inbox", "provider": "outlook"})
        self.assertIn("unavailable", result.lower())

    def test_search_requires_query(self):
        from actions.email_control import email_control
        result = email_control({"action": "search", "query": ""})
        self.assertIn("which sender or subject", result.lower())

    def test_read_requires_message_id(self):
        from actions.email_control import email_control
        result = email_control({"action": "read", "message_id": ""})
        self.assertIn("message ID", result)

    def test_prepare_requires_all_fields(self):
        from actions.email_control import email_control
        result = email_control({"action": "prepare", "to": "", "subject": "x", "body": "y"})
        self.assertIn("recipient", result.lower())

        result = email_control({"action": "prepare", "to": "a@a.com", "subject": "", "body": "y"})
        self.assertIn("subject", result.lower())

        result = email_control({"action": "prepare", "to": "a@a.com", "subject": "x", "body": ""})
        self.assertIn("body", result.lower())

    def test_approve_no_pending(self):
        from actions.email_control import email_control, _clear_pending_email
        _clear_pending_email()
        result = email_control({"action": "approve"})
        self.assertIn("no pending email", result.lower())

    def test_cancel_no_pending(self):
        from actions.email_control import email_control, _clear_pending_email
        _clear_pending_email()
        result = email_control({"action": "cancel"})
        self.assertIn("no pending email", result.lower())


class TestPendingEmailLifecycle(unittest.TestCase):
    """_set_pending_email / _get_pending_email / _clear_pending_email."""

    def test_lifecycle(self):
        from actions.email_control import (
            _set_pending_email, _get_pending_email, _clear_pending_email,
        )
        _clear_pending_email()
        self.assertEqual(_get_pending_email(), {})
        draft = {"to": "a@a.com", "subject": "Hi", "body": "Hello"}
        _set_pending_email(draft)
        self.assertEqual(_get_pending_email()["to"], "a@a.com")
        _clear_pending_email()
        self.assertEqual(_get_pending_email(), {})


class TestNormalizedVisibleText(unittest.TestCase):

    def test_whitespace_normalization(self):
        from actions.email_control import _normalized_visible_text
        self.assertEqual(
            _normalized_visible_text("  Hello   World  "),
            "Hello World",
        )

    def test_none_input(self):
        from actions.email_control import _normalized_visible_text
        self.assertEqual(_normalized_visible_text(None), "")


class TestGmailConnectPhysical(unittest.TestCase):

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real Google OAuth credentials")
    def test_gmail_connect_real(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real Gmail account")
    def test_gmail_inbox_real(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real Gmail and browser for compose")
    def test_gmail_compose_and_send_real(self):
        pass


# ---------------------------------------------------------------------------
# B — MULTIMEDIA (media_control.py)
# ---------------------------------------------------------------------------

class TestSpotifyUri(unittest.TestCase):

    def test_spotify_link_converted(self):
        from actions.media_control import _spotify_uri
        result = _spotify_uri("https://open.spotify.com/track/abc123")
        self.assertEqual(result, "spotify:track:abc123")

    def test_spotify_album_link(self):
        from actions.media_control import _spotify_uri
        result = _spotify_uri("https://open.spotify.com/album/xyz")
        self.assertEqual(result, "spotify:album:xyz")

    def test_spotify_playlist_link(self):
        from actions.media_control import _spotify_uri
        result = _spotify_uri("https://open.spotify.com/playlist/abc")
        self.assertEqual(result, "spotify:playlist:abc")

    def test_spotify_native_uri_passthrough(self):
        from actions.media_control import _spotify_uri
        self.assertEqual(_spotify_uri("spotify:track:abc"), "spotify:track:abc")

    def test_plain_text_returns_empty(self):
        from actions.media_control import _spotify_uri
        self.assertEqual(_spotify_uri("my favorite song"), "")

    def test_non_spotify_url_returns_empty(self):
        from actions.media_control import _spotify_uri
        self.assertEqual(_spotify_uri("https://example.com/track/abc"), "")

    def test_empty_and_none(self):
        from actions.media_control import _spotify_uri
        self.assertEqual(_spotify_uri(""), "")
        self.assertEqual(_spotify_uri(None), "")


class TestMediaActionAliases(unittest.TestCase):

    def test_resume_is_play(self):
        from actions.media_control import _ACTION_ALIASES
        self.assertEqual(_ACTION_ALIASES["resume"], "play")
        self.assertEqual(_ACTION_ALIASES["skip"], "next")
        self.assertEqual(_ACTION_ALIASES["prev"], "previous")
        self.assertEqual(_ACTION_ALIASES["play_pause"], "toggle")

    def test_platform_aliases(self):
        from actions.media_control import _PLATFORM_ALIASES
        self.assertEqual(_PLATFORM_ALIASES[""], "spotify")
        self.assertEqual(_PLATFORM_ALIASES["apple music"], "apple_music")
        self.assertEqual(_PLATFORM_ALIASES["youtube"], "youtube_music")
        self.assertEqual(_PLATFORM_ALIASES["default"], "system")


class TestMediaControlDispatch(unittest.TestCase):

    def test_unknown_action_rejected(self):
        from actions.media_control import media_control
        result = media_control({"action": "rewind"})
        self.assertIn("Unknown media action", result)

    def test_unknown_platform_rejected(self):
        from actions.media_control import media_control
        result = media_control({"action": "play", "platform": "tidal"})
        self.assertIn("Unknown music platform", result)

    def test_play_query_without_query_rejected(self):
        from actions.media_control import media_control
        result = media_control({"action": "play_query", "query": ""})
        self.assertIn("which song", result.lower())

    def test_play_query_system_rejected(self):
        from actions.media_control import media_control
        result = media_control({"action": "play", "query": "Bohemian Rhapsody", "platform": "system"})
        self.assertIn("Choose Spotify", result)

    @patch("actions.media_control._generic_media_key", return_value="System media toggle command sent.")
    def test_toggle_uses_system_fallback_on_windows(self, mock_key):
        from actions.media_control import media_control
        with patch("actions.media_control._SYSTEM", "Windows"):
            result = media_control({"action": "toggle", "platform": "system"})
        self.assertIn("System media", result)

    @patch("actions.media_control._open_uri", return_value=(True, ""))
    def test_spotify_play_query_non_darwin(self, mock_open):
        from actions.media_control import media_control
        with patch("actions.media_control._SYSTEM", "Windows"):
            result = media_control({"action": "play", "query": "test song", "platform": "spotify"})
        self.assertIn("Spotify results", result)

    @patch("actions.media_control._open_uri", return_value=(True, ""))
    def test_spotify_direct_link_play(self, mock_open):
        from actions.media_control import media_control
        with patch("actions.media_control._SYSTEM", "Windows"):
            result = media_control({
                "action": "play",
                "query": "https://open.spotify.com/track/abc123",
                "platform": "spotify",
            })
        mock_open.assert_called_once()
        self.assertIn("Spotify", result)

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real Spotify running")
    def test_spotify_real_playback(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real YouTube Music")
    def test_youtube_music_real_playback(self):
        pass


# ---------------------------------------------------------------------------
# C — REMINDERS (reminder.py)
# ---------------------------------------------------------------------------

class TestReminderSanitise(unittest.TestCase):

    def test_strips_dangerous_chars(self):
        from actions.reminder import _sanitise
        result = _sanitise('He said "hello\\world"\nnewline')
        self.assertNotIn('"', result)
        self.assertNotIn("\\", result)
        self.assertNotIn("\n", result)

    def test_max_length(self):
        from actions.reminder import _sanitise
        result = _sanitise("a" * 500, max_len=100)
        self.assertEqual(len(result), 100)


class TestReminderValidation(unittest.TestCase):

    def test_missing_date(self):
        from actions.reminder import reminder
        result = reminder({"date": "", "time": "14:00", "message": "Test"})
        self.assertIn("fecha y una hora", result.lower())

    def test_missing_time(self):
        from actions.reminder import reminder
        result = reminder({"date": "2099-01-01", "time": "", "message": "Test"})
        self.assertIn("fecha y una hora", result.lower())

    def test_invalid_date_format(self):
        from actions.reminder import reminder
        result = reminder({"date": "tomorrow", "time": "noon", "message": "Test"})
        self.assertIn("hora concreta", result.lower())

    def test_past_date_rejected(self):
        from actions.reminder import reminder
        result = reminder({"date": "2020-01-01", "time": "10:00", "message": "Test"})
        self.assertIn("ya ha pasado", result.lower())


class TestReminderScheduling(unittest.TestCase):

    @patch("actions.reminder.subprocess.run")
    @patch("actions.reminder._write_notify_script")
    def test_windows_scheduling(self, mock_script, mock_run):
        from actions.reminder import reminder
        mock_script.return_value = Path("C:/fake/script.py")
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="SUCCESS", stderr="")
        future = datetime.now() + timedelta(days=1)
        with patch("actions.reminder._get_os", return_value="windows"):
            result = reminder({
                "date": future.strftime("%Y-%m-%d"),
                "time": "14:00",
                "message": "Test reminder",
            })
        self.assertIn("Recordatorio", result)
        self.assertIn("programado", result)

    @patch("actions.reminder.subprocess.run")
    @patch("actions.reminder._write_notify_script")
    def test_scheduling_failure(self, mock_script, mock_run):
        from actions.reminder import reminder
        mock_script.return_value = Path("C:/fake/script.py")
        mock_run.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="Access denied")
        future = datetime.now() + timedelta(days=1)
        with patch("actions.reminder._get_os", return_value="windows"):
            result = reminder({
                "date": future.strftime("%Y-%m-%d"),
                "time": "14:00",
                "message": "Test",
            })
        self.assertIn("no pude registrar", result.lower())


class TestWriteNotifyScript(unittest.TestCase):

    def test_windows_script_content(self):
        from actions.reminder import _write_notify_script
        d = tempfile.mkdtemp()
        try:
            with patch("actions.reminder._scripts_dir", return_value=Path(d)):
                path = _write_notify_script("test_task", "Hello!", "windows")
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn("Hello!", content)
            self.assertIn("plyer", content)
            self.assertIn("win10toast", content)
            self.assertIn("winsound", content)
            self.assertIn("Self-delete", content)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_mac_script_content(self):
        from actions.reminder import _write_notify_script
        d = tempfile.mkdtemp()
        try:
            with patch("actions.reminder._scripts_dir", return_value=Path(d)):
                path = _write_notify_script("test_task", "Mac reminder", "mac")
            content = path.read_text(encoding="utf-8")
            self.assertIn("osascript", content)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_linux_script_content(self):
        from actions.reminder import _write_notify_script
        d = tempfile.mkdtemp()
        try:
            with patch("actions.reminder._scripts_dir", return_value=Path(d)):
                path = _write_notify_script("test_task", "Linux reminder", "linux")
            content = path.read_text(encoding="utf-8")
            self.assertIn("notify-send", content)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real OS scheduler")
    def test_real_reminder_fires(self):
        pass


# ---------------------------------------------------------------------------
# D — PRESENTATIONS (presentation_maker.py)
# ---------------------------------------------------------------------------

class TestSafeFilename(unittest.TestCase):

    def test_normal_title(self):
        from actions.presentation_maker import _safe_filename
        result = _safe_filename("Q4 Revenue Report")
        self.assertTrue(result.endswith(".pptx"))
        self.assertIn("Q4_Revenue_Report", result)

    def test_empty_title(self):
        from actions.presentation_maker import _safe_filename
        result = _safe_filename("")
        self.assertEqual(result, "JARVIS_Presentation.pptx")

    def test_special_chars_removed(self):
        from actions.presentation_maker import _safe_filename
        result = _safe_filename("Test<>|/\\:?*Report")
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        self.assertNotIn("|", result)

    def test_already_pptx(self):
        from actions.presentation_maker import _safe_filename
        result = _safe_filename("Report.pptx")
        self.assertEqual(result.count(".pptx"), 1)

    def test_long_title_truncated(self):
        from actions.presentation_maker import _safe_filename
        result = _safe_filename("A" * 200)
        self.assertLessEqual(len(result), 85)


class TestOutputPath(unittest.TestCase):

    def test_empty_path_uses_desktop(self):
        from actions.presentation_maker import _output_path
        result = _output_path("", "Test Title")
        self.assertIn("JARVIS Presentations", str(result))
        self.assertTrue(str(result).endswith(".pptx"))

    def test_explicit_path(self):
        from actions.presentation_maker import _output_path
        result = _output_path("C:/Users/test/my_deck.pptx", "Title")
        self.assertEqual(str(result), "C:\\Users\\test\\my_deck.pptx")

    def test_relative_path(self):
        from actions.presentation_maker import _output_path
        result = _output_path("subfolder/deck.pptx", "Title")
        self.assertIn("Desktop", str(result))


class TestCleanJson(unittest.TestCase):

    def test_strips_code_fence(self):
        from actions.presentation_maker import _clean_json
        raw = '```json\n{"title": "Test"}\n```'
        result = _clean_json(raw)
        self.assertEqual(result["title"], "Test")

    def test_extracts_from_noise(self):
        from actions.presentation_maker import _clean_json
        raw = 'Here is the plan:\n{"slides": []}\nDone.'
        result = _clean_json(raw)
        self.assertEqual(result["slides"], [])

    def test_invalid_json_raises(self):
        from actions.presentation_maker import _clean_json
        with self.assertRaises(ValueError):
            _clean_json("No JSON here at all")


class TestTrimConciseItems(unittest.TestCase):

    def test_trim(self):
        from actions.presentation_maker import _trim
        self.assertEqual(_trim("Hello", 100), "Hello")
        self.assertEqual(len(_trim("A" * 200, 50)), 50)
        self.assertTrue(_trim("A" * 200, 50).endswith("…"))

    def test_concise(self):
        from actions.presentation_maker import _concise
        self.assertEqual(_concise("One two three", 10, 200), "One two three")
        result = _concise("One two three four five six", 3, 200)
        self.assertTrue(result.endswith("…"))

    def test_items(self):
        from actions.presentation_maker import _items
        self.assertEqual(_items(None), [])
        self.assertEqual(_items([]), [])
        self.assertEqual(len(_items(["a", "b", "c", "d", "e", "f"], limit=3)), 3)

    def test_items_trims_each(self):
        from actions.presentation_maker import _items
        result = _items(["A" * 200], limit=5, maximum=50)
        self.assertEqual(len(result[0]), 50)


class TestChartNormalization(unittest.TestCase):

    def test_valid_chart(self):
        from actions.presentation_maker import _chart
        result = _chart({
            "type": "bar",
            "title": "Revenue",
            "categories": ["Q1", "Q2"],
            "series": [{"name": "Sales", "values": [100, 200]}],
        })
        self.assertEqual(result["type"], "bar")
        self.assertEqual(result["categories"], ["Q1", "Q2"])
        self.assertEqual(len(result["series"]), 1)

    def test_invalid_chart_type_defaults(self):
        from actions.presentation_maker import _chart
        result = _chart({"type": "radar"})
        self.assertEqual(result["type"], "column")

    def test_empty_chart(self):
        from actions.presentation_maker import _chart
        result = _chart(None)
        self.assertEqual(result["type"], "column")
        self.assertEqual(result["series"], [])


class TestTableNormalization(unittest.TestCase):

    def test_valid_table(self):
        from actions.presentation_maker import _table
        result = _table({
            "headers": ["Name", "Value"],
            "rows": [["A", "1"], ["B", "2"]],
        })
        self.assertEqual(len(result["headers"]), 2)
        self.assertEqual(len(result["rows"]), 2)

    def test_empty_table(self):
        from actions.presentation_maker import _table
        result = _table(None)
        self.assertEqual(result["headers"], [])
        self.assertEqual(result["rows"], [])


class TestNormalizePlan(unittest.TestCase):

    def test_normalizes_correct_count(self):
        from actions.presentation_maker import _normalize_plan
        plan = {
            "title": "Test",
            "slides": [
                {"type": "cover", "title": "Intro"},
                {"type": "statement", "title": "Point 1"},
                {"type": "closing", "title": "End"},
            ],
        }
        result = _normalize_plan(plan, "Test Topic", 3)
        self.assertEqual(len(result["slides"]), 3)
        self.assertEqual(result["slides"][0]["type"], "cover")
        self.assertEqual(result["slides"][-1]["type"], "closing")

    def test_wrong_count_raises(self):
        from actions.presentation_maker import _normalize_plan
        plan = {"slides": [{"type": "cover"}, {"type": "closing"}]}
        with self.assertRaises(ValueError):
            _normalize_plan(plan, "Test", 5)

    def test_deck_profile_defaults(self):
        from actions.presentation_maker import _normalize_plan
        plan = {
            "slides": [{"type": "cover"}, {"type": "statement"}, {"type": "closing"}],
            "deck_profile": "invalid_profile",
        }
        result = _normalize_plan(plan, "Test", 3)
        self.assertEqual(result["deck_profile"], "general")


class TestPlanQualityIssues(unittest.TestCase):

    def test_repeated_layout_detected(self):
        from actions.presentation_maker import _plan_quality_issues
        plan = {"slides": [
            {"type": "cover", "title": "Intro"},
            {"type": "statement", "title": "A", "subtitle": "x"},
            {"type": "statement", "title": "B", "subtitle": "y"},
            {"type": "statement", "title": "C", "subtitle": "z"},
            {"type": "closing", "title": "End"},
        ]}
        issues = _plan_quality_issues(plan)
        found = any("repeats the same layout" in i for i in issues)
        self.assertTrue(found)

    def test_repeated_title_detected(self):
        from actions.presentation_maker import _plan_quality_issues
        plan = {"slides": [
            {"type": "cover", "title": "Same Title"},
            {"type": "statement", "title": "Same Title", "subtitle": "x"},
            {"type": "closing", "title": "End"},
        ]}
        issues = _plan_quality_issues(plan)
        found = any("repeats an earlier title" in i for i in issues)
        self.assertTrue(found)


class TestEnforceVisualStory(unittest.TestCase):

    def test_consumer_retail_gets_images(self):
        from actions.presentation_maker import _enforce_visual_story
        plan = {
            "deck_profile": "consumer-retail",
            "slides": [
                {"type": "cover", "title": "Nature"},
                {"type": "statement", "title": "Trees"},
                {"type": "image", "title": "Forest"},
                {"type": "closing", "title": "End"},
            ],
        }
        result = _enforce_visual_story(plan, "Nature photography")
        visual_count = sum(
            1 for s in result["slides"]
            if s.get("asset_ref") or s.get("image_prompt")
        )
        self.assertGreaterEqual(visual_count, 2)

    def test_non_consumer_retail_unchanged(self):
        from actions.presentation_maker import _enforce_visual_story
        plan = {
            "deck_profile": "general",
            "slides": [{"type": "cover", "title": "Test"}],
        }
        result = _enforce_visual_story(plan, "Finance")
        self.assertEqual(result, plan)


class TestPresentationExecutionMode(unittest.TestCase):

    def test_valid_modes(self):
        from actions.presentation_maker import _presentation_execution_mode
        self.assertEqual(_presentation_execution_mode({"execution_mode": "background"}), "background")
        self.assertEqual(_presentation_execution_mode({"execution_mode": "visible"}), "visible")
        self.assertEqual(_presentation_execution_mode({"execution_mode": "ask"}), "ask")

    def test_aliases(self):
        from actions.presentation_maker import _presentation_execution_mode
        self.assertEqual(_presentation_execution_mode({"execution_mode": "foreground"}), "visible")
        self.assertEqual(_presentation_execution_mode({"execution_mode": "quiet"}), "background")

    def test_invalid_mode_raises(self):
        from actions.presentation_maker import _presentation_execution_mode
        with self.assertRaises(ValueError):
            _presentation_execution_mode({"execution_mode": "turbo"})


class TestPresentation3DPreference(unittest.TestCase):

    def test_explicit_yes(self):
        from actions.presentation_maker import _presentation_3d_preference
        self.assertTrue(_presentation_3d_preference({"three_d_mode": "yes"}))

    def test_explicit_no(self):
        from actions.presentation_maker import _presentation_3d_preference
        self.assertFalse(_presentation_3d_preference({"three_d_mode": "no"}))

    def test_topic_with_3d(self):
        from actions.presentation_maker import _presentation_3d_preference
        self.assertTrue(_presentation_3d_preference({"topic": "use 3D models in it"}))

    def test_topic_without_3d(self):
        from actions.presentation_maker import _presentation_3d_preference
        self.assertFalse(_presentation_3d_preference({"topic": "without 3D please"}))

    def test_unspecified_returns_none(self):
        from actions.presentation_maker import _presentation_3d_preference
        self.assertIsNone(_presentation_3d_preference({"topic": "just a normal presentation"}))


class TestExtractSource(unittest.TestCase):

    def test_txt_file(self):
        from actions.presentation_maker import _extract_source
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("Source material for presentation")
            f.flush()
            result = _extract_source(f.name)
        self.assertIn("Source material", result)
        os.unlink(f.name)

    def test_json_file(self):
        from actions.presentation_maker import _extract_source
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump({"data": "test"}, f)
            f.flush()
            result = _extract_source(f.name)
        self.assertIn("data", result)
        os.unlink(f.name)

    def test_empty_path(self):
        from actions.presentation_maker import _extract_source
        self.assertEqual(_extract_source(""), "")

    def test_missing_file_raises(self):
        from actions.presentation_maker import _extract_source
        with self.assertRaises(FileNotFoundError):
            _extract_source("/nonexistent/file.txt")

    def test_unsupported_format_raises(self):
        from actions.presentation_maker import _extract_source
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"binary data")
            f.flush()
        with self.assertRaises(ValueError):
            _extract_source(f.name)
        os.unlink(f.name)

    def test_truncation_at_50k(self):
        from actions.presentation_maker import _extract_source
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("x" * 60_000)
            f.flush()
            result = _extract_source(f.name)
        self.assertEqual(len(result), 50_000)
        os.unlink(f.name)


class TestQuotaFallbackPlan(unittest.TestCase):

    def test_produces_correct_slide_count(self):
        from actions.presentation_maker import _quota_fallback_plan
        from actions.presentations.models import PresentationRequest
        request = PresentationRequest(topic="Test Topic", title="Test")
        plan = _quota_fallback_plan(request, 5, "Some source text here.")
        self.assertEqual(len(plan["slides"]), 5)
        self.assertEqual(plan["slides"][0]["type"], "cover")
        self.assertEqual(plan["slides"][-1]["type"], "closing")

    def test_uses_evidence_from_source(self):
        from actions.presentation_maker import _quota_fallback_plan
        from actions.presentations.models import PresentationRequest
        request = PresentationRequest(topic="Revenue", title="Revenue")
        source = "Q1 revenue grew 15% year-over-year to $2.3 billion.\nCustomer count reached 50 million."
        plan = _quota_fallback_plan(request, 4, source)
        all_text = json.dumps(plan)
        self.assertTrue(
            "Q1 revenue" in all_text or "Customer count" in all_text
        )


class TestThemes(unittest.TestCase):

    def test_all_themes_have_required_keys(self):
        from actions.presentation_maker import THEMES
        required = {"ink", "paper", "accent", "accent_2", "muted", "white"}
        for name, colors in THEMES.items():
            self.assertTrue(
                required.issubset(colors.keys()),
                f"Theme {name} missing keys: {required - colors.keys()}",
            )

    def test_color_values_are_hex(self):
        from actions.presentation_maker import THEMES
        for name, colors in THEMES.items():
            for key, value in colors.items():
                self.assertTrue(
                    re.fullmatch(r"[0-9A-Fa-f]{6}", value),
                    f"Theme {name}.{key} = '{value}' is not valid hex",
                )


class TestCreatePresentationEntry(unittest.TestCase):

    @patch("actions.presentation_maker.build_presentation")
    def test_returns_result_string(self, mock_build):
        from actions.presentation_maker import create_presentation
        mock_build.return_value = "Presentation created at /path/to/file.pptx"
        result = create_presentation({"topic": "Test"})
        self.assertIn("Presentation created", result)

    @patch("actions.presentation_maker.build_presentation", side_effect=RuntimeError("API key missing"))
    def test_handles_exception(self, mock_build):
        from actions.presentation_maker import create_presentation
        result = create_presentation({"topic": "Test"})
        self.assertIn("Could not create", result)

    @unittest.skip("PHYSICAL TEST REQUIRED — needs Gemini API key and python-pptx")
    def test_real_presentation_creation(self):
        pass


class TestPresentationPending(unittest.TestCase):

    def test_pending_lifecycle(self):
        from actions.presentation_maker import (
            _remember_pending_presentation,
            _take_pending_presentation,
        )
        params = {"topic": "Test", "title": "Test Deck"}
        _remember_pending_presentation(params)
        result = _take_pending_presentation({})
        self.assertIsNotNone(result)
        self.assertEqual(result["topic"], "Test")
        # Second take should return None (consumed)
        result2 = _take_pending_presentation({})
        self.assertIsNone(result2)


class TestSafeOutputForSource(unittest.TestCase):

    def test_different_paths_unchanged(self):
        from actions.presentation_maker import _safe_output_for_source
        output = Path("C:/out/deck.pptx")
        source = Path("C:/src/original.pptx")
        result = _safe_output_for_source(output, source, "edit")
        self.assertEqual(result, output)

    def test_same_path_gets_suffix(self):
        from actions.presentation_maker import _safe_output_for_source
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            path = Path(f.name)
        result = _safe_output_for_source(path, path, "edit")
        self.assertIn("edited", result.stem)
        path.unlink(missing_ok=True)

    def test_extend_suffix(self):
        from actions.presentation_maker import _safe_output_for_source
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            path = Path(f.name)
        result = _safe_output_for_source(path, path, "extend")
        self.assertIn("extended", result.stem)
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
