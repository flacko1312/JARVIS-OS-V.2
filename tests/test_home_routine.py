"""Tests for home_routine tool — smart domestic meta-routines."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from actions.home_routine import home_routine, _ROUTINES, _get_current_time


class TestHomeRoutineList:
    def test_list_returns_all_routines(self):
        result = home_routine({"action": "list"})
        assert "buenos_dias" in result
        assert "me_voy" in result
        assert "llegue_a_casa" in result
        assert "buenas_noches" in result
        assert "modo_taller" in result

    def test_list_includes_descriptions(self):
        result = home_routine({"action": "list"})
        assert "rutinas" in result.lower() or "Rutinas" in result

    def test_empty_params_returns_list(self):
        result = home_routine({})
        assert "buenos_dias" in result

    def test_none_params_returns_list(self):
        result = home_routine(None)
        assert "buenos_dias" in result

    def test_unknown_routine_returns_error(self):
        result = home_routine({"action": "run", "routine": "desayuno_magico"})
        assert "no reconocida" in result.lower() or "disponibles" in result.lower()


class TestBuenosDias:
    def test_buenos_dias_via_action(self):
        result = home_routine({"action": "buenos_dias"})
        assert "Buenos días" in result or "buenos días" in result.lower()

    def test_buenos_dias_includes_time(self):
        result = home_routine({"action": "buenos_dias"})
        # Should include time info
        assert any(word in result.lower() for word in ["son las", "hora", "del"])

    def test_buenos_dias_no_device_actions(self):
        # buenos_dias never touches devices
        result = home_routine({"action": "buenos_dias"})
        assert "confirmación" not in result.lower() or "sin cambios" in result.lower()

    def test_buenos_dias_via_routine_param(self):
        result = home_routine({"action": "run", "routine": "buenos_dias"})
        assert "Buenos días" in result or "buenos días" in result.lower()


class TestMeVoy:
    def test_me_voy_without_confirm_shows_preview(self):
        result = home_routine({"action": "me_voy"})
        assert "confirmación" in result.lower() or "pendiente" in result.lower()

    def test_me_voy_lists_devices(self):
        result = home_routine({"action": "me_voy"})
        assert "bombilla" in result.lower() or "switch" in result.lower() or "cargador" in result.lower()

    def test_me_voy_with_confirm_executes(self):
        result = home_routine({"action": "me_voy", "confirm": True})
        # Should attempt device actions (may fail if LILITH not reachable, but should report)
        assert "apagado" in result.lower() or "disponible" in result.lower() or "error" in result.lower()

    def test_me_voy_announcement_present(self):
        result = home_routine({"action": "me_voy"})
        assert "salida" in result.lower() or "luego" in result.lower() or "Iniciando" in result


class TestLlegueACasa:
    def test_llegue_without_confirm_shows_preview(self):
        result = home_routine({"action": "llegue_a_casa"})
        assert "confirmación" in result.lower() or "pendiente" in result.lower()

    def test_llegue_includes_greeting(self):
        result = home_routine({"action": "llegue_a_casa"})
        assert "bienvenido" in result.lower() or "casa" in result.lower()

    def test_llegue_with_confirm(self):
        result = home_routine({"action": "llegue_a_casa", "confirm": True})
        assert "encendido" in result.lower() or "disponible" in result.lower() or "error" in result.lower()


class TestBuenasNoches:
    def test_buenas_noches_without_confirm_shows_preview(self):
        result = home_routine({"action": "buenas_noches"})
        assert "confirmación" in result.lower() or "pendiente" in result.lower()

    def test_buenas_noches_suggests_alarm(self):
        result = home_routine({"action": "buenas_noches"})
        # Should suggest setting an alarm or confirm device control
        assert "alarma" in result.lower() or "confirma" in result.lower()

    def test_buenas_noches_with_confirm(self):
        result = home_routine({"action": "buenas_noches", "confirm": True})
        assert "apagado" in result.lower() or "disponible" in result.lower()


class TestModoTaller:
    def test_modo_taller_without_confirm(self):
        result = home_routine({"action": "modo_taller"})
        assert "confirmación" in result.lower() or "pendiente" in result.lower()

    def test_modo_taller_mentions_brightness(self):
        result = home_routine({"action": "modo_taller"})
        assert "brillo" in result.lower() or "blanca" in result.lower() or "taller" in result.lower()

    def test_modo_taller_with_confirm(self):
        result = home_routine({"action": "modo_taller", "confirm": True})
        assert "configurado" in result.lower() or "disponible" in result.lower()


class TestCurrentTime:
    def test_get_current_time_returns_string(self):
        t = _get_current_time()
        assert isinstance(t, str)
        assert len(t) > 10

    def test_get_current_time_has_hour(self):
        t = _get_current_time()
        assert "las" in t.lower() or ":" in t


class TestRoutineDefinitions:
    def test_all_routines_have_name(self):
        for key, r in _ROUTINES.items():
            assert "name" in r, f"Routine '{key}' missing 'name'"

    def test_all_routines_have_description(self):
        for key, r in _ROUTINES.items():
            assert "description" in r, f"Routine '{key}' missing 'description'"

    def test_all_routines_have_announcement(self):
        for key, r in _ROUTINES.items():
            assert "announcement" in r, f"Routine '{key}' missing 'announcement'"

    def test_device_routines_require_confirm(self):
        for key, r in _ROUTINES.items():
            if r.get("device_action"):
                assert r.get("device_confirm_required"), f"Routine '{key}' has device_action but no confirm_required"

    def test_buenos_dias_no_device_action(self):
        assert _ROUTINES["buenos_dias"]["device_action"] is None

    def test_five_routines_defined(self):
        assert len(_ROUTINES) == 5
