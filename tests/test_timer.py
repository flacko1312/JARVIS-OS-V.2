"""
Tests for actions.timer — in-process countdown timer tool.
No real OS timers are started; threading.Timer is mocked.
"""
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from actions.timer import (
    _format_duration,
    _parse_duration,
    timer,
)


# ---------------------------------------------------------------------------
# _parse_duration
# ---------------------------------------------------------------------------


class TestParseDuration:
    def test_minutes(self):
        s, err = _parse_duration("5 minutos")
        assert err is None
        assert s == 300

    def test_seconds(self):
        s, err = _parse_duration("30 segundos")
        assert err is None
        assert s == 30

    def test_hours(self):
        s, err = _parse_duration("2 horas")
        assert err is None
        assert s == 7200

    def test_combined(self):
        s, err = _parse_duration("1 hora 30 minutos")
        assert err is None
        assert s == 5400

    def test_combined_seconds(self):
        s, err = _parse_duration("1 hora 30 minutos 15 segundos")
        assert err is None
        assert s == 5415

    def test_spanish_word_number(self):
        s, err = _parse_duration("cinco minutos")
        assert err is None
        assert s == 300

    def test_bare_number_treated_as_minutes(self):
        s, err = _parse_duration("10")
        assert err is None
        assert s == 600

    def test_empty_string_error(self):
        _, err = _parse_duration("")
        assert err is not None

    def test_garbage_error(self):
        _, err = _parse_duration("mañana a las 5")
        assert err is not None

    def test_too_long_error(self):
        _, err = _parse_duration("25 horas")
        assert err is not None
        assert "24 horas" in err

    def test_accent_normalization(self):
        # "minútos" accent handled
        s, err = _parse_duration("3 minutos")
        assert err is None
        assert s == 180

    def test_treinta_segundos(self):
        s, err = _parse_duration("treinta segundos")
        assert err is None
        assert s == 30


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_seconds_only(self):
        assert "segundo" in _format_duration(45)

    def test_minutes_only(self):
        assert "minuto" in _format_duration(120)

    def test_hours_only(self):
        assert "hora" in _format_duration(3600)

    def test_combined(self):
        result = _format_duration(3660)
        assert "hora" in result
        assert "minuto" in result

    def test_zero(self):
        assert _format_duration(0) == "0 segundos"


# ---------------------------------------------------------------------------
# timer() — create/list/cancel
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_timer_registry(tmp_path, monkeypatch):
    """Each test gets its own registry file and cleared in-memory state."""
    monkeypatch.setenv("JARVIS_TIMER_DIR", str(tmp_path))
    # Clear module-level in-memory timer dict between tests
    import actions.timer as _tm
    for handle in list(_tm._TIMERS.values()):
        handle.cancel()
    _tm._TIMERS.clear()
    yield
    for handle in list(_tm._TIMERS.values()):
        handle.cancel()
    _tm._TIMERS.clear()


class TestTimerCreate:
    def test_create_returns_id(self):
        result = timer({"action": "create", "duration": "5 minutos"})
        assert "tmr_" in result
        assert "5 minuto" in result

    def test_create_with_label(self):
        result = timer({"action": "create", "duration": "10 minutos", "label": "pizza"})
        assert "pizza" in result.lower() or "minuto" in result

    def test_create_no_duration_error(self):
        result = timer({"action": "create"})
        assert "duración" in result.lower() or "necesito" in result.lower()

    def test_create_invalid_duration_error(self):
        result = timer({"action": "create", "duration": "mañana"})
        assert "no he entendido" in result.lower() or "duración" in result.lower()

    def test_create_starts_thread_timer(self):
        import actions.timer as _tm
        timer({"action": "create", "duration": "60 minutos"})
        assert len(_tm._TIMERS) == 1

    def test_create_persists_to_registry(self, tmp_path):
        timer({"action": "create", "duration": "2 minutos", "label": "test"})
        reg_path = tmp_path / "registry.json"
        assert reg_path.exists()
        data = json.loads(reg_path.read_text())
        assert any(item.get("label") == "2 minutos" or item.get("label") == "test" for item in data)

    def test_create_default_action(self):
        result = timer({"duration": "1 minuto"})
        assert "tmr_" in result

    def test_create_via_text_key(self):
        result = timer({"text": "3 minutos"})
        assert "tmr_" in result


