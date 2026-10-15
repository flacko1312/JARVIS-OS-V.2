"""Deterministic verification of the host date/time authority."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import main
from actions.reminder import _parse_natural_datetime
from core.date_time_authority import (
    DateTimeAuthority,
    localize_wall_time,
    normalize_timezone,
    relative_date,
)
from core.schedule_safety import daily_time_from_text
from lilith_client.config import LilithConfig
from router.core import JarvisRouter
from router.models import Domain
from runtime import JarvisRuntime


def _clock(value: str):
    instant = datetime.fromisoformat(value).astimezone(timezone.utc)
    return lambda: instant


def test_current_time_queries_use_frozen_host_clock():
    authority = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-01-15T13:05:00+00:00"))
    for query in ("¿Qué hora es?", "Dime la hora", "¿Qué hora tenemos?", "¿Qué hora es ahora?"):
        answer = authority.answer(query)
        assert answer == "Ahora son las 14:05 (CET, Europe/Madrid)."


def test_current_date_queries_use_local_calendar():
    authority = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-10-15T10:00:00+00:00"))
    assert authority.answer("¿Qué día es hoy?") == "Hoy es jueves, 15 de octubre de 2026."
    assert authority.answer("¿Qué fecha es?") == "Hoy es jueves, 15 de octubre de 2026."


def test_windows_timezone_and_cet_cest_aliases_normalize_to_madrid(monkeypatch):
    monkeypatch.delenv("JARVIS_TIMEZONE", raising=False)
    assert normalize_timezone(None, os_name="Windows", windows_name="Romance Standard Time") == "Europe/Madrid"
    assert normalize_timezone("Romance Standard Time") == "Europe/Madrid"
    assert normalize_timezone("CET") == "Europe/Madrid"
    assert normalize_timezone("CEST") == "Europe/Madrid"


def test_madrid_reports_cet_and_cest_at_frozen_instants():
    winter = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-01-15T12:00:00+00:00"))
    summer = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-07-15T12:00:00+00:00"))
    assert "13:00 (CET" in winter.format_time()
    assert "14:00 (CEST" in summer.format_time()


def test_dst_transition_rejects_nonexistent_and_duplicated_wall_times():
    missing, missing_error = localize_wall_time(date(2026, 3, 29), 2, 30, "Europe/Madrid")
    duplicated, duplicated_error = localize_wall_time(date(2026, 10, 25), 2, 30, "Europe/Madrid")
    assert missing is None and "no existe" in missing_error
    assert duplicated is None and "ocurre dos veces" in duplicated_error


def test_near_midnight_date_rollover_and_year_rollover_are_local():
    before = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-12-31T22:59:00+00:00"))
    after = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-12-31T23:01:00+00:00"))
    assert "31 de diciembre de 2026" in before.format_date()
    assert "1 de enero de 2027" in after.format_date()


def test_today_tomorrow_and_day_after_tomorrow_roll_over_year():
    reference = datetime(2026, 12, 31, 23, 55, tzinfo=timezone.utc)
    assert relative_date(reference, "hoy") == date(2026, 12, 31)
    assert relative_date(reference, "mañana") == date(2027, 1, 1)
    assert relative_date(reference, "pasado mañana") == date(2027, 1, 2)


def test_ten_at_night_is_2200_and_five_oclock_is_ambiguous():
    assert daily_time_from_text("a las 10 de la noche") == (22, 0)
    assert daily_time_from_text("a las 5") is None


def test_reminder_uses_same_authority_for_tomorrow_and_ambiguity():
    frozen = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
    target, error = _parse_natural_datetime(
        "recuérdame mañana a las 10 de la noche", timezone_name="Europe/Madrid", now=frozen,
    )
    assert error is None
    assert target.isoformat() == "2027-01-02T22:00:00+01:00"
    ambiguous, error = _parse_natural_datetime(
        "recuérdame mañana a las 5", timezone_name="Europe/Madrid", now=frozen,
    )
    assert ambiguous is None and "ambigua" in error


def test_routine_integration_uses_2200_and_central_timezone():
    call = SimpleNamespace(args={"action": "turn_on", "target": "bombilla", "timezone": "CET"})
    args = main._routine_args_from_wrong_call(
        "Todos los días a las 10 de la noche enciende la bombilla", call,
    )
    assert args is not None
    assert args["schedule"] == {"hour": 22, "minute": 0}
    assert args["timezone"] == "Europe/Madrid"


def test_router_and_runtime_handle_time_without_conversation_model():
    authority = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-01-15T13:05:00+00:00"))
    monitor = SimpleNamespace(status=SimpleNamespace(is_available=False))
    router = JarvisRouter(MagicMock(), monitor, date_time_authority=authority)
    classified = router.classify("¿Qué hora es?")
    assert classified.domain is Domain.DATE_TIME
    routed = asyncio.run(router.execute(classified))
    assert routed["message"] == "Ahora son las 14:05 (CET, Europe/Madrid)."

    runtime = JarvisRuntime(LilithConfig(base_url="http://127.0.0.1:9", api_key="test"))
    runtime._router._date_time = authority
    result = asyncio.run(runtime.process_input("¿Qué hora es?"))
    assert result["handled"] is True
    assert result["pass_to_conversation"] is False
    assert result["message"] == routed["message"]


def test_typed_live_time_is_injected_from_host_not_sent_as_guessing_prompt():
    authority = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-07-15T12:34:00+00:00"))

    class Session:
        def __init__(self):
            self.sent = []

        async def send_client_content(self, *, turns, turn_complete):
            self.sent.append(turns["parts"][0]["text"])

    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.session = Session()
    jarvis._date_time_authority = authority
    jarvis._pending_self_quit = False
    jarvis._begin_schedule_turn = lambda *_: None
    jarvis._remember_conversation_text = lambda *_: None
    jarvis._last_input_transcript = ""
    jarvis._last_input_transcript_at = 0.0
    jarvis._is_explicit_self_quit_transcript = lambda _text: False
    jarvis._offer_typed_to_lilith = MagicMock(side_effect=AssertionError("must bypass LILITH/LLM routing"))

    assert asyncio.run(jarvis.send_text("¿Qué hora es?")) is True
    assert len(jarvis.session.sent) == 1
    sent = jarvis.session.sent[0]
    assert "14:34 (CEST, Europe/Madrid)" in sent
    assert "No calcules ni adivines" in sent
    assert "¿Qué hora es?" not in sent


def test_live_tool_contract_returns_authoritative_host_value():
    authority = DateTimeAuthority(timezone_name="Europe/Madrid", clock=_clock("2026-01-15T13:05:00+00:00"))
    assert authority.answer_action("current_time") == "Ahora son las 14:05 (CET, Europe/Madrid)."
    assert authority.answer_action("current_date") == "Hoy es jueves, 15 de enero de 2026."
