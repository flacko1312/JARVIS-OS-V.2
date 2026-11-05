"""Tests for actions.radio_control — internet radio streaming."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from actions.radio_control import (
    _action_add,
    _action_list,
    _action_play,
    _action_remove,
    _action_status,
    _action_stop,
    _all_stations,
    _BUILTIN_STATIONS,
    radio_control,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Isolate module state between tests."""
    import actions.radio_control as rc
    monkeypatch.setattr(rc, "_CURRENT_PROC", None)
    monkeypatch.setattr(rc, "_CURRENT_STATION", "")
    monkeypatch.setattr(rc, "_CURRENT_NAME", "")
    monkeypatch.setenv("JARVIS_RADIO_DIR", str(tmp_path))
    yield
    # Stop any process left by tests
    import actions.radio_control as rc2
    if rc2._CURRENT_PROC is not None:
        try:
            rc2._CURRENT_PROC.terminate()
        except Exception:
            pass
        rc2._CURRENT_PROC = None
    rc2._CURRENT_STATION = ""
    rc2._CURRENT_NAME = ""


class TestBuiltinStations:
    def test_has_rtve(self):
        assert "radio1" in _BUILTIN_STATIONS
        assert "radio2" in _BUILTIN_STATIONS

    def test_has_cadena_ser(self):
        assert "ser" in _BUILTIN_STATIONS

    def test_all_have_url(self):
        for key, (name, url) in _BUILTIN_STATIONS.items():
            assert url.startswith("http"), f"{key} has bad URL"
            assert name


class TestActionList:
    def test_lists_stations(self):
        result = _action_list()
        assert "radio1" in result.lower() or "rtve" in result.lower()
        assert "ser" in result.lower() or "cadena" in result.lower()


class TestActionPlay:
    def test_no_query(self):
        result = _action_play("")
        assert "especifica" in result.lower()

    def test_unknown_station(self):
        result = _action_play("estacion_inexistente_xyzabc")
        assert "no encontré" in result.lower()

    def test_play_by_key_with_ffplay(self):
        proc = MagicMock()
        proc.poll.return_value = None
        with patch("actions.radio_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play("radio1")
        assert "reproduciendo" in result.lower() or "Radio" in result

    def test_play_direct_url(self):
        proc = MagicMock()
        with patch("actions.radio_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play("https://example.com/stream.mp3")
        assert "example.com" in result or "reproduciendo" in result.lower()

    def test_play_fuzzy_match(self):
        proc = MagicMock()
        with patch("actions.radio_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play("cadena ser")
        assert "SER" in result or "Cadena" in result or "reproduciendo" in result.lower()

    def test_play_fallback_no_ffplay(self):
        proc = MagicMock()
        with patch("actions.radio_control._find_ffplay", return_value=None), \
             patch("os.startfile", create=True), \
             patch("subprocess.Popen", return_value=proc):
            result = _action_play("radio1")
        assert isinstance(result, str)


class TestActionStop:
    def test_stop_nothing_playing(self):
        result = _action_stop()
        assert "no hay" in result.lower()

    def test_stop_active_process(self):
        import actions.radio_control as rc
        proc = MagicMock()
        proc.poll.return_value = None
        with rc._LOCK:
            rc._CURRENT_PROC = proc
            rc._CURRENT_STATION = "https://example.com"
            rc._CURRENT_NAME = "Test FM"
        result = _action_stop()
        assert "Test FM" in result
        proc.terminate.assert_called_once()


class TestActionStatus:
    def test_nothing_playing(self):
        result = _action_status()
        assert "no hay" in result.lower()

    def test_something_playing(self):
        import actions.radio_control as rc
        proc = MagicMock()
        proc.poll.return_value = None
        with rc._LOCK:
            rc._CURRENT_PROC = proc
            rc._CURRENT_STATION = "https://example.com"
            rc._CURRENT_NAME = "Radio Test"
        result = _action_status()
        assert "Radio Test" in result


class TestActionAdd:
    def test_add_no_key(self):
        result = _action_add("", "My Radio", "https://example.com")
        assert "especifica" in result.lower()

    def test_add_no_url(self):
        result = _action_add("myradio", "My Radio", "")
        assert "especifica" in result.lower()

    def test_add_bad_url(self):
        result = _action_add("myradio", "My Radio", "not_a_url")
        assert "http" in result.lower()

    def test_add_builtin_blocked(self):
        result = _action_add("radio1", "Override", "https://example.com")
        assert "integrada" in result.lower()

    def test_add_and_list(self, tmp_path):
        _action_add("mystation", "Mi Emisora", "https://example.com/stream")
        result = _action_list()
        assert "mystation" in result.lower()

    def test_add_persisted(self, tmp_path):
        _action_add("newstation", "Nueva", "https://new.example.com/stream.mp3")
        stations = _all_stations()
        assert "newstation" in stations
        assert stations["newstation"][1] == "https://new.example.com/stream.mp3"


class TestActionRemove:
    def test_remove_builtin(self):
        result = _action_remove("radio1")
        assert "integrada" in result.lower()

    def test_remove_nonexistent(self):
        result = _action_remove("ghost_station")
        assert "no encontré" in result.lower()

    def test_remove_custom(self, tmp_path):
        _action_add("toremove", "Remover", "https://example.com/r.mp3")
        result = _action_remove("toremove")
        assert "eliminada" in result.lower()
        assert "toremove" not in _all_stations()


class TestRadioControlEntryPoint:
    def test_unknown_action(self):
        result = radio_control({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_list_action(self):
        result = radio_control({"action": "list"})
        assert "radio1" in result.lower() or "rtve" in result.lower()

    def test_stop_nothing(self):
        result = radio_control({"action": "stop"})
        assert "no hay" in result.lower()

    def test_status_empty(self):
        result = radio_control({"action": "status"})
        assert "no hay" in result.lower()

    def test_none_params(self):
        result = radio_control(None)
        assert isinstance(result, str)

    def test_play_action(self):
        proc = MagicMock()
        with patch("actions.radio_control._find_ffplay", return_value="/usr/bin/ffplay"), \
             patch("subprocess.Popen", return_value=proc):
            result = radio_control({"action": "play", "station": "radio1"})
        assert isinstance(result, str)
        assert "radio" in result.lower() or "rtve" in result.lower()