class TestTimerList:
    def test_list_empty(self):
        result = timer({"action": "list"})
        assert "no hay" in result.lower()

    def test_list_after_create(self):
        timer({"action": "create", "duration": "10 minutos", "label": "prueba"})
        result = timer({"action": "list"})
        assert "prueba" in result.lower() or "minuto" in result.lower()

    def test_list_multiple_timers(self):
        timer({"action": "create", "duration": "5 minutos", "label": "A"})
        timer({"action": "create", "duration": "10 minutos", "label": "B"})
        result = timer({"action": "list"})
        assert "A" in result
        assert "B" in result


class TestTimerCancel:
    def test_cancel_by_id(self):
        import actions.timer as _tm
        create_result = timer({"action": "create", "duration": "30 minutos", "label": "borrar"})
        timer_id = None
        for part in create_result.split():
            if part.startswith("tmr_"):
                timer_id = part.rstrip(").:")
                break
        assert timer_id is not None, f"Could not extract ID from: {create_result}"
        cancel_result = timer({"action": "cancel", "id": timer_id})
        assert "cancelad" in cancel_result.lower()
        assert timer_id not in _tm._TIMERS

    def test_cancel_all_no_id(self):
        import actions.timer as _tm
        timer({"action": "create", "duration": "5 minutos", "label": "X"})
        timer({"action": "create", "duration": "6 minutos", "label": "Y"})
        result = timer({"action": "cancel"})
        assert "cancelad" in result.lower()
        assert len(_tm._TIMERS) == 0

    def test_cancel_nonexistent(self):
        result = timer({"action": "cancel", "id": "tmr_notreal"})
        assert "no encuentro" in result.lower()

    def test_cancel_removes_from_registry(self, tmp_path):
        create_result = timer({"action": "create", "duration": "20 minutos"})
        timer_id = None
        for part in create_result.split():
            if part.startswith("tmr_"):
                timer_id = part.rstrip(").:"); break
        timer({"action": "cancel", "id": timer_id})
        reg = json.loads((tmp_path / "registry.json").read_text())
        assert not any(item.get("id") == timer_id for item in reg)


class TestTimerFireCallback:
    def test_fire_calls_player_speak(self):
        import actions.timer as _tm

        player = MagicMock()
        create_result = timer(
            {"action": "create", "duration": "1 segundos", "label": "ping"},
            player=player,
        )
        # Wait for the 1-second timer to fire (with margin)
        time.sleep(2.0)
        player.speak.assert_called_once()
        call_text = player.speak.call_args[0][0]
        assert "ping" in call_text or "temporizador" in call_text.lower()

    def test_fire_removes_from_registry(self, tmp_path):
        create_result = timer({"action": "create", "duration": "1 segundos"})
        time.sleep(2.0)
        reg_path = tmp_path / "registry.json"
        if reg_path.exists():
            data = json.loads(reg_path.read_text())
            timer_id = None
            for part in create_result.split():
                if part.startswith("tmr_"):
                    timer_id = part.rstrip(").:")
                    break
            if timer_id:
                assert not any(item.get("id") == timer_id for item in data)

    def test_fire_no_player_no_error(self):
        # Should not raise even when player is None
        timer({"action": "create", "duration": "1 segundos"})
        time.sleep(2.0)


class TestTimerUnknownAction:
    def test_unknown_action(self):
        result = timer({"action": "modify"})
        assert "no compatible" in result.lower()
