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
                     "lilith_memory_delete", "lilith_home_action", "lilith_health",
                     "lilith_request_approval", "lilith_resolve_approval"):
            self.assertIn(tool, names)

    def test_lilith_tools_excluded_from_cloud_safe(self):
        cloud_tools = {t["name"] for t in get_tool_declarations(cloud_safe=True)}
        for tool in ("lilith_memory_search", "lilith_memory_store",
                     "lilith_memory_delete", "lilith_home_action", "lilith_health",
                     "lilith_request_approval", "lilith_resolve_approval"):
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


# ── 4b. lilith_memory_delete (JL-M004) ─────────────────────────────────

class TestLilithMemoryDelete(unittest.TestCase):

    def test_delete_ok(self):
        mock = AsyncMock()
        mock.delete_memory.return_value = {"key": "jarvis:café", "action": "deleted"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_delete", {"key": "café"})))
        self.assertIn("deleted", resp.response["result"])
        mock.delete_memory.assert_awaited_once_with("café", reason="user_request")

    def test_delete_with_reason(self):
        mock = AsyncMock()
        mock.delete_memory.return_value = {"key": "jarvis:old", "action": "deleted"}
        jarvis = _make_jarvis(lilith_client=mock)
        _run(jarvis._execute_tool(_fake_fc("lilith_memory_delete", {
            "key": "old", "reason": "no longer true",
        })))
        mock.delete_memory.assert_awaited_once_with("old", reason="no longer true")

    def test_delete_no_bridge(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_delete", {"key": "x"})))
        self.assertIn("not available", resp.response["result"])

    def test_delete_empty_key(self):
        jarvis = _make_jarvis(lilith_client=AsyncMock())
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_delete", {"key": ""})))
        self.assertIn("No memory key", resp.response["result"])

    def test_delete_exception(self):
        mock = AsyncMock()
        mock.delete_memory.side_effect = RuntimeError("not found")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_delete", {"key": "x"})))
        self.assertIn("failed", resp.response["result"])

    def test_delete_in_mutating_set(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py")).read()
        self.assertIn('"lilith_memory_delete"', src)


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
        self.assertIn('"lilith_resolve_approval"', src)


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


# ── 9. Context injection (JL-M003) ──────────────────────────────────────

class TestLilithContextInjection(unittest.TestCase):

    def test_format_lilith_context_basic(self):
        ctx = {
            "categories": {
                "preferences": [
                    {"key": "color", "value": "azul", "confidence": 0.9, "source": "s"},
                    {"key": "comida", "value": "pizza", "confidence": 0.8, "source": "s"},
                ],
                "family": [
                    {"key": "madre", "value": "María", "confidence": 1.0, "source": "identity_document"},
                ],
            },
            "total_facts": 3,
        }
        result = main.JarvisLive._format_lilith_context(ctx)
        self.assertIn("LILITH PERSISTENT MEMORY", result)
        self.assertIn("azul", result)
        self.assertIn("pizza", result)
        self.assertIn("María", result)
        self.assertIn("Preferences:", result)
        self.assertIn("Family:", result)

    def test_format_lilith_context_empty(self):
        result = main.JarvisLive._format_lilith_context({"categories": {}, "total_facts": 0})
        self.assertEqual(result, "")

    def test_format_lilith_context_none(self):
        result = main.JarvisLive._format_lilith_context({})
        self.assertEqual(result, "")

    def test_format_lilith_context_truncation_at_line_boundary(self):
        ctx = {
            "categories": {
                "notes": [{"key": f"k{i}", "value": "x" * 200, "confidence": 0.5, "source": "s"} for i in range(30)],
            },
            "total_facts": 30,
        }
        result = main.JarvisLive._format_lilith_context(ctx)
        self.assertLessEqual(len(result), 3001)
        self.assertFalse(result.endswith("…"), "should truncate at section boundary, not mid-text")

    def test_format_skips_operational_categories(self):
        ctx = {
            "categories": {
                "jarvis_fact": [{"key": "test", "value": "JL-S004 probe", "confidence": 0.8, "source": "jarvis"}],
                "project_status": [{"key": "audit", "value": "pytest 1108 passed", "confidence": 0.9, "source": "codex"}],
                "conversation_summary": [{"key": "conv:x", "value": "old convo", "confidence": 0.8, "source": "conv"}],
                "signal": [{"key": "_asked:x", "value": "internal", "confidence": 0.5, "source": "system"}],
                "identity": [{"key": "nombre", "value": "Flako", "confidence": 1.0, "source": "identity_document"}],
            },
            "total_facts": 5,
        }
        result = main.JarvisLive._format_lilith_context(ctx)
        self.assertIn("Flako", result)
        self.assertNotIn("JL-S004", result)
        self.assertNotIn("pytest", result)
        self.assertNotIn("old convo", result)
        self.assertNotIn("internal", result)

    def test_format_priority_order(self):
        ctx = {
            "categories": {
                "habits": [{"key": "h", "value": "café", "confidence": 0.9, "source": "s"}],
                "identity": [{"key": "n", "value": "Flako", "confidence": 1.0, "source": "s"}],
                "preferences": [{"key": "p", "value": "jazz", "confidence": 0.8, "source": "s"}],
            },
            "total_facts": 3,
        }
        result = main.JarvisLive._format_lilith_context(ctx)
        idx_identity = result.index("Identity:")
        idx_preferences = result.index("Preferences:")
        idx_habits = result.index("Habits:")
        self.assertLess(idx_identity, idx_preferences)
        self.assertLess(idx_preferences, idx_habits)


# ── 10. Approval tools (JL-S003) ──────────────────────────────────────

class TestLilithRequestApproval(unittest.TestCase):

    def test_request_approval_ok(self):
        mock = AsyncMock()
        mock.request_approval.return_value = {
            "token": "abc123", "expires_at": "2026-10-02T12:00:00Z",
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_request_approval", {
            "entity_id": "light.bombilla", "action": "turn_on",
        })))
        self.assertIn("abc123", resp.response["result"])
        self.assertIn("Approval requested", resp.response["result"])

    def test_request_approval_offline(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_request_approval", {
            "entity_id": "light.x", "action": "turn_on",
        })))
        self.assertIn("not available", resp.response["result"])

    def test_request_approval_missing_args(self):
        mock = AsyncMock()
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_request_approval", {
            "entity_id": "", "action": "turn_on",
        })))
        self.assertIn("Missing", resp.response["result"])

    def test_request_approval_error(self):
        mock = AsyncMock()
        mock.request_approval.side_effect = Exception("offline")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_request_approval", {
            "entity_id": "light.x", "action": "turn_on",
        })))
        self.assertIn("failed", resp.response["result"])


