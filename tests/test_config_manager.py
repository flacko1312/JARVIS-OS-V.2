"""Tests for memory.config_manager — local-only path (no tenant)."""

import json
from unittest.mock import patch

from memory.config_manager import (
    get_gemini_key,
    is_configured,
    load_api_keys,
    save_api_keys,
)


def test_save_and_load_round_trip(tmp_path):
    config_file = tmp_path / "api_keys.json"
    with (
        patch("memory.config_manager.CONFIG_FILE", config_file),
        patch("memory.config_manager.CONFIG_DIR", tmp_path),
        patch("core.tenant.get_current_user_id", return_value=None),
    ):
        save_api_keys("AIzaSy_test_key_1234567890abc")
        keys = load_api_keys()
    assert keys["gemini_api_key"] == "AIzaSy_test_key_1234567890abc"


def test_get_gemini_key_prefers_env(tmp_path):
    config_file = tmp_path / "api_keys.json"
    config_file.write_text(json.dumps({"gemini_api_key": "from-file"}), encoding="utf-8")
    with (
        patch("memory.config_manager.CONFIG_FILE", config_file),
        patch("core.tenant.get_current_user_id", return_value=None),
        patch.dict("os.environ", {"GEMINI_API_KEY": "from-env"}),
    ):
        assert get_gemini_key() == "from-env"


def test_get_gemini_key_falls_back_to_file(tmp_path):
    config_file = tmp_path / "api_keys.json"
    config_file.write_text(json.dumps({"gemini_api_key": "from-file"}), encoding="utf-8")
    with (
        patch("memory.config_manager.CONFIG_FILE", config_file),
        patch("core.tenant.get_current_user_id", return_value=None),
        patch.dict("os.environ", {}, clear=True),
    ):
        assert get_gemini_key() == "from-file"


def test_is_configured_with_valid_key(tmp_path):
    config_file = tmp_path / "api_keys.json"
    with (
        patch("memory.config_manager.CONFIG_FILE", config_file),
        patch("memory.config_manager.CONFIG_DIR", tmp_path),
        patch("core.tenant.get_current_user_id", return_value=None),
    ):
        save_api_keys("AIzaSy_test_key_1234567890abc")
        assert is_configured()


def test_is_configured_without_key(tmp_path):
    config_file = tmp_path / "nonexistent.json"
    with (
        patch("memory.config_manager.CONFIG_FILE", config_file),
        patch("core.tenant.get_current_user_id", return_value=None),
        patch.dict("os.environ", {}, clear=True),
    ):
        assert not is_configured()


def test_load_handles_corrupt_file(tmp_path):
    config_file = tmp_path / "api_keys.json"
    config_file.write_text("{broken json", encoding="utf-8")
    with (
        patch("memory.config_manager.CONFIG_FILE", config_file),
        patch("core.tenant.get_current_user_id", return_value=None),
    ):
        assert load_api_keys() == {}
