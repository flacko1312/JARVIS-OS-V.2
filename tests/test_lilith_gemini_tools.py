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
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── 1. Tool declarations ────────────────────────────────────────────────

class TestToolDeclarations(unittest.TestCase):

    def test_lilith_tools_registered(self):
        names = {t["name"] for t in TOOL_DECLARATIONS}
        for tool in ("lilith_memory_search", "lilith_memory_store",
                     "lilith_memory_delete", "lilith_home_action", "lilith_health",
                     "lilith_runtime_status", "lilith_request_approval",
                     "lilith_resolve_approval", "lilith_docs_list",
                     "lilith_docs_read", "lilith_docs_search",
                     "lilith_source_list", "lilith_source_read",
                     "lilith_source_search", "lilith_git_status",
                     "lilith_command_submit"):
            self.assertIn(tool, names)

    def test_lilith_tools_excluded_from_cloud_safe(self):
        cloud_tools = {t["name"] for t in get_tool_declarations(cloud_safe=True)}
        for tool in ("lilith_memory_search", "lilith_memory_store",
                     "lilith_memory_delete", "lilith_home_action", "lilith_health",
                     "lilith_runtime_status", "lilith_request_approval",
                     "lilith_resolve_approval", "lilith_docs_list",
                     "lilith_docs_read", "lilith_docs_search",
                     "lilith_source_list", "lilith_source_read",
                     "lilith_source_search", "lilith_git_status",
                     "lilith_command_submit"):
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


class TestLilithRuntimeStatus(unittest.TestCase):

    def test_runtime_status_ok(self):
        mock = AsyncMock()
        mock.runtime_status.return_value = {
            "health": {
                "status": "online",
                "services": {"database": True, "mqtt": True, "kernel": True},
            },
            "autonomy": {
                "running": True,
                "state": "OBSERVATION",
                "queue": {"queued": 0, "succeeded": 3},
            },
            "aut6": {"satisfaction": {"score": 91}},
            "goals": {"total": 2},
            "monitor": {"recent_errors": 0},
            "routines": {"available": False, "reason": "not_implemented"},
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_runtime_status")))
        result = resp.response["result"]
        self.assertIn("online", result)
        self.assertIn("autonomy: running", result)
        self.assertIn("satisfaction: 91", result)
        self.assertIn("routines: not_implemented", result)
        mock.runtime_status.assert_awaited_once()

    def test_runtime_status_reports_degraded_services(self):
        mock = AsyncMock()
        mock.runtime_status.return_value = {
            "health": {
                "status": "degraded",
                "services": {"database": True, "mqtt": False, "kernel": True},
            },
            "autonomy": {"running": False, "state": "OBSERVATION", "queue": {}},
            "aut6": {},
            "goals": {},
            "monitor": {},
            "routines": {"available": False, "reason": "not_implemented"},
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_runtime_status")))
        result = resp.response["result"]
        self.assertIn("degraded", result)
        self.assertIn("services down: mqtt", result)
        self.assertIn("autonomy: stopped", result)

    def test_runtime_status_offline(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_runtime_status")))
        self.assertIn("not configured", resp.response["result"])

    def test_runtime_status_exception(self):
        mock = AsyncMock()
        mock.runtime_status.side_effect = TimeoutError("timeout")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_runtime_status")))
        self.assertIn("failed", resp.response["result"])


class TestLilithDocsTools(unittest.TestCase):

    def test_docs_list(self):
        mock = AsyncMock()
        mock.docs_list.return_value = {
            "documents": [
                {"path": "ARCHITECTURE.md"},
                {"path": "AI_MEMORY/CURRENT.md"},
            ],
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_docs_list", {"prefix": "AI_MEMORY"})))
        result = resp.response["result"]
        self.assertIn("ARCHITECTURE.md", result)
        self.assertIn("AI_MEMORY/CURRENT.md", result)
        mock.docs_list.assert_awaited_once_with(prefix="AI_MEMORY")

    def test_docs_read(self):
        mock = AsyncMock()
        mock.docs_read.return_value = {
            "path": "TASKS.md",
            "content": "# Tasks\nJL-A3 document access",
            "truncated": False,
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_docs_read", {
            "path": "TASKS.md", "max_bytes": 1000,
        })))
        self.assertIn("JL-A3", resp.response["result"])
        mock.docs_read.assert_awaited_once_with("TASKS.md", max_bytes=1000)

    def test_docs_search(self):
        mock = AsyncMock()
        mock.docs_search.return_value = {
            "results": [{
                "path": "ARCHITECTURE.md",
                "matches": [{"line": 4, "text": "ResistanceEngine boundary"}],
            }],
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_docs_search", {
            "query": "ResistanceEngine", "limit": 5,
        })))
        self.assertIn("ARCHITECTURE.md", resp.response["result"])
        self.assertIn("L4", resp.response["result"])
        mock.docs_search.assert_awaited_once_with("ResistanceEngine", limit=5)

    def test_docs_tools_offline(self):
        jarvis = _make_jarvis()
        for name, args in (
            ("lilith_docs_list", {}),
            ("lilith_docs_read", {"path": "TASKS.md"}),
            ("lilith_docs_search", {"query": "AUT-7"}),
        ):
            resp = _run(jarvis._execute_tool(_fake_fc(name, args)))
            self.assertIn("not configured", resp.response["result"])


