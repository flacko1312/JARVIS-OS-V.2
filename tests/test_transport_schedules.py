"""Tests for transport_schedules tool (E51)."""
import pytest
from actions.transport_schedules import transport_schedules, _detect_transport_type, _fmt_metro, _fmt_cercanias


class TestDetectTransportType:
    def test_metro_with_line(self):
        assert _detect_transport_type("horario metro línea 3") == ("metro", "3")

    def test_metro_line_before(self):
        assert _detect_transport_type("línea 6 del metro de Madrid") == ("metro", "6")

    def test_cercanias_with_line(self):
        t, k = _detect_transport_type("cercanías C1")
        assert t == "cercanias" and k == "1"

    def test_cercanias_c4(self):
        t, k = _detect_transport_type("tren cercanías C4")
        assert t == "cercanias" and k == "4"

    def test_emt_bus(self):
        assert _detect_transport_type("autobús EMT") == ("emt", None)

    def test_buhons(self):
        assert _detect_transport_type("búho nocturno") == ("emt", None)

    def test_renfe(self):
        assert _detect_transport_type("tren Renfe AVE") == ("renfe", None)

    def test_metro_generic(self):
        assert _detect_transport_type("metro Madrid") == ("metro", None)

    def test_generic(self):
        t, _ = _detect_transport_type("transporte público Sevilla")
        assert t == "generic"

    def test_cercanias_c10(self):
        t, k = _detect_transport_type("horario cercanías C10")
        assert t == "cercanias" and k == "10"


class TestFmtMetro:
    def test_known_line(self):
        result = _fmt_metro("1")
        assert "Línea 1" in result
        assert "6:00" in result
        assert "1:30" in result

    def test_line_6_later_last(self):
        result = _fmt_metro("6")
        assert "2:00" in result

    def test_unknown_line(self):
        result = _fmt_metro("99")
        assert "no encontrada" in result

    def test_contains_metro_madrid(self):
        result = _fmt_metro("3")
        assert "Metro Madrid" in result


class TestFmtCercanias:
    def test_known_line(self):
        result = _fmt_cercanias("1")
        assert "C1" in result
        assert "5:35" in result

    def test_unknown_line(self):
        result = _fmt_cercanias("99")
        assert "no encontrada" in result

    def test_contains_renfe(self):
        result = _fmt_cercanias("c2")
        assert "renfe" in result.lower() or "Cercanías" in result


class TestTransportSchedules:
    def test_no_params_returns_help(self):
        result = transport_schedules({})
        assert "metro" in result.lower() or "transporte" in result.lower()

    def test_status_action(self):
        result = transport_schedules({"action": "status"})
        assert "transport_schedules" in result.lower() or "API" in result

    def test_metro_line_query(self):
        result = transport_schedules({"action": "query", "query": "metro línea 1"})
        assert "Línea 1" in result or "metro" in result.lower()

    def test_metro_all_lines(self):
        result = transport_schedules({"action": "query", "query": "metro Madrid"})
        assert "Metro Madrid" in result

    def test_cercanias_c1(self):
        result = transport_schedules({"action": "query", "query": "cercanías C1"})
        assert "C1" in result or "Cercanías" in result

    def test_cercanias_all(self):
        result = transport_schedules({"query": "cercanías"})
        assert "Cercanías" in result

    def test_emt_buses(self):
        result = transport_schedules({"query": "autobús nocturno EMT"})
        assert "EMT" in result or "búho" in result.lower() or "Búho" in result

    def test_renfe_ave(self):
        result = transport_schedules({"query": "renfe AVE Madrid Barcelona"})
        assert "Renfe" in result or "renfe" in result.lower()

    def test_generic_fallback(self):
        result = transport_schedules({"query": "cómo llegar al aeropuerto"})
        assert len(result) > 50  # returns something useful

    def test_no_parameters(self):
        result = transport_schedules(None)
        assert isinstance(result, str) and len(result) > 20

    def test_line_param(self):
        result = transport_schedules({"line": "metro línea 5"})
        assert "5" in result or "metro" in result.lower()

    def test_horario_action(self):
        result = transport_schedules({"action": "horario", "query": "metro línea 3"})
        assert "3" in result

    def test_metro_6_circular(self):
        result = transport_schedules({"query": "metro línea 6"})
        assert "2:00" in result or "Circular" in result

    def test_result_always_string(self):
        for params in [
            {"action": "query", "query": ""},
            {"action": "status"},
            {"query": "tren"},
            None,
            {},
        ]:
            assert isinstance(transport_schedules(params), str)

    def test_cercanias_c4a(self):
        result = transport_schedules({"query": "cercanías C4"})
        assert "C4" in result or "Cercanías" in result
