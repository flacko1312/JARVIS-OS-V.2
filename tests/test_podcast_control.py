"""Tests for actions.podcast_control — podcast search and playback."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from actions.podcast_control import (
    _action_episodes,
    _action_play,
    _action_search,
    _action_status,
    _action_stop,
    _fetch_rss_episodes,
    _search_podcasts,
    podcast_control,
)

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test Podcast</title>
    <item>
      <title>Episodio 42</title>
      <enclosure url="https://example.com/ep42.mp3" type="audio/mpeg" length="12345"/>
      <pubDate>Mon, 04 Nov 2026 10:00:00 +0000</pubDate>
      <itunes:duration>35:00</itunes:duration>
    </item>
    <item>
      <title>Episodio 41</title>
      <enclosure url="https://example.com/ep41.mp3" type="audio/mpeg" length="11000"/>
      <pubDate>Mon, 27 Oct 2026 10:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_SAMPLE_ITUNES = {
    "resultCount": 1,
    "results": [
        {
            "collectionName": "Podcast de Prueba",
            "artistName": "Autor Test",
            "feedUrl": "https://example.com/feed.xml",
            "collectionId": 12345,
        }
    ],
}


@pytest.fixture(autouse=True)
def reset_state():
    import actions.podcast_control as pc
    pc._CURRENT_PROC = None
    pc._CURRENT_TITLE = ""
    pc._CURRENT_URL = ""
    yield
    if pc._CURRENT_PROC is not None:
        try:
            pc._CURRENT_PROC.terminate()
        except Exception:
            pass
    pc._CURRENT_PROC = None
    pc._CURRENT_TITLE = ""
    pc._CURRENT_URL = ""


def _mock_http(content: bytes):
    with patch("actions.podcast_control._http_get", return_value=content):
        yield


class TestFetchRssEpisodes:
    def test_parses_items(self):
        with patch("actions.podcast_control._http_get", return_value=_SAMPLE_RSS.encode()):
            episodes = _fetch_rss_episodes("https://example.com/feed.xml")
        assert len(episodes) == 2
        assert episodes[0]["title"] == "Episodio 42"
        assert episodes[0]["url"] == "https://example.com/ep42.mp3"
        assert episodes[0]["duration"] == "35:00"

    def test_max_ep_respected(self):
        with patch("actions.podcast_control._http_get", return_value=_SAMPLE_RSS.encode()):
            episodes = _fetch_rss_episodes("https://example.com/feed.xml", max_ep=1)
        assert len(episodes) == 1

    def test_network_error_raises(self):
        with patch("actions.podcast_control._http_get", side_effect=Exception("timeout")):
            with pytest.raises(Exception, match="timeout"):
                _fetch_rss_episodes("https://example.com/feed.xml")


class TestSearchPodcasts:
    def test_returns_results(self):
        with patch("actions.podcast_control._http_get",
                   return_value=json.dumps(_SAMPLE_ITUNES).encode()):
            results = _search_podcasts("test")
        assert len(results) == 1
        assert results[0]["collectionName"] == "Podcast de Prueba"

    def test_empty_results(self):
        with patch("actions.podcast_control._http_get",
                   return_value=json.dumps({"resultCount": 0, "results": []}).encode()):
            results = _search_podcasts("xyz123")
        assert results == []


class TestActionSearch:
    def test_no_query(self):
        result = _action_search("")
        assert "especifica" in result.lower()

    def test_found(self):
        with patch("actions.podcast_control._http_get",
                   return_value=json.dumps(_SAMPLE_ITUNES).encode()):
            result = _action_search("prueba")
        assert "Podcast de Prueba" in result

    def test_not_found(self):
        with patch("actions.podcast_control._http_get",
                   return_value=json.dumps({"resultCount": 0, "results": []}).encode()):
            result = _action_search("xyz123")
        assert "no encontré" in result.lower()

    def test_network_error(self):
        with patch("actions.podcast_control._http_get", side_effect=Exception("refused")):
            result = _action_search("prueba")
        assert "error" in result.lower()


class TestActionEpisodes:
    def test_no_query_no_feed(self):
        result = _action_episodes("", "")
        assert "especifica" in result.lower()

    def test_via_feed_url(self):
        with patch("actions.podcast_control._http_get", return_value=_SAMPLE_RSS.encode()):
            result = _action_episodes("", "https://example.com/feed.xml")
        assert "Episodio 42" in result

    def test_via_search(self):
        def side_effect(url):
            if "itunes" in url:
                return json.dumps(_SAMPLE_ITUNES).encode()
            return _SAMPLE_RSS.encode()
        with patch("actions.podcast_control._http_get", side_effect=side_effect):
            result = _action_episodes("prueba", "")
        assert "Episodio" in result

    def test_no_feed_in_search_result(self):
        no_feed = {"resultCount": 1, "results": [{"collectionName": "Sin Feed", "feedUrl": ""}]}
        with patch("actions.podcast_control._http_get",
                   return_value=json.dumps(no_feed).encode()):
            result = _action_episodes("sin feed", "")
        assert "rss" in result.lower() or "feed" in result.lower()


class TestActionPlay:
    def test_no_args(self):
        result = _action_play()
        assert "especifica" in result.lower()

    def test_direct_episode_url(self):
        proc = MagicMock()
        with patch("actions.podcast_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play(episode_url="https://example.com/ep.mp3")
        assert "example.com" in result or "reproduciendo" in result.lower()

    def test_play_latest_via_search(self):
        def side_effect(url):
            if "itunes" in url:
                return json.dumps(_SAMPLE_ITUNES).encode()
            return _SAMPLE_RSS.encode()
        proc = MagicMock()
        with patch("actions.podcast_control._http_get", side_effect=side_effect), \
             patch("actions.podcast_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play(query="prueba")
        assert "Episodio 42" in result or "reproduciendo" in result.lower()

    def test_play_no_ffplay_fallback(self):
        with patch("actions.podcast_control._http_get",
                   side_effect=lambda url: (json.dumps(_SAMPLE_ITUNES).encode() if "itunes" in url else _SAMPLE_RSS.encode())):
            with patch("actions.podcast_control._find_ffplay", return_value=None), \
                 patch("os.startfile", create=True) as mock_sf:
                result = _action_play(query="prueba")
        assert isinstance(result, str)


class TestActionStop:
    def test_stop_nothing(self):
        result = _action_stop()
        assert "no hay" in result.lower()

    def test_stop_active(self):
        import actions.podcast_control as pc
        proc = MagicMock()
        proc.poll.return_value = None
        pc._CURRENT_PROC = proc
        pc._CURRENT_TITLE = "Episodio Test"
        pc._CURRENT_URL = "https://example.com"
        result = _action_stop()
        assert "Episodio Test" in result
        proc.terminate.assert_called_once()


class TestActionStatus:
    def test_nothing_playing(self):
        result = _action_status()
        assert "no hay" in result.lower()

    def test_playing(self):
        import actions.podcast_control as pc
        proc = MagicMock()
        proc.poll.return_value = None
        pc._CURRENT_PROC = proc
        pc._CURRENT_TITLE = "Mi Episodio"
        pc._CURRENT_URL = "https://example.com"
        result = _action_status()
        assert "Mi Episodio" in result


class TestPodcastControlEntryPoint:
    def test_unknown_action(self):
        result = podcast_control({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_search_action(self):
        with patch("actions.podcast_control._http_get",
                   return_value=json.dumps(_SAMPLE_ITUNES).encode()):
            result = podcast_control({"action": "search", "query": "prueba"})
        assert "Podcast de Prueba" in result

    def test_stop_action(self):
        result = podcast_control({"action": "stop"})
        assert isinstance(result, str)

    def test_status_action(self):
        result = podcast_control({"action": "status"})
        assert isinstance(result, str)

    def test_none_params(self):
        result = podcast_control(None)
        assert isinstance(result, str)

    def test_podcast_alias(self):
        with patch("actions.podcast_control._http_get",
                   return_value=json.dumps({"resultCount": 0, "results": []}).encode()):
            result = podcast_control({"action": "search", "podcast": "test"})
        assert isinstance(result, str)