class TestLilithSourceTools(unittest.TestCase):

    def test_source_list(self):
        mock = AsyncMock()
        mock.source_list.return_value = {
            "files": [
                {"path": "core/routers/integration.py"},
                {"path": "core/tests/test_jarvis_integration.py"},
            ],
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_source_list", {"prefix": "core"})))
        result = resp.response["result"]
        self.assertIn("core/routers/integration.py", result)
        self.assertIn("core/tests/test_jarvis_integration.py", result)
        mock.source_list.assert_awaited_once_with(prefix="core")

    def test_source_read(self):
        mock = AsyncMock()
        mock.source_read.return_value = {
            "path": "core/routers/integration.py",
            "content": "def integration_source_read():\n    pass",
            "truncated": False,
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_source_read", {
            "path": "core/routers/integration.py", "max_bytes": 1000,
        })))
        self.assertIn("integration_source_read", resp.response["result"])
        mock.source_read.assert_awaited_once_with(
            "core/routers/integration.py", max_bytes=1000)

    def test_source_search(self):
        mock = AsyncMock()
        mock.source_search.return_value = {
            "results": [{
                "path": "core/routers/integration.py",
                "matches": [{"line": 4, "text": "DecisionLevel boundary"}],
            }],
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_source_search", {
            "query": "DecisionLevel", "limit": 5,
        })))
        self.assertIn("core/routers/integration.py", resp.response["result"])
        self.assertIn("L4", resp.response["result"])
        mock.source_search.assert_awaited_once_with("DecisionLevel", limit=5)

    def test_source_tools_offline(self):
        jarvis = _make_jarvis()
        for name, args in (
            ("lilith_source_list", {}),
            ("lilith_source_read", {"path": "core/routers/integration.py"}),
            ("lilith_source_search", {"query": "DecisionLevel"}),
        ):
            resp = _run(jarvis._execute_tool(_fake_fc(name, args)))
            self.assertIn("not configured", resp.response["result"])


class TestLilithGitStatusTool(unittest.TestCase):

    def test_git_status(self):
        mock = AsyncMock()
        mock.git_status.return_value = {
            "branch": "main",
            "head": "abcdef1234567890",
            "origin_main": "abcdef1234567890",
            "head_equals_origin_main": True,
            "dirty": True,
            "dirty_files": ["core/voice/wakeword.py"],
            "untracked_files": [".claude/"],
            "diff_stat": [" core/voice/wakeword.py | 2 +-"],
            "recent": ["abcdef1 docs: smoke"],
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_git_status")))
        result = resp.response["result"]
        self.assertIn("main", result)
        self.assertIn("dirty", result)
        self.assertIn("core/voice/wakeword.py", result)
        self.assertIn("abcdef1 docs: smoke", result)
        mock.git_status.assert_awaited_once()

    def test_git_status_offline(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_git_status")))
        self.assertIn("not configured", resp.response["result"])


class TestLilithCommandSubmitTool(unittest.TestCase):

    def test_command_submit_completed(self):
        mock = AsyncMock()
        mock.command_submit.return_value = {
            "status": "completed",
            "intent": "git.status",
            "correlation_id": "corr-1",
            "replayed": False,
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_command_submit", {
            "intent": "git.status",
            "parameters": {},
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "idempotency_key": "idem-1",
        })))
        result = resp.response["result"]
        self.assertIn("completed", result)
        self.assertIn("corr-1", result)
        mock.command_submit.assert_awaited_once_with(
            intent="git.status",
            parameters={},
            request_id="req-1",
            correlation_id="corr-1",
            idempotency_key="idem-1",
        )

    def test_command_submit_offline(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_command_submit", {
            "intent": "git.status",
        })))
        self.assertIn("not configured", resp.response["result"])


