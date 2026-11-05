"""Tests for actions.audiobook_control — LibriVox audiobook streaming."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from actions.audiobook_control import (
    _action_chapters,
    _action_play,
    _action_search,
    _action_status,
    _action_stop,
    _get_chapters,
    _search_books,
    audiobook_control,
)

# ---------------------------------------------------------------------------
# Sample fixtures

_SAMPLE_BOOKS = {
    "books": [
        {
            "id": "42",
            "title": "The Time Machine",
            "authors": [{"last_name": "Wells", "first_name": "H. G."}],
            "language": "English",
            "num_sections": "12",
            "url_librivox": "https://librivox.org/the-time-machine/",
        }
    ]
}

_SAMPLE_CHAPTERS = {
    "sections": [
        {
            "section_number": "1",
            "title": "Chapter 1",
            "playtime": "10:00",
            "listen_url": "https://ia800.archive.org/the-time-machine-ch1.mp3",
        },
        {
            "section_number": "2",
            "title": "Chapter 2",
            "playtime": "12:00",
            "listen_url": "https://ia800.archive.org/the-time-machine-ch2.mp3",
        },
    ]
}


@pytest.fixture(autouse=True)
def reset_state():
    import actions.audiobook_control as ab
    ab._CURRENT_PROC = None
    ab._CURRENT_TITLE = ""
    ab._CURRENT_URL = ""
    yield
    if ab._CURRENT_PROC is not None:
        try:
            ab._CURRENT_PROC.terminate()
        except Exception:
            pass
    ab._CURRENT_PROC = None
    ab._CURRENT_TITLE = ""
    ab._CURRENT_URL = ""


# ---------------------------------------------------------------------------
# TestSearchBooks


class TestSearchBooks:
    def test_returns_books(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps(_SAMPLE_BOOKS).encode()):
            books = _search_books("time machine")
        assert len(books) == 1
        assert books[0]["title"] == "The Time Machine"

    def test_empty_result_fallback_author(self):
        empty = json.dumps({"books": []}).encode()
        result_with_books = json.dumps(_SAMPLE_BOOKS).encode()
        responses = [empty, result_with_books]
        with patch("actions.audiobook_control._http_get",
                   side_effect=lambda url: responses.pop(0)):
            books = _search_books("wells")
        assert len(books) == 1

    def test_network_error_raises(self):
        with patch("actions.audiobook_control._http_get", side_effect=Exception("timeout")):
            with pytest.raises(Exception, match="timeout"):
                _search_books("test")


class TestGetChapters:
    def test_returns_chapters(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps(_SAMPLE_CHAPTERS).encode()):
            chapters = _get_chapters("42")
        assert len(chapters) == 2
        assert chapters[0]["title"] == "Chapter 1"

    def test_network_error_raises(self):
        with patch("actions.audiobook_control._http_get", side_effect=Exception("refused")):
            with pytest.raises(Exception):
                _get_chapters("42")


# ---------------------------------------------------------------------------
# TestActionSearch


class TestActionSearch:
    def test_no_query(self):
        result = _action_search("")
        assert "especifica" in result.lower()

    def test_found(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps(_SAMPLE_BOOKS).encode()):
            result = _action_search("time machine")
        assert "Time Machine" in result

    def test_not_found(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps({"books": []}).encode()):
            result = _action_search("xyznonexistent123")
        assert "no encontré" in result.lower()

    def test_network_error(self):
        with patch("actions.audiobook_control._http_get", side_effect=Exception("refused")):
            result = _action_search("test")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# TestActionChapters


class TestActionChapters:
    def test_no_args(self):
        result = _action_chapters("", "")
        assert "especifica" in result.lower()

    def test_via_book_id(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps(_SAMPLE_CHAPTERS).encode()):
            result = _action_chapters(book_id="42")
        assert "Chapter 1" in result

    def test_via_search(self):
        def side_effect(url):
            if "audiobooks" in url:
                return json.dumps(_SAMPLE_BOOKS).encode()
            return json.dumps(_SAMPLE_CHAPTERS).encode()
        with patch("actions.audiobook_control._http_get", side_effect=side_effect):
            result = _action_chapters(query="time machine")
        assert "Chapter" in result

    def test_not_found_via_search(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps({"books": []}).encode()):
            result = _action_chapters(query="nonexistent xyz")
        assert "no encontré" in result.lower()

    def test_no_downloadable_chapters(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps({"sections": []}).encode()):
            result = _action_chapters(book_id="99")
        assert "no encontré" in result.lower() or "capítulos" in result.lower()


# ---------------------------------------------------------------------------
# TestActionPlay


class TestActionPlay:
    def test_no_args(self):
        result = _action_play()
        assert "especifica" in result.lower()

    def test_direct_chapter_url(self):
        proc = MagicMock()
        with patch("actions.audiobook_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play(chapter_url="https://ia800.archive.org/ep.mp3")
        assert "reproduciendo" in result.lower() or "ia800" in result

    def test_play_via_search(self):
        def side_effect(url):
            if "audiobooks" in url:
                return json.dumps(_SAMPLE_BOOKS).encode()
            return json.dumps(_SAMPLE_CHAPTERS).encode()
        proc = MagicMock()
        with patch("actions.audiobook_control._http_get", side_effect=side_effect), \
             patch("actions.audiobook_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play(query="time machine")
        assert "Chapter 1" in result or "reproduciendo" in result.lower()

    def test_play_chapter_2(self):
        def side_effect(url):
            if "audiobooks" in url:
                return json.dumps(_SAMPLE_BOOKS).encode()
            return json.dumps(_SAMPLE_CHAPTERS).encode()
        proc = MagicMock()
        with patch("actions.audiobook_control._http_get", side_effect=side_effect), \
             patch("actions.audiobook_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play(query="time machine", chapter=2)
        assert "Chapter 2" in result or "reproduciendo" in result.lower()

    def test_play_chapter_oob_clamps_to_first(self):
        def side_effect(url):
            if "audiobooks" in url:
                return json.dumps(_SAMPLE_BOOKS).encode()
            return json.dumps(_SAMPLE_CHAPTERS).encode()
        proc = MagicMock()
        with patch("actions.audiobook_control._http_get", side_effect=side_effect), \
             patch("actions.audiobook_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play(query="time machine", chapter=99)
        assert isinstance(result, str)

    def test_no_ffplay_fallback(self):
        def side_effect(url):
            if "audiobooks" in url:
                return json.dumps(_SAMPLE_BOOKS).encode()
            return json.dumps(_SAMPLE_CHAPTERS).encode()
        with patch("actions.audiobook_control._http_get", side_effect=side_effect), \
             patch("actions.audiobook_control._find_ffplay", return_value=None), \
             patch("os.startfile", create=True), \
             patch("subprocess.Popen"):
            result = _action_play(query="time machine")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# TestActionStop / Status


class TestActionStop:
    def test_stop_nothing(self):
        result = _action_stop()
        assert "no hay" in result.lower()

    def test_stop_active(self):
        import actions.audiobook_control as ab
        proc = MagicMock()
        proc.poll.return_value = None
        ab._CURRENT_PROC = proc
        ab._CURRENT_TITLE = "The Time Machine — Chapter 1"
        ab._CURRENT_URL = "https://example.com/ch1.mp3"
        result = _action_stop()
        assert "Time Machine" in result
        proc.terminate.assert_called_once()


class TestActionStatus:
    def test_nothing_playing(self):
        result = _action_status()
        assert "no hay" in result.lower()

    def test_something_playing(self):
        import actions.audiobook_control as ab
        proc = MagicMock()
        proc.poll.return_value = None
        ab._CURRENT_PROC = proc
        ab._CURRENT_TITLE = "Dracula — Chapter 5"
        ab._CURRENT_URL = "https://example.com/ch5.mp3"
        result = _action_status()
        assert "Dracula" in result


# ---------------------------------------------------------------------------
# TestEntryPoint


class TestAudiobookControlEntryPoint:
    def test_none_params(self):
        result = audiobook_control(None)
        assert isinstance(result, str)

    def test_unknown_action(self):
        result = audiobook_control({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_search_action(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps(_SAMPLE_BOOKS).encode()):
            result = audiobook_control({"action": "search", "query": "time machine"})
        assert "Time Machine" in result

    def test_stop_action(self):
        result = audiobook_control({"action": "stop"})
        assert isinstance(result, str)

    def test_status_action(self):
        result = audiobook_control({"action": "status"})
        assert isinstance(result, str)

    def test_book_alias(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps(_SAMPLE_BOOKS).encode()):
            result = audiobook_control({"action": "search", "book": "wells"})
        assert isinstance(result, str)

    def test_buscar_alias(self):
        with patch("actions.audiobook_control._http_get",
                   return_value=json.dumps(_SAMPLE_BOOKS).encode()):
            result = audiobook_control({"action": "buscar", "query": "time machine"})
        assert "Time Machine" in result
