"""Tests for batch_home_action (B23/B24)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from actions.batch_home_action import batch_home_action, batch_home_action_async


def _make_client(resolve_status="resolved", entity_id="light.test", friendly_name="Test Light"):
    """Create a mock LILITH client."""
    client = MagicMock()
    client.home_resolve = AsyncMock(return_value={
        "status": resolve_status,
        "entity_id": entity_id,
        "friendly_name": friendly_name,
        "candidates": [
            {"entity_id": "light.a", "friendly_name": "Light A"},
            {"entity_id": "light.b", "friendly_name": "Light B"},
        ],
    })
    client.home_action = AsyncMock(return_value={"status": "ok"})
    return client


class TestBatchHomeActionSync:
    def test_no_targets_returns_help(self):
        result = batch_home_action({"targets": [], "action": "turn_on"}, lilith_client=_make_client())
        assert "No devices" in result

    def test_no_client_returns_error(self):
        result = batch_home_action({"targets": ["luz"], "action": "turn_on"}, lilith_client=None)
        assert "LILITH" in result

    def test_invalid_action(self):
        result = batch_home_action({"targets": ["luz"], "action": "explode"}, lilith_client=_make_client())
        assert "turn_on" in result or "turn_off" in result

    def test_single_target_resolved(self):
        result = batch_home_action({"targets": ["bombilla"], "action": "turn_on"}, lilith_client=_make_client())
        assert "1/1" in result
        assert "encendido" in result.lower() or "✓" in result

    def test_multiple_targets(self):
        result = batch_home_action(
            {"targets": ["luz 1", "luz 2", "luz 3"], "action": "turn_off"},
            lilith_client=_make_client()
        )
        assert "3/3" in result

    def test_string_targets_comma_separated(self):
        result = batch_home_action(
            {"targets": "bombilla mueble, bombilla tv", "action": "turn_on"},
            lilith_client=_make_client()
        )
        assert "2/2" in result

    def test_none_parameters_handled(self):
        result = batch_home_action(None, lilith_client=_make_client())
        assert "No devices" in result

    def test_empty_dict_parameters(self):
        result = batch_home_action({}, lilith_client=_make_client())
        assert "No devices" in result


class TestBatchHomeActionAsync:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_resolved_device_turn_on(self):
        client = _make_client("resolved", "light.salon", "Luz Salón")
        result = self._run(batch_home_action_async(["luz salón"], "turn_on", client))
        assert "✓" in result
        assert "Luz Salón" in result

    def test_ambiguous_device(self):
        client = _make_client("ambiguous")
        result = self._run(batch_home_action_async(["luz"], "turn_on", client))
        assert "⚠" in result or "ambiguo" in result.lower()

    def test_unknown_device(self):
        client = _make_client("unknown")
        result = self._run(batch_home_action_async(["xyz123"], "turn_off", client))
        assert "⚠" in result or "desconocido" in result.lower()

    def test_not_allowed_device(self):
        client = _make_client("not_allowed")
        result = self._run(batch_home_action_async(["termostato"], "turn_on", client))
        assert "⚠" in result or "denegado" in result.lower()

    def test_mixed_results(self):
        """Two resolved + one unknown — summary reflects partial success."""
        call_count = [0]
        client = MagicMock()
        async def resolve(target):
            call_count[0] += 1
            if "desconocido" in target:
                return {"status": "unknown", "entity_id": None, "friendly_name": None, "candidates": []}
            return {"status": "resolved", "entity_id": f"light.{call_count[0]}", "friendly_name": f"Luz {call_count[0]}", "candidates": []}
        client.home_resolve = resolve
        client.home_action = AsyncMock(return_value={"status": "ok"})
        result = self._run(batch_home_action_async(["luz a", "desconocido xyz", "luz b"], "turn_on", client))
        assert "2/3" in result

    def test_empty_targets(self):
        client = _make_client()
        result = self._run(batch_home_action_async([], "turn_on", client))
        assert "No devices" in result

    def test_invalid_action(self):
        client = _make_client()
        result = self._run(batch_home_action_async(["luz"], "fly", client))
        assert "turn_on" in result or "turn_off" in result

    def test_exception_does_not_break_others(self):
        """If one device throws, others still succeed."""
        client = MagicMock()
        call_count = [0]
        async def resolve(target):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("connection refused")
            return {"status": "resolved", "entity_id": "light.ok", "friendly_name": "Luz OK", "candidates": []}
        client.home_resolve = resolve
        client.home_action = AsyncMock(return_value={"status": "ok"})
        result = self._run(batch_home_action_async(["luz a", "luz b", "luz c"], "turn_on", client))
        assert "2/3" in result
        assert "✗" in result or "error" in result.lower()

    def test_summary_line_first(self):
        client = _make_client("resolved", "light.x", "Luz X")
        result = self._run(batch_home_action_async(["luz x"], "turn_off", client))
        first_line = result.split("\n")[0]
        assert "1/1" in first_line
        assert "apagado" in first_line.lower()