class TestLilithRoutineTool(unittest.TestCase):

    def test_declared_and_excluded_from_cloud_safe(self):
        self.assertIn("lilith_routine", {t["name"] for t in TOOL_DECLARATIONS})
        self.assertNotIn("lilith_routine", {t["name"] for t in get_tool_declarations(cloud_safe=True)})

    def test_create_maps_natural_language_fields_to_authoritative_command(self):
        mock = AsyncMock()
        mock.command_submit.return_value = {
            "status": "completed", "correlation_id": "routine-corr",
            "response": {"routine": {"routine_id": 12, "name": "Noticias"}},
        }
        jarvis = _make_jarvis(lilith_client=mock)
        args = {"operation": "create", "name": "Noticias", "schedule_type": "daily",
                "schedule": {"hour": 5, "minute": 0}, "timezone": "Europe/Madrid",
                "action_intent": "runtime.status", "action_parameters": {}}
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_routine", args)))
        self.assertIn("LILITH confirmed", resp.response["result"])
        self.assertIn("routine_id", resp.response["result"])
        mock.command_submit.assert_awaited_once_with(
            intent="routines.create", parameters={k: v for k, v in args.items() if k != "operation"})

    def test_ambiguous_create_asks_for_missing_fields_without_calling_lilith(self):
        mock = AsyncMock()
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_routine", {
            "operation": "create", "name": "Bombilla",
        })))
        self.assertIn("ambiguous", resp.response["result"])
        mock.command_submit.assert_not_awaited()

    def test_disable_and_update_use_existing_routine_id(self):
        mock = AsyncMock()
        mock.command_submit.return_value = {"status": "completed", "correlation_id": "c", "response": {}}
        jarvis = _make_jarvis(lilith_client=mock)
        _run(jarvis._execute_tool(_fake_fc("lilith_routine", {"operation": "disable", "routine_id": 4})))
        _run(jarvis._execute_tool(_fake_fc("lilith_routine", {
            "operation": "update", "routine_id": 4, "schedule": {"hour": 10, "minute": 0}})))
        self.assertEqual(mock.command_submit.await_args_list[0].kwargs["intent"], "routines.disable")
        self.assertEqual(mock.command_submit.await_args_list[1].kwargs["intent"], "routines.update")

    def test_blocked_or_offline_never_reports_success(self):
        mock = AsyncMock()
        mock.command_submit.return_value = {"status": "blocked", "correlation_id": "c",
                                            "error": {"code": "routine_action_not_allowed"}}
        jarvis = _make_jarvis(lilith_client=mock)
        blocked = _run(jarvis._execute_tool(_fake_fc("lilith_routine", {
            "operation": "delete", "routine_id": 9}))).response["result"]
        self.assertIn("did not complete", blocked)
        self.assertNotIn("confirmed", blocked)
        offline = _run(_make_jarvis()._execute_tool(_fake_fc("lilith_routine", {
            "operation": "list"}))).response["result"]
        self.assertIn("no routine was changed", offline)


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

    def test_store_create(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {"key": "jarvis:preferences/favorite_color", "action": "created"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "favorite_color", "value": "lila", "category": "preferences",
        })))
        self.assertIn("created", resp.response["result"])
        mock.store_memory.assert_called_once_with(
            "preferences/favorite_color", "lila", category="preferences", confidence=1.0,
            description=None,
        )

    def test_store_update_disregard_hint(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {"key": "jarvis:preferences/favorite_color", "action": "updated"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "favorite_color", "value": "lila", "category": "preferences",
        })))
        self.assertIn("updated", resp.response["result"])
        self.assertIn("Disregard", resp.response["result"])

    def test_store_semantic_key_format(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {"key": "k", "action": "created"}
        jarvis = _make_jarvis(lilith_client=mock)
        _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "birthday", "value": "15 de marzo", "category": "family",
        })))
        call_args = mock.store_memory.call_args
        self.assertEqual(call_args[0][0], "family/birthday")

    def test_store_no_bridge(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "x", "value": "y",
        })))
        self.assertIn("not available", resp.response["result"])

    def test_store_missing_key(self):
        mock = AsyncMock()
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "", "value": "test",
        })))
        self.assertIn("Missing", resp.response["result"])

    def test_store_missing_value(self):
        mock = AsyncMock()
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "x", "value": "",
        })))
        self.assertIn("Missing", resp.response["result"])

    def test_store_exception(self):
        mock = AsyncMock()
        mock.store_memory.side_effect = RuntimeError("forbidden")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "x", "value": "y",
        })))
        self.assertIn("failed", resp.response["result"])

    def test_store_default_category(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {"key": "k", "action": "created"}
        jarvis = _make_jarvis(lilith_client=mock)
        _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "test_key", "value": "algo",
        })))
        _, kwargs = mock.store_memory.call_args
        self.assertEqual(kwargs.get("category"), "preferences")

    def test_store_idempotent_same_key(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {"key": "k", "action": "updated"}
        jarvis = _make_jarvis(lilith_client=mock)
        _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "favorite_color", "value": "lila", "category": "preferences",
        })))
        _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "favorite_color", "value": "lila", "category": "preferences",
        })))
        self.assertEqual(mock.store_memory.call_count, 2)
        for call in mock.store_memory.call_args_list:
            self.assertEqual(call[0][0], "preferences/favorite_color")


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
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8").read()
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
        mock.home_action.assert_awaited_once_with(
            "light.bombilla_mueble", "turn_on", parameters=None)

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


