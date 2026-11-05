"""Tests for actions.alarm_control — time-based alarm scheduling."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from actions.alarm_control import (
    _action_cancel,
    _action_list,
    _action_set,
    _action_status,
    _fmt_delay,
    _parse_time_str,
    alarm_control,
)


@pytest.fixture(autouse=True)
def isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ALARMS_DIR", str(tmp_path))
    yield
    # Cancel any timers created in tests
    import actions.alarm_control as ac
    with ac._LOCK:
        for h in list(ac._ALARMS.values()):
            h.cancel()
        ac._ALARMS.clear()


# ---------------------------------------------------------------------------
# TestParseTimeStr


class TestParseTimeStr:
    def test_hhmm(self):
        future = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
        result = _parse_time_str(future)
        assert result is not None
        assert result > datetime.now()

    def test_midnight_pushes_to_tomorrow(self):
        # 00:01 is almost certainly in the past today
        result = _parse_time_str("00:01")
        assert result is not None
        assert result > datetime.now()

    def test_manana(self):
        result = _parse_time_str("mañana 8:00")
        assert result is not None
        tomorrow = datetime.now() + timedelta(days=1)
        assert result.date() == tomorrow.date()

    def test_am_pm(self):
        result = _parse_time_str("9 AM")
        assert result is not None

    def test_hh_format(self):
        result = _parse_time_str("8h30")
        assert result is not None

    def test_invalid(self):
        result = _parse_time_str("ahora mismo")
        assert result is None

    def test_hour_25_invalid(self):
        result = _parse_time_str("25:00")
        assert result is None


# ---------------------------------------------------------------------------
# TestFmtDelay


class TestFmtDelay:
    def test_seconds(self):
        assert "s" in _fmt_delay(45)

    def test_minutes(self):
        assert "m" in _fmt_delay(130)

    def test_hours(self):
        assert "h" in _fmt_delay(3700)


# ---------------------------------------------------------------------------
# TestActionSet


class TestActionSet:
    def test_no_time(self):
        result = _action_set("")
        assert "especifica" in result.lower()

    def test_invalid_time(self):
        result = _action_set("mediodía exacto")
        assert "no entendí" in result.lower()

    def test_set_future_alarm(self):
        future = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
        result = _action_set(future, label="Despertador test")
        assert "alarma" in result.lower()
        assert "Despertador test" in result

    def test_set_manana(self):
        result = _action_set("mañana 7:00", label="Mañana temprano")
        assert "mañana" in result.lower()

    def test_timer_created(self):
        import actions.alarm_control as ac
        future = (datetime.now() + timedelta(hours=3)).strftime("%H:%M")
        _action_set(future)
        with ac._LOCK:
            count = len(ac._ALARMS)
        assert count >= 1

    def test_persisted(self, tmp_path):
        future = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
        _action_set(future, label="PersistTest")
        from actions.alarm_control import _load_registry
        items = _load_registry()
        assert any("PersistTest" in i.get("label", "") for i in items)


# ---------------------------------------------------------------------------
# TestActionList


class TestActionList:
    def test_empty(self):
        result = _action_list()
        assert "no hay" in result.lower()

    def test_shows_alarm(self):
        future = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
        _action_set(future, label="ListTest")
        result = _action_list()
        assert "ListTest" in result


# ---------------------------------------------------------------------------
# TestActionCancel


class TestActionCancel:
    def test_cancel_nonexistent(self):
        result = _action_cancel(alarm_id="nonexistent")
        assert "no se encontró" in result.lower()

    def test_cancel_by_id(self):
        import actions.alarm_control as ac
        future = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
        _action_set(future, label="CancelTest")
        with ac._LOCK:
            alarm_id = list(ac._ALARMS.keys())[0]
        result = _action_cancel(alarm_id=alarm_id)
        assert alarm_id in result
        with ac._LOCK:
            assert alarm_id not in ac._ALARMS

    def test_cancel_all(self):
        import actions.alarm_control as ac
        for h in [2, 3, 4]:
            future = (datetime.now() + timedelta(hours=h)).strftime("%H:%M")
            _action_set(future)
        result = _action_cancel()
        with ac._LOCK:
            assert len(ac._ALARMS) == 0


# ---------------------------------------------------------------------------
# TestActionStatus


class TestActionStatus:
    def test_no_alarms(self):
        result = _action_status()
        assert "no hay" in result.lower()

    def test_with_alarm(self):
        future = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
        _action_set(future)
        result = _action_status()
        assert "alarma" in result.lower()


# ---------------------------------------------------------------------------
# TestEntryPoint


class TestAlarmControlEntryPoint:
    def test_none_params_returns_list(self):
        result = alarm_control(None)
        assert isinstance(result, str)

    def test_set_action(self):
        future = (datetime.now() + timedelta(hours=5)).strftime("%H:%M")
        result = alarm_control({"action": "set", "time": future, "label": "Test"})
        assert "Test" in result

    def test_list_action(self):
        result = alarm_control({"action": "list"})
        assert isinstance(result, str)

    def test_cancel_action(self):
        result = alarm_control({"action": "cancel"})
        assert isinstance(result, str)

    def test_status_action(self):
        result = alarm_control({"action": "status"})
        assert isinstance(result, str)

    def test_unknown_action(self):
        result = alarm_control({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_hora_alias(self):
        future = (datetime.now() + timedelta(hours=6)).strftime("%H:%M")
        result = alarm_control({"action": "set", "hora": future})
        assert isinstance(result, str)

    def test_crear_alias(self):
        future = (datetime.now() + timedelta(hours=4)).strftime("%H:%M")
        result = alarm_control({"action": "crear", "time": future})
        assert "alarma" in result.lower()
