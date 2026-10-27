"""Tests for the deterministic answer cache (local-only, no tenant)."""

import json
from pathlib import Path
from unittest.mock import patch

from memory.answer_cache import (
    is_cacheable_question,
    looks_time_sensitive,
    normalize_question,
    get_cached_answer,
    save_cached_answer,
    MAX_CACHE_ENTRIES,
    _trim_cache,
)


class TestNormalization:
    def test_strips_and_lowercases(self):
        assert normalize_question("  What IS the speed of light?  ") == "what is the speed of light"

    def test_collapses_whitespace(self):
        assert normalize_question("who  was   Einstein") == "who was einstein"

    def test_strips_trailing_punctuation(self):
        assert normalize_question("what is DNA?!") == "what is dna"


class TestTimeSensitivity:
    def test_price_is_time_sensitive(self):
        assert looks_time_sensitive("What is the price of bitcoin?")

    def test_weather_is_time_sensitive(self):
        assert looks_time_sensitive("What's the weather forecast?")

    def test_definition_is_not_time_sensitive(self):
        assert not looks_time_sensitive("What is photosynthesis?")


class TestCacheability:
    def test_definition_is_cacheable(self):
        assert is_cacheable_question("What is the capital of France?")

    def test_command_is_not_cacheable(self):
        assert not is_cacheable_question("open Chrome")

    def test_time_sensitive_is_not_cacheable(self):
        assert not is_cacheable_question("what is the latest news?")

    def test_too_short_is_not_cacheable(self):
        assert not is_cacheable_question("hi?")

    def test_empty_is_not_cacheable(self):
        assert not is_cacheable_question("")


class TestTrimCache:
    def test_trim_keeps_max_entries(self):
        data = {
            f"q{i}": {"answer": f"a{i}", "hits": i, "updated_at": float(i)}
            for i in range(MAX_CACHE_ENTRIES + 50)
        }
        trimmed = _trim_cache(data)
        assert len(trimmed) == MAX_CACHE_ENTRIES

    def test_trim_preserves_high_hit_entries(self):
        data = {
            "popular": {"answer": "yes", "hits": 999, "updated_at": 1.0},
            "rare": {"answer": "no", "hits": 0, "updated_at": 0.0},
        }
        assert len(_trim_cache(data)) == 2


class TestRoundTrip:
    def test_save_and_retrieve(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        with (
            patch("memory.answer_cache.CACHE_PATH", cache_path),
            patch("core.tenant.get_current_user_id", return_value=None),
        ):
            save_cached_answer("What is the capital of France?", "Paris is the capital of France.")
            result = get_cached_answer("What is the capital of France?")
        assert result == "Paris is the capital of France."

    def test_non_cacheable_question_is_not_stored(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        with (
            patch("memory.answer_cache.CACHE_PATH", cache_path),
            patch("core.tenant.get_current_user_id", return_value=None),
        ):
            save_cached_answer("open Chrome", "Opening Chrome.")
            assert not cache_path.exists()

    def test_missing_key_returns_none(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        with (
            patch("memory.answer_cache.CACHE_PATH", cache_path),
            patch("core.tenant.get_current_user_id", return_value=None),
        ):
            assert get_cached_answer("What is dark matter?") is None