# ── 6b. lilith_home_action — parameters ────────────────────────────────

class TestLilithHomeActionParameters(unittest.TestCase):

    def _resolved_mock(self, state="on", brightness=None):
        mock = AsyncMock()
        mock.home_resolve.return_value = {
            "status": "resolved", "entity_id": "light.bombilla_mueble",
            "friendly_name": "Bombilla habitación",
        }
        mock.home_action.return_value = {}
        attrs = {}
        if brightness is not None:
            attrs["brightness"] = brightness
        mock.home_entity.return_value = {
            "state": state, "attributes": attrs,
        }
        return mock

    def test_turn_on_without_brightness_unchanged(self):
        mock = self._resolved_mock(state="on")
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "bombilla habitación", "action": "turn_on",
        })))
        mock.home_action.assert_awaited_once_with(
            "light.bombilla_mueble", "turn_on", parameters=None,
        )
        self.assertIn("on", resp.response["result"])

    def test_brightness_pct_100(self):
        mock = self._resolved_mock(state="on", brightness=255)
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "bombilla habitación", "action": "turn_on",
            "parameters": {"brightness_pct": 100},
        })))
        mock.home_action.assert_awaited_once_with(
            "light.bombilla_mueble", "turn_on",
            parameters={"brightness_pct": 100},
        )
        self.assertIn("100%", resp.response["result"])

    def test_brightness_pct_50(self):
        mock = self._resolved_mock(state="on", brightness=128)
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "bombilla habitación", "action": "turn_on",
            "parameters": {"brightness_pct": 50},
        })))
        mock.home_action.assert_awaited_once_with(
            "light.bombilla_mueble", "turn_on",
            parameters={"brightness_pct": 50},
        )
        self.assertIn("50%", resp.response["result"])

    def test_unknown_device_with_parameters_still_rejected(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {"status": "unknown"}
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
            "target": "luz inexistente", "action": "turn_on",
            "parameters": {"brightness_pct": 100},
        })))
        self.assertIn("Unknown", resp.response["result"])
        mock.home_action.assert_not_awaited()

    def test_target_must_not_contain_brightness_phrases(self):
        """Verify the tool declaration instructs Gemini to keep target clean."""
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8").read()
        self.assertIn("Device name only", src)
        self.assertIn("brightness_pct", src)
        self.assertIn("parameters", src)


# ── 7. Mutating set ─────────────────────────────────────────────────────

