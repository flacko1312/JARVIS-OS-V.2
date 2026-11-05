"""Tests for actions.news_control — RSS news headlines."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from actions.news_control import (
    _action_headlines,
    _action_list_sources,
    _action_summary,
    _parse_rss,
    _resolve_feed,
    news_control,
)

_SAMPLE_RSS = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<rss version='2.0'><channel><title>Test News</title>"
    b"<item><title>El gobierno anuncia medidas</title>"
    b"<description>Nuevas medidas aprobadas hoy.</description>"
    b"<link>https://example.com/1</link>"
    b"<pubDate>Thu, 05 Nov 2026 10:00:00 +0000</pubDate></item>"
    b"<item><title>Lluvia en Madrid</title>"
    b"<description>Las lluvias afectan a la comunidad.</description>"
    b"<link>https://example.com/2</link>"
    b"<pubDate>Thu, 05 Nov 2026 09:00:00 +0000</pubDate></item>"
    b"</channel></rss>"
)

_EMPTY_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>"""
_BAD_XML = b"not xml at all <<<<"


class TestParseRss:
    def test_parses_items(self):
        items = _parse_rss(_SAMPLE_RSS)
        assert len(items) == 2
        assert items[0]["title"] == "El gobierno anuncia medidas"
        assert "medidas" in items[0]["description"]

    def test_max_items_respected(self):
        items = _parse_rss(_SAMPLE_RSS, max_items=1)
        assert len(items) == 1

    def test_empty_feed(self):
        items = _parse_rss(_EMPTY_RSS)
        assert items == []

    def test_bad_xml_returns_empty(self):
        items = _parse_rss(_BAD_XML)
        assert items == []


class TestResolveFeed:
    def test_known_key(self):
        result = _resolve_feed("rtve")
        assert result is not None
        name, url = result
        assert "RTVE" in name

    def test_fuzzy_match(self):
        result = _resolve_feed("bbc")
        assert result is not None

    def test_direct_url(self):
        result = _resolve_feed("https://example.com/feed.rss")
        assert result is not None

    def test_unknown_returns_none(self):
        result = _resolve_feed("nonexistent_feed_xyz")
        assert result is None


class TestActionListSources:
    def test_contains_known_sources(self):
        result = _action_list_sources()
        assert "rtve" in result.lower()
        assert "bbc" in result.lower()
        assert "xataka" in result.lower()


class TestActionHeadlines:
    def test_default_source(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = _action_headlines()
        assert "gobierno" in result.lower() or "Madrid" in result

    def test_specific_source(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = _action_headlines(source="rtve")
        assert isinstance(result, str)

    def test_unknown_source(self):
        result = _action_headlines(source="nonexistent_xyz")
        assert "no encontrada" in result.lower()

    def test_network_error(self):
        with patch("actions.news_control._http_get", side_effect=Exception("timeout")):
            result = _action_headlines(source="rtve")
        assert "error" in result.lower()

    def test_empty_feed(self):
        with patch("actions.news_control._http_get", return_value=_EMPTY_RSS):
            result = _action_headlines(source="bbc")
        assert "no se encontraron" in result.lower()

    def test_max_items_param(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = _action_headlines(source="rtve", max_items=1)
        assert "1." in result
        assert "2." not in result

    def test_direct_url(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = _action_headlines(source="https://example.com/feed.rss")
        assert isinstance(result, str)


class TestActionSummary:
    def test_returns_string(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = _action_summary(source="rtve")
        assert isinstance(result, str)
        assert "gobierno" in result.lower() or "titulares" in result.lower()

    def test_unknown_source(self):
        result = _action_summary(source="nonexistent_xyz")
        assert "no encontrada" in result.lower()

    def test_network_error(self):
        with patch("actions.news_control._http_get", side_effect=Exception("refused")):
            result = _action_summary(source="bbc")
        assert "error" in result.lower()

    def test_no_items(self):
        with patch("actions.news_control._http_get", return_value=_EMPTY_RSS):
            result = _action_summary(source="rtve")
        assert "no hay" in result.lower()


class TestNewsControlEntryPoint:
    def test_none_params_returns_summary(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = news_control(None)
        assert isinstance(result, str)

    def test_headlines_action(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = news_control({"action": "headlines", "source": "rtve"})
        assert isinstance(result, str)

    def test_summary_action(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = news_control({"action": "summary"})
        assert isinstance(result, str)

    def test_sources_action(self):
        result = news_control({"action": "sources"})
        assert "rtve" in result.lower()

    def test_unknown_action(self):
        result = news_control({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_noticias_alias(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = news_control({"action": "noticias"})
        assert isinstance(result, str)

    def test_fuente_alias(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = news_control({"action": "summary", "fuente": "rtve"})
        assert isinstance(result, str)

    def test_count_param(self):
        with patch("actions.news_control._http_get", return_value=_SAMPLE_RSS):
            result = news_control({"action": "headlines", "count": "1"})
        assert "2." not in result
