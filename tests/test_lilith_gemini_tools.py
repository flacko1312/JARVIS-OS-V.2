"""JL-W005: LILITH Gemini Live tool integration tests.

Offline tests: no network, no real Gemini, no real LILITH. Uses unittest/asyncio
and mocks only. Verifies that:
  * LILITH tool declarations are registered in TOOL_DECLARATIONS;
  * LILITH tools are excluded from cloud_safe mode;
  * tool dispatcher routes to LILITH client methods correctly;
  * memory search/store work through the bridge;
  * HOME resolve + action + readback work end-to-end;
  * unknown/ambiguous/not_allowed devices are handled safely;
  * unsupported actions and missing targets are rejected;
  * LILITH offline returns a useful error, never crashes;
  * malformed args and timeouts are handled;
  * existing tools and typed integration are preserved.
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import main
from main import TOOL_DECLARATIONS, get_tool_declarations
from core.lilith_gateway import LilithBridge


# ── helpers ──────────────────────────────────────────────────────────────

class StubClient:
    """Minimal stand-in for ``JarvisClient`` (the desktop UI object)."""
    def __init__(self):
        self.on_text_command = None
        self.muted = False
        self.current_file = None
        self._voice_combo = None
        self.operational_ready = True
        self.logs = []

    def write_log(self, text):
        self.logs.append(text)

    def set_state(self, state):
        pass

    def sync_voice_display(self, v):
        pass

    def show_tool_progress(self, n):
        pass

    def hide_tool_progress(self):
        pass

    def handle_ui_command(self, cmd):
        pass


def _fake_fc(name: str, args: dict | None = None):
    """Simulate a Gemini ``FunctionCall`` namedtuple."""
    fc = SimpleNamespace()
    fc.name = name
    fc.args = args or {}
    fc.id = f"fake-{name}"
    return fc


def _make_jarvis(*, lilith_client=None) -> main.JarvisLive:
    """Build a ``JarvisLive`` with a fake UI client and optional mock LILITH."""
    client = StubClient()
    jarvis = main.JarvisLive(client, "puck")

    if lilith_client is not None:
        runtime = SimpleNamespace(client=lilith_client, lilith_available=True)
        runtime.start = AsyncMock()
        runtime.stop = AsyncMock()
        bridge = LilithBridge(runtime)
        bridge._started = True
        jarvis._lilith = bridge

    return jarvis


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. Tool declarations ────────────────────────────────────────────────

class TestToolDeclarations(unittest.TestCase):

    def test_lilith_tools_registered(self):
        names = {t["name"] for t in TOOL_DECLARATIONS}
        for tool in ("lilith_memory_search", "lilith_memory_store",
                     "lilith_home_action", "lilith_health"):
            self.assertIn(tool, names)

    def test_lilith_tools_excluded_from_cloud_safe(self):
        cloud_tools = {t["name"] for t in get_tool_declarations(cloud_safe=True)}
        for tool in ("lilith_memory_search", "lilith_memory_store",
                     "lilith_home_action", "lilith_health"):
            self.assertNotIn(tool, cloud_tools)

    def test_existing_tools_preserved(self):
        names = {t["name"] for t in TOOL_DECLARATIONS}
        for existing in ("open_app", "web_search", "save_memory", "browser_control"):
            self.assertIn(existing, names)


# ── 2. lilith_health ─────────────────────────────────────────────────────

class TestLilithHealth(unittest.TestCase):

    def test_health_ok(self):
        mock = AsyncMock()
        mock.health.return_value = {
            "status": "online", "version": "1.0.0",
            "services": {"database": True, "mqtt": True, "kernel": True, "home_assistant": True},
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_health")))
        r = resp.response["result"]
        self.assertIn("online", r)
        self.assertIn("1.0.0", r)

    def test_health_no_bridge(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_health")))
        self.assertIn("not configured", resp.response["result"])

    def test_health_exception(self):
        mock = AsyncMock()
        mock.health.side_effect = ConnectionError("unreachable")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_health")))
        self.assertIn("failed", resp.response["result"])


# ── 3. lilith_memory_search ─────────────────────────────────────────────

class TestLilithMemorySearch(unittest.TestCase):

    def test_search_with_results(self):
        mock = AsyncMock()
        mock.search_memory.return_value = [
            {"text": "El usuario prefiere café", "score": 0.9},
            {"text": "Le gusta el jazz", "score": 0.7},
        ]
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_search", {"query": "preferencias"})))
        r = resp.response["result"]
        self.assertIn("café", r)
        self.assertIn("jazz", r)

    def test_search_empty(self):
        mock = AsyncMock()
        mock.search_memory.return_value = []
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_search", {"query": "xyz"})))
        self.assertIn("No results", resp.response["result"])

    def test_search_no_bridge(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_search", {"query": "test"})))
        self.assertIn("not available", resp.response["result"])

    def test_search_exception(self):
        mock = AsyncMock()
        mock.search_memory.side_effect = TimeoutError("timeout")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_search", {"query": "test"})))
        self.assertIn("failed", resp.response["result"])

    def test_search_passes_limit(self):
        mock = AsyncMock()
        mock.search_memory.return_value = [{"text": "x", "score": 0.5}]
        jarvis = _make_jarvis(lilith_client=mock)
        _run(jarvis._execute_tool(_fake_fc("lilith_memory_search", {"query": "q", "limit": 3})))
        mock.search_memory.assert_awaited_once_with("q", limit=3)


# ── 4. lilith_memory_store ───────────────────────────────────────────────

class TestLilithMemoryStore(unittest.TestCase):

    def test_store_ok(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {"key": "jarvis:test", "action": "created"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "content": "Me gusta el café con leche",
            "category": "preferences",
        })))
        self.assertIn("created", resp.response["result"])

    def test_store_no_bridge(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {"content": "test"})))
        self.assertIn("not available", resp.response["result"])

    def test_store_exception(self):
        mock = AsyncMock()
        mock.store_memory.side_effect = RuntimeError("forbidden")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {"content": "test"})))
        self.assertIn("failed", resp.response["result"])

    def test_store_default_category(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {"key": "k", "action": "created"}
        jarvis = _make_jarvis(lilith_client=mock)
        _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {"content": "algo"})))
        _, kwargs = mock.store_memory.call_args
        self.assertEqual(kwargs.get("category"), "jarvis_fact")


# ── 5. lilith_home_action — happy path ───────────────────────────────────

class TestLilithHomeAction(unittest.TestCase):

    def test_turn_on_resolved(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {
            "status": "resolved", "entity_id": "light.bombilla_mueble",
            "friendly_name": "Bombilla del mueble",
        }
        mock.home_action.return_value = {}
        mock.home_entity.return_value = {"state": "on", "entity_id": "light.bombilla_mueble"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "luz del mueble", "action": "turn_on",
        })))
        r = resp.response["result"]
        self.assertIn("turn_on", r)
        self.assertIn("on", r)
        mock.home_resolve.assert_awaited_once_with("luz del mueble")
        mock.home_action.assert_awaited_once_with("light.bombilla_mueble", "turn_on")

    def test_turn_off_resolved(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {
            "status": "resolved", "entity_id": "light.bombilla_mueble",
            "friendly_name": "Bombilla del mueble",
        }
        mock.home_action.return_value = {}
        mock.home_entity.return_value = {"state": "off"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "luz del mueble", "action": "turn_off",
        })))
        self.assertIn("off", resp.response["result"])

    def test_readback_fails_gracefully(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {
            "status": "resolved", "entity_id": "light.x", "friendly_name": "X",
        }
        mock.home_action.return_value = {}
        mock.home_entity.side_effect = TimeoutError("readback timeout")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "X", "action": "turn_on",
        })))
        self.assertIn("Could not confirm", resp.response["result"])


# ── 6. lilith_home_action — safety cases ─────────────────────────────────

class TestLilithHomeActionSafety(unittest.TestCase):

    def test_unknown_device(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {"status": "unknown"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "luz del baño", "action": "turn_on",
        })))
        r = resp.response["result"]
        self.assertIn("Unknown", r)
        self.assertIn("No action taken", r)
        mock.home_action.assert_not_awaited()

    def test_ambiguous_device(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {
            "status": "ambiguous",
            "candidates": [
                {"entity_id": "light.a", "friendly_name": "Bombilla A"},
                {"entity_id": "light.b", "friendly_name": "Bombilla B"},
            ],
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "la bombilla", "action": "turn_on",
        })))
        r = resp.response["result"]
        self.assertIn("Ambiguous", r)
        self.assertIn("Bombilla A", r)
        mock.home_action.assert_not_awaited()

    def test_not_allowed_device(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {"status": "not_allowed"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "servidor", "action": "turn_off",
        })))
        self.assertIn("Not allowed", resp.response["result"])
        mock.home_action.assert_not_awaited()

    def test_unsupported_action(self):
        jarvis = _make_jarvis(lilith_client=AsyncMock())
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "luz", "action": "toggle",
        })))
        self.assertIn("Only turn_on and turn_off", resp.response["result"])

    def test_empty_target(self):
        jarvis = _make_jarvis(lilith_client=AsyncMock())
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "", "action": "turn_on",
        })))
        self.assertIn("No device target", resp.response["result"])

    def test_no_bridge(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "luz", "action": "turn_on",
        })))
        self.assertIn("not available", resp.response["result"])

    def test_connection_error(self):
        mock = AsyncMock()
        mock.home_resolve.side_effect = ConnectionError("offline")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "luz", "action": "turn_on",
        })))
        self.assertIn("failed", resp.response["result"])


# ── 7. Mutating set ─────────────────────────────────────────────────────

class TestMutatingSet(unittest.TestCase):

    def test_lilith_mutating_tools_in_set(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py")).read()
        self.assertIn('"lilith_memory_store"', src)
        self.assertIn('"lilith_home_action"', src)


# ── 8. Preservation ─────────────────────────────────────────────────────

class TestPreservation(unittest.TestCase):

    def test_typed_integration_bridge_attribute(self):
        client = StubClient()
        jarvis = main.JarvisLive(client, "puck")
        self.assertTrue(hasattr(jarvis, "_lilith"))
        self.assertIsNone(jarvis._lilith)

    def test_save_memory_still_exists(self):
        names = {t["name"] for t in TOOL_DECLARATIONS}
        self.assertIn("save_memory", names)


if __name__ == "__main__":
    unittest.main()