class TestMutatingSet(unittest.TestCase):

    def test_lilith_mutating_tools_in_set(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8").read()
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


# ── 10. Memory canonicalization ────────────────────────────────────────

class TestMemoryCanonicalization(unittest.TestCase):

    def test_save_memory_blocks_identity(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("save_memory", {
            "category": "identity", "key": "name", "value": "Test",
        })))
        self.assertIn("restricted", resp.response["result"])
        self.assertIn("lilith_memory_store", resp.response["result"])

    def test_save_memory_blocks_preferences(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("save_memory", {
            "category": "preferences", "key": "color", "value": "blue",
        })))
        self.assertIn("restricted", resp.response["result"])

    def test_save_memory_blocks_relationships(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("save_memory", {
            "category": "relationships", "key": "friend", "value": "Alex",
        })))
        self.assertIn("restricted", resp.response["result"])

    def test_save_memory_blocks_wishes(self):
        jarvis = _make_jarvis()
        resp = _run(jarvis._execute_tool(_fake_fc("save_memory", {
            "category": "wishes", "key": "travel", "value": "Japan",
        })))
        self.assertIn("restricted", resp.response["result"])

    def test_save_memory_allows_notes(self):
        jarvis = _make_jarvis()
        with patch("main.update_memory") as mock_update:
            resp = _run(jarvis._execute_tool(_fake_fc("save_memory", {
                "category": "notes", "key": "session_flag", "value": "debug",
            })))
        self.assertEqual(resp.response["result"], "ok")
        mock_update.assert_called_once()

    def test_save_memory_allows_projects(self):
        jarvis = _make_jarvis()
        with patch("main.update_memory") as mock_update:
            resp = _run(jarvis._execute_tool(_fake_fc("save_memory", {
                "category": "projects", "key": "current", "value": "JARVIS",
            })))
        self.assertEqual(resp.response["result"], "ok")
        mock_update.assert_called_once()

    def test_save_memory_declaration_warns_about_lilith(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8").read()
        self.assertIn("lilith_memory_store instead", src)
        self.assertIn("restricted to LILITH", src)

    def test_build_config_strips_local_personal_when_lilith_present(self):
        mock_client = AsyncMock()
        jarvis = _make_jarvis(lilith_client=mock_client)
        memory = {
            "identity": {"name": {"value": "LOCAL_NAME", "updated": "2026-01-01"}},
            "preferences": {"color": {"value": "LOCAL_BLUE", "updated": "2026-01-01"}},
            "notes": {"flag": {"value": "keep_this", "updated": "2026-01-01"}},
        }
        lilith_ctx = {
            "categories": {
                "identity": [{"key": "nombre", "value": "LILITH_NAME", "confidence": 1.0, "source": "s"}],
            },
            "total_facts": 1,
        }
        with patch("main.load_memory", return_value=memory), \
             patch("main._load_system_prompt", return_value="SYS"):
            config = jarvis._build_config(lilith_context=lilith_ctx)
        prompt = config.system_instruction
        self.assertIn("LILITH_NAME", prompt)
        self.assertNotIn("LOCAL_NAME", prompt)
        self.assertNotIn("LOCAL_BLUE", prompt)
        self.assertIn("keep_this", prompt)

    def test_build_config_keeps_local_when_lilith_absent(self):
        jarvis = _make_jarvis()
        memory = {
            "identity": {"name": {"value": "LOCAL_NAME", "updated": "2026-01-01"}},
            "notes": {"flag": {"value": "keep_this", "updated": "2026-01-01"}},
        }
        with patch("main.load_memory", return_value=memory), \
             patch("main._load_system_prompt", return_value="SYS"):
            config = jarvis._build_config(lilith_context=None)
        prompt = config.system_instruction
        self.assertIn("LOCAL_NAME", prompt)
        self.assertIn("keep_this", prompt)


# ── 11. Approval tools (JL-S003) ──────────────────────────────────────

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
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8").read()
        self.assertIn('"lilith_request_approval"', src)
        self.assertIn('"lilith_resolve_approval"', src)


class TestSearchTextDescription(unittest.TestCase):
    """Verify description field is declared in lilith_memory_store tool."""

    def test_store_tool_has_description_property(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8").read()
        self.assertIn('"description"', src)
        self.assertIn("LILITH uses this to make the fact searchable", src)

    def test_store_passes_description_to_client(self):
        mock = AsyncMock()
        mock.store_memory.return_value = {
            "key": "jarvis:pets/dog_name", "action": "created", "superseded": [],
        }
        jarvis = _make_jarvis(lilith_client=mock)
        resp = _run(jarvis._execute_tool(_fake_fc("lilith_memory_store", {
            "key": "dog_name", "value": "Caín", "category": "pets",
            "description": "nombre del perro",
        })))
        call_kwargs = mock.store_memory.call_args
        self.assertEqual(call_kwargs.kwargs.get("description"), "nombre del perro")
        self.assertIn("Caín", resp.response["result"])


if __name__ == "__main__":
    unittest.main()