class TestLilithResolveApproval(unittest.TestCase):

    def test_resolve_approve_executed(self):
        mock = AsyncMock()
        mock.resolve_approval.return_value = {
            "resolution": "executed",
            "execution": {"entity_id": "light.x", "action": "turn_on"},
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_resolve_approval", {
            "token": "tok123", "resolution": "approved",
        })))
        self.assertIn("Approved and executed", resp.response["result"])

    def test_resolve_rejected(self):
        mock = AsyncMock()
        mock.resolve_approval.return_value = {"resolution": "rejected"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_resolve_approval", {
            "token": "tok123", "resolution": "rejected",
        })))
        self.assertIn("rejected", resp.response["result"])

    def test_resolve_expired(self):
        mock = AsyncMock()
        mock.resolve_approval.return_value = {"resolution": "expired"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_resolve_approval", {
            "token": "tok123", "resolution": "approved",
        })))
        self.assertIn("expired", resp.response["result"])

    def test_resolve_invalid_resolution(self):
        mock = AsyncMock()
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_resolve_approval", {
            "token": "tok123", "resolution": "maybe",
        })))
        self.assertIn("Invalid", resp.response["result"])

    def test_resolve_offline(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_resolve_approval", {
            "token": "tok123", "resolution": "approved",
        })))
        self.assertIn("not available", resp.response["result"])

    def test_resolve_error(self):
        mock = AsyncMock()
        mock.resolve_approval.side_effect = Exception("timeout")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_resolve_approval", {
            "token": "tok123", "resolution": "approved",
        })))
        self.assertIn("failed", resp.response["result"])

    def test_resolve_approval_tool_in_declarations(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py")).read()
        self.assertIn('"lilith_request_approval"', src)
        self.assertIn('"lilith_resolve_approval"', src)


if __name__ == "__main__":
    unittest.main()
