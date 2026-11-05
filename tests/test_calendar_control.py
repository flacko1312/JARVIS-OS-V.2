"""
Tests for actions.calendar_control — Google Calendar integration.
All Google API calls are mocked; no network or OAuth flow is exercised.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from actions.calendar_control import (
    _action_create,
    _action_delete,
    _action_list,
    _action_search,
    _action_status,
    _action_today,
    _clear_credentials,
    _do_connect,
    _fmt_event,
    _valid_client_file,
    calendar_control,
    CalendarConnectionError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    """Wipe module-level credential cache between tests."""
    import actions.calendar_control as cc
    monkeypatch.setattr(cc, "_CREDENTIALS_CACHE", "")
    _clear_credentials.__wrapped__ = None  # allow repeated calls
    yield
    import actions.calendar_control as cc2
    cc2._CREDENTIALS_CACHE = ""
    cc2._TENANT_CREDENTIALS.clear()


def _make_creds(valid=True, expired=False, refresh_token="rt"):
    creds = MagicMock()
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = refresh_token
    creds.expiry = "2099-01-01T00:00:00"
    creds.to_json.return_value = json.dumps({"token": "fake", "refresh_token": refresh_token})
    return creds


def _make_service(events=None):
    service = MagicMock()
    items = events if events is not None else []
    service.events.return_value.list.return_value.execute.return_value = {"items": items}
    service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt_abc123",
        "summary": "Test event",
    }
    service.events.return_value.delete.return_value.execute.return_value = {}
    return service


def _fake_event(summary="Reunión", start="2026-11-10T10:00:00+01:00", event_id="evt_1"):
    return {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": "2026-11-10T11:00:00+01:00"},
        "id": event_id,
    }


# ---------------------------------------------------------------------------
# _valid_client_file
# ---------------------------------------------------------------------------

class TestValidClientFile:
    def test_valid_installed_credentials(self, tmp_path):
        creds_file = tmp_path / "creds.json"
        creds_file.write_text(json.dumps({
            "installed": {
                "client_id": "id.apps.googleusercontent.com",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }), encoding="utf-8")
        assert _valid_client_file(creds_file) is True

    def test_missing_client_id(self, tmp_path):
        creds_file = tmp_path / "bad.json"
        creds_file.write_text(json.dumps({"installed": {"auth_uri": "x", "token_uri": "y"}}), encoding="utf-8")
        assert _valid_client_file(creds_file) is False

    def test_not_installed_type(self, tmp_path):
        creds_file = tmp_path / "web.json"
        creds_file.write_text(json.dumps({"web": {"client_id": "id", "auth_uri": "x", "token_uri": "y"}}), encoding="utf-8")
        assert _valid_client_file(creds_file) is False

    def test_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        assert _valid_client_file(bad) is False

    def test_nonexistent_file(self, tmp_path):
        assert _valid_client_file(tmp_path / "ghost.json") is False


# ---------------------------------------------------------------------------
# _fmt_event
# ---------------------------------------------------------------------------

class TestFmtEvent:
    def test_basic_event(self):
        result = _fmt_event(_fake_event("Junta de equipo"))
        assert "Junta de equipo" in result
        assert "evt_1" in result

    def test_all_day_event(self):
        event = {"summary": "Festivo", "start": {"date": "2026-12-25"}, "end": {"date": "2026-12-26"}, "id": "festivo_1"}
        result = _fmt_event(event)
        assert "Festivo" in result
        assert "2026-12-25" in result

    def test_missing_summary(self):
        event = {"start": {"dateTime": "2026-11-10T09:00:00+01:00"}, "end": {"dateTime": "2026-11-10T10:00:00+01:00"}, "id": "x"}
        result = _fmt_event(event)
        assert "Sin título" in result

    def test_location_included(self):
        event = _fake_event()
        event["location"] = "Oficina Madrid"
        result = _fmt_event(event)
        assert "Oficina Madrid" in result


# ---------------------------------------------------------------------------
# _action_status
# ---------------------------------------------------------------------------

class TestActionStatus:
    def test_connected(self):
        creds = _make_creds()
        with patch("actions.calendar_control._load_credentials", return_value=creds):
            result = _action_status()
        assert "conectado" in result.lower()

    def test_not_connected(self):
        with patch("actions.calendar_control._load_credentials",
                   side_effect=CalendarConnectionError("no conectado")):
            result = _action_status()
        assert "no conectado" in result.lower()


# ---------------------------------------------------------------------------
# _action_list
# ---------------------------------------------------------------------------

class TestActionList:
    def test_no_events(self):
        with patch("actions.calendar_control._calendar_service", return_value=_make_service([])):
            result = _action_list(days=7)
        assert "no tienes eventos" in result.lower()

    def test_with_events(self):
        events = [_fake_event("Reunión semanal"), _fake_event("Demo", event_id="evt_2")]
        with patch("actions.calendar_control._calendar_service", return_value=_make_service(events)):
            result = _action_list(days=7)
        assert "Reunión semanal" in result
        assert "Demo" in result

    def test_days_parameter(self):
        with patch("actions.calendar_control._calendar_service") as mock_svc:
            svc = _make_service([])
            mock_svc.return_value = svc
            _action_list(days=14)
        call_kwargs = svc.events.return_value.list.call_args.kwargs
        assert call_kwargs.get("maxResults") == 20

    def test_service_error(self):
        svc = MagicMock()
        svc.events.return_value.list.return_value.execute.side_effect = Exception("API error")
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            with pytest.raises(CalendarConnectionError, match="API error"):
                _action_list()


# ---------------------------------------------------------------------------
# _action_today
# ---------------------------------------------------------------------------

class TestActionToday:
    def test_no_events_today(self):
        with patch("actions.calendar_control._calendar_service", return_value=_make_service([])):
            result = _action_today()
        assert "no tienes eventos" in result.lower()

    def test_events_today(self):
        events = [_fake_event("Stand-up"), _fake_event("1:1 con jefa", event_id="evt_11")]
        with patch("actions.calendar_control._calendar_service", return_value=_make_service(events)):
            result = _action_today()
        assert "Stand-up" in result
        assert "1:1 con jefa" in result


# ---------------------------------------------------------------------------
# _action_search
# ---------------------------------------------------------------------------

class TestActionSearch:
    def test_empty_query(self):
        result = _action_search(query="")
        assert "especifica" in result.lower()

    def test_no_results(self):
        with patch("actions.calendar_control._calendar_service", return_value=_make_service([])):
            result = _action_search(query="dentista")
        assert "dentista" in result
        assert "no encontré" in result.lower()

    def test_found_results(self):
        events = [_fake_event("Dentista")]
        with patch("actions.calendar_control._calendar_service", return_value=_make_service(events)):
            result = _action_search(query="dentista")
        assert "Dentista" in result

    def test_query_forwarded_to_api(self):
        svc = _make_service([])
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            _action_search(query="reunión")
        call_kwargs = svc.events.return_value.list.call_args.kwargs
        assert call_kwargs.get("q") == "reunión"


# ---------------------------------------------------------------------------
# _action_create
# ---------------------------------------------------------------------------

class TestActionCreate:
    def test_no_title(self):
        result = _action_create(title="")
        assert "título" in result.lower()

    def test_basic_create(self):
        svc = _make_service()
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            result = _action_create(title="Junta importante", date="2026-11-10", start_time="10:00")
        assert "Junta importante" in result
        assert "evt_abc123" in result

    def test_create_with_location(self):
        svc = _make_service()
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            result = _action_create(title="Comida", date="2026-11-10", start_time="13:00", location="Restaurante X")
        assert "Restaurante X" in result

    def test_invalid_date(self):
        result = _action_create(title="Evento", date="10-11-2026")
        assert "formato" in result.lower()

    def test_invalid_start_time(self):
        result = _action_create(title="Evento", date="2026-11-10", start_time="10:00 AM")
        assert "formato" in result.lower()

    def test_duration_minutes(self):
        svc = _make_service()
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            _action_create(title="Reunión", date="2026-11-10", start_time="09:00", duration_minutes=30)
        body = svc.events.return_value.insert.call_args.kwargs.get("body", {})
        # end time should be 09:30
        assert "09:30" in body.get("end", {}).get("dateTime", "")

    def test_api_error(self):
        svc = MagicMock()
        svc.events.return_value.insert.return_value.execute.side_effect = Exception("quota")
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            with pytest.raises(CalendarConnectionError, match="quota"):
                _action_create(title="Test", date="2026-11-10", start_time="10:00")


# ---------------------------------------------------------------------------
# _action_delete
# ---------------------------------------------------------------------------

class TestActionDelete:
    def test_no_event_id(self):
        result = _action_delete(event_id="")
        assert "id" in result.lower()

    def test_delete_ok(self):
        svc = _make_service()
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            result = _action_delete(event_id="evt_abc123")
        assert "eliminado" in result.lower()
        assert "evt_abc123" in result

    def test_delete_api_error(self):
        svc = MagicMock()
        svc.events.return_value.delete.return_value.execute.side_effect = Exception("not found")
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            with pytest.raises(CalendarConnectionError, match="not found"):
                _action_delete(event_id="bad_id")


# ---------------------------------------------------------------------------
# calendar_control() entry point
# ---------------------------------------------------------------------------

class TestCalendarControlEntryPoint:
    def test_unknown_action(self):
        result = calendar_control({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_status_action(self):
        creds = _make_creds()
        with patch("actions.calendar_control._load_credentials", return_value=creds):
            result = calendar_control({"action": "status"})
        assert "conectado" in result.lower()

    def test_list_default_action(self):
        with patch("actions.calendar_control._calendar_service", return_value=_make_service([])):
            result = calendar_control({})
        assert "no tienes" in result.lower()

    def test_today_action(self):
        events = [_fake_event("Morning standup")]
        with patch("actions.calendar_control._calendar_service", return_value=_make_service(events)):
            result = calendar_control({"action": "today"})
        assert "Morning standup" in result

    def test_connection_error_returned_as_string(self):
        with patch("actions.calendar_control._load_credentials",
                   side_effect=CalendarConnectionError("No configurado")):
            result = calendar_control({"action": "status"})
        assert "No configurado" in result

    def test_disconnect_clears_cache(self):
        import actions.calendar_control as cc
        cc._CREDENTIALS_CACHE = json.dumps({"token": "x"})
        result = calendar_control({"action": "disconnect"})
        assert "desconectado" in result.lower()
        assert cc._CREDENTIALS_CACHE == ""

    def test_none_parameters(self):
        with patch("actions.calendar_control._calendar_service", return_value=_make_service([])):
            result = calendar_control(None)
        assert isinstance(result, str)

    def test_connect_no_file_returns_message(self):
        Request = MagicMock()
        Credentials = MagicMock()
        InstalledAppFlow = MagicMock()
        build = MagicMock()
        with patch("actions.calendar_control._calendar_dependencies", return_value=(Request, Credentials, InstalledAppFlow, build)), \
             patch("actions.calendar_control._discover_client_path", return_value=None):
            result = calendar_control({"action": "connect"})
        assert "credenciales" in result.lower()

    def test_create_action(self):
        svc = _make_service()
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            result = calendar_control({
                "action": "create",
                "title": "Revisión código",
                "date": "2026-11-10",
                "start_time": "15:00",
            })
        assert "Revisión código" in result

    def test_search_action(self):
        events = [_fake_event("Curso Python")]
        with patch("actions.calendar_control._calendar_service", return_value=_make_service(events)):
            result = calendar_control({"action": "search", "query": "Python"})
        assert "Curso Python" in result

    def test_delete_action(self):
        svc = _make_service()
        with patch("actions.calendar_control._calendar_service", return_value=svc):
            result = calendar_control({"action": "delete", "event_id": "evt_xyz"})
        assert "eliminado" in result.lower()
