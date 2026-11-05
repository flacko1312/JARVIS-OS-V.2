"""
Tests for actions.traffic_info — routing and traffic info tool.
All HTTP calls are mocked; no network access required.
'requests' may not be installed in the test environment — it is imported lazily
inside functions so we patch it at sys.modules level for tests that exercise
the HTTP paths.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# Provide a lightweight requests stub if not installed so imports succeed.
if "requests" not in sys.modules:
    _requests_stub = MagicMock()
    sys.modules["requests"] = _requests_stub

from actions.traffic_info import (
    _action_addresses,
    _action_commute,
    _action_route,
    _action_setup,
    _action_status,
    _fmt_distance,
    _fmt_duration,
    _geocode,
    _get_ors_key,
    _no_key_message,
    _ors_route,
    traffic_info,
    TrafficError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_caches(monkeypatch):
    """Clear module-level caches and env overrides between tests."""
    import actions.traffic_info as ti
    monkeypatch.setattr(ti, "_API_CACHE", {})
    monkeypatch.delenv("ORS_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_HOME_ADDRESS", raising=False)
    monkeypatch.delenv("JARVIS_WORK_ADDRESS", raising=False)
    # Stub secret_store to avoid keychain calls
    store = MagicMock()
    store.get.return_value = ""
    store.set.return_value = None
    monkeypatch.setattr("actions.traffic_info._secret_store", lambda: store)
    yield
    import actions.traffic_info as ti2
    ti2._API_CACHE.clear()


def _make_geocode(lon=3.7, lat=40.4):
    return (lon, lat)


def _make_ors_response(distance_m=15000.0, duration_s=1200.0):
    return {"distance_m": distance_m, "duration_s": duration_s}


# ---------------------------------------------------------------------------
# _fmt_duration
# ---------------------------------------------------------------------------

class TestFmtDuration:
    def test_under_60_minutes(self):
        assert _fmt_duration(600) == "10 min"

    def test_exactly_1_hour(self):
        assert _fmt_duration(3600) == "1 h"

    def test_hours_and_minutes(self):
        assert _fmt_duration(5400) == "1 h 30 min"

    def test_zero(self):
        assert _fmt_duration(0) == "0 min"

    def test_rounding(self):
        result = _fmt_duration(70)  # 70s → 1 min
        assert "1 min" in result


# ---------------------------------------------------------------------------
# _fmt_distance
# ---------------------------------------------------------------------------

class TestFmtDistance:
    def test_under_1km(self):
        assert "500 m" == _fmt_distance(500)

    def test_over_1km(self):
        assert "15.0 km" == _fmt_distance(15000)

    def test_exactly_1km(self):
        assert "1.0 km" == _fmt_distance(1000)


# ---------------------------------------------------------------------------
# _geocode
# ---------------------------------------------------------------------------

class TestGeocode:
    def _mock_response(self, lon, lat):
        resp = MagicMock()
        resp.json.return_value = [{"lon": str(lon), "lat": str(lat), "display_name": "Madrid, Spain"}]
        resp.raise_for_status.return_value = None
        return resp

    def test_returns_coordinates(self):
        with patch("requests.get", return_value=self._mock_response(3.7, 40.4)):
            lon, lat = _geocode("Madrid, Spain")
        assert lon == pytest.approx(3.7)
        assert lat == pytest.approx(40.4)

    def test_no_results_raises(self):
        resp = MagicMock()
        resp.json.return_value = []
        resp.raise_for_status.return_value = None
        with patch("requests.get", return_value=resp):
            with pytest.raises(TrafficError, match="No encontré"):
                _geocode("Lugar inexistente xyzabc123")

    def test_network_error_raises(self):
        with patch("requests.get", side_effect=Exception("timeout")):
            with pytest.raises(TrafficError, match="timeout"):
                _geocode("Madrid")


# ---------------------------------------------------------------------------
# _ors_route
# ---------------------------------------------------------------------------

class TestOrsRoute:
    def _make_resp(self, status=200, body=None):
        resp = MagicMock()
        resp.status_code = status
        if body is None:
            body = {"routes": [{"summary": {"distance": 15000.0, "duration": 1200.0}}]}
        resp.json.return_value = body
        if status == 200:
            resp.raise_for_status.return_value = None
        else:
            resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
        return resp

    def test_returns_summary(self):
        with patch("requests.post", return_value=self._make_resp()):
            result = _ors_route((3.7, 40.4), (-3.7, 40.4), api_key="test_key")
        assert result["distance_m"] == pytest.approx(15000.0)
        assert result["duration_s"] == pytest.approx(1200.0)

    def test_403_raises_invalid_key(self):
        resp = self._make_resp(403)
        with patch("requests.post", return_value=resp):
            with pytest.raises(TrafficError, match="válida"):
                _ors_route((0.0, 0.0), (1.0, 1.0), api_key="bad")

    def test_404_raises_no_route(self):
        resp = self._make_resp(404)
        with patch("requests.post", return_value=resp):
            with pytest.raises(TrafficError, match="ruta"):
                _ors_route((0.0, 0.0), (1.0, 1.0), api_key="key")

    def test_network_error(self):
        with patch("requests.post", side_effect=Exception("refused")):
            with pytest.raises(TrafficError, match="refused"):
                _ors_route((0.0, 0.0), (1.0, 1.0), api_key="key")


# ---------------------------------------------------------------------------
# _action_status
# ---------------------------------------------------------------------------

class TestActionStatus:
    def test_no_key_no_addresses(self):
        result = _action_status()
        assert "NO configurado" in result

    def test_key_configured(self, monkeypatch):
        monkeypatch.setenv("ORS_API_KEY", "mykey1234")
        result = _action_status()
        assert "1234" in result

    def test_addresses_shown(self, monkeypatch):
        monkeypatch.setenv("JARVIS_HOME_ADDRESS", "Calle Mayor, Madrid")
        monkeypatch.setenv("JARVIS_WORK_ADDRESS", "Gran Vía, Madrid")
        result = _action_status()
        assert "Calle Mayor" in result
        assert "Gran Vía" in result


# ---------------------------------------------------------------------------
# _action_setup
# ---------------------------------------------------------------------------

class TestActionSetup:
    def test_no_args_returns_guidance(self):
        result = _action_setup()
        assert "especifica" in result.lower()

    def test_save_home(self):
        result = _action_setup(home="Calle Falsa 123, Madrid")
        assert "Calle Falsa 123" in result
        assert "guardada" in result.lower()

    def test_save_work(self):
        result = _action_setup(work="Paseo de la Castellana 1")
        assert "Paseo de la Castellana" in result

    def test_save_api_key(self):
        result = _action_setup(api_key="mykey5678")
        assert "5678" in result
        assert "guardada" in result.lower()

    def test_save_all(self):
        result = _action_setup(home="Casa", work="Oficina", api_key="key9999")
        assert "Casa" in result
        assert "Oficina" in result
        assert "9999" in result


# ---------------------------------------------------------------------------
# _action_addresses
# ---------------------------------------------------------------------------

class TestActionAddresses:
    def test_no_addresses(self):
        result = _action_addresses()
        assert "no guardada" in result.lower()

    def test_home_set(self, monkeypatch):
        monkeypatch.setenv("JARVIS_HOME_ADDRESS", "Mi casa, 28001 Madrid")
        result = _action_addresses()
        assert "Mi casa" in result

    def test_work_set(self, monkeypatch):
        monkeypatch.setenv("JARVIS_WORK_ADDRESS", "Oficina, Madrid")
        result = _action_addresses()
        assert "Oficina" in result


# ---------------------------------------------------------------------------
# _action_route
# ---------------------------------------------------------------------------

class TestActionRoute:
    def test_no_origin(self):
        result = _action_route(origin="", destination="Barcelona")
        assert "origen" in result.lower() or "destino" in result.lower()

    def test_no_destination(self):
        result = _action_route(origin="Madrid", destination="")
        assert "destino" in result.lower() or "origen" in result.lower()

    def test_no_api_key_returns_setup_msg(self):
        result = _action_route(origin="Madrid", destination="Barcelona")
        assert "openrouteservice" in result.lower()

    def test_route_ok(self, monkeypatch):
        monkeypatch.setenv("ORS_API_KEY", "testkey")
        with patch("actions.traffic_info._geocode", side_effect=[(3.7, 40.4), (-2.1, 41.6)]):
            with patch("actions.traffic_info._ors_route", return_value=_make_ors_response(600000, 14400)):
                result = _action_route(origin="Madrid", destination="Barcelona")
        assert "Madrid" in result
        assert "Barcelona" in result
        assert "km" in result or "h" in result

    def test_geocode_error_propagated(self, monkeypatch):
        monkeypatch.setenv("ORS_API_KEY", "testkey")
        with patch("actions.traffic_info._geocode", side_effect=TrafficError("no encontré")):
            # _action_route re-raises TrafficError; use entry-point to get string
            result = traffic_info({"action": "route", "origin": "Narnia", "destination": "Hogwarts"})
        assert "no encontré" in result.lower()


# ---------------------------------------------------------------------------
# _action_commute
# ---------------------------------------------------------------------------

class TestActionCommute:
    def test_no_home(self):
        result = _action_commute("to_work")
        assert "casa" in result.lower()

    def test_no_work(self, monkeypatch):
        monkeypatch.setenv("JARVIS_HOME_ADDRESS", "Casa")
        result = _action_commute("to_work")
        assert "trabajo" in result.lower()

    def test_to_work(self, monkeypatch):
        monkeypatch.setenv("JARVIS_HOME_ADDRESS", "Casa, Madrid")
        monkeypatch.setenv("JARVIS_WORK_ADDRESS", "Trabajo, Madrid")
        monkeypatch.setenv("ORS_API_KEY", "k")
        with patch("actions.traffic_info._geocode", side_effect=[(3.7, 40.4), (3.8, 40.5)]):
            with patch("actions.traffic_info._ors_route", return_value=_make_ors_response(5000, 600)):
                result = _action_commute("to_work")
        assert "Casa" in result or "Trabajo" in result

    def test_to_home(self, monkeypatch):
        monkeypatch.setenv("JARVIS_HOME_ADDRESS", "Casa, Madrid")
        monkeypatch.setenv("JARVIS_WORK_ADDRESS", "Trabajo, Madrid")
        monkeypatch.setenv("ORS_API_KEY", "k")
        with patch("actions.traffic_info._geocode", side_effect=[(3.8, 40.5), (3.7, 40.4)]):
            with patch("actions.traffic_info._ors_route", return_value=_make_ors_response(5000, 600)):
                result = _action_commute("to_home")
        assert "km" in result or "min" in result


# ---------------------------------------------------------------------------
# traffic_info() entry point
# ---------------------------------------------------------------------------

class TestTrafficInfoEntryPoint:
    def test_unknown_action(self):
        result = traffic_info({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_status_action(self):
        result = traffic_info({"action": "status"})
        assert isinstance(result, str)
        assert "openrouteservice" in result.lower() or "configurado" in result.lower()

    def test_addresses_action(self):
        result = traffic_info({"action": "addresses"})
        assert "casa" in result.lower()

    def test_setup_action(self):
        result = traffic_info({"action": "setup", "home": "Mi barrio, Madrid"})
        assert "Mi barrio" in result

    def test_route_no_key(self):
        result = traffic_info({"action": "route", "origin": "Madrid", "destination": "Sevilla"})
        assert "openrouteservice" in result.lower()

    def test_commute_no_addresses(self):
        result = traffic_info({"action": "commute"})
        assert "casa" in result.lower()

    def test_none_params(self):
        result = traffic_info(None)
        assert isinstance(result, str)

    def test_traffic_error_returned_as_string(self):
        with patch("actions.traffic_info._action_status", side_effect=TrafficError("API caída")):
            result = traffic_info({"action": "status"})
        assert "API caída" in result

    def test_from_to_aliases(self, monkeypatch):
        monkeypatch.setenv("ORS_API_KEY", "k")
        with patch("actions.traffic_info._geocode", side_effect=[(0.0, 0.0), (1.0, 1.0)]):
            with patch("actions.traffic_info._ors_route", return_value=_make_ors_response()):
                result = traffic_info({"action": "route", "from": "A", "to": "B"})
        assert "A" in result and "B" in result

    def test_trayecto_alias(self, monkeypatch):
        monkeypatch.setenv("JARVIS_HOME_ADDRESS", "Casa")
        monkeypatch.setenv("JARVIS_WORK_ADDRESS", "Oficina")
        monkeypatch.setenv("ORS_API_KEY", "k")
        with patch("actions.traffic_info._geocode", side_effect=[(0.0, 0.0), (1.0, 1.0)]):
            with patch("actions.traffic_info._ors_route", return_value=_make_ors_response()):
                result = traffic_info({"action": "trayecto"})
        assert isinstance(result, str)
