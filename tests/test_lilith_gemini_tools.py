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
from core.schedule_safety import daily_time_from_text, normalize_timezone


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
            intent="routines.create", parameters={k: v for k, v in args.items() if k != "operation"},
            request_id="jarvis:fake-lilith_routine",
            correlation_id="jarvis:fake-lilith_routine",
            idempotency_key="jarvis:routine:fake-lilith_routine",
        )

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


class TestJlA9RoutineRoutingPolicy(unittest.TestCase):
    """Regression contract for Gemini's mutually exclusive scheduling routes."""

    @staticmethod
    def _prompt_and_tools():
        jarvis = _make_jarvis()
        with patch("main.load_memory", return_value={}), \
             patch("main._load_system_prompt", return_value="SYS"):
            config = jarvis._build_config(lilith_context=None)
        tools = {item["name"]: item for item in jarvis.tool_declarations}
        live_names = {
            declaration.name
            for tool in config.tools
            for declaration in (tool.function_declarations or [])
        }
        return config.system_instruction, tools, live_names

    def test_a_immediate_light_routes_only_to_home_action(self):
        prompt, tools, _ = self._prompt_and_tools()
        self.assertIn('"Enciende la bombilla" -> lilith_home_action.', prompt)
        self.assertIn("immediate action", tools["lilith_home_action"]["description"])

    def test_b_one_future_occurrence_routes_to_reminder(self):
        prompt, tools, _ = self._prompt_and_tools()
        self.assertIn('"Recuérdame hoy a las 21:00 encender la bombilla" -> reminder.', prompt)
        self.assertIn("ONE-TIME", tools["reminder"]["description"])

    def test_c_daily_action_routes_to_lilith_routine(self):
        prompt, tools, _ = self._prompt_and_tools()
        self.assertIn('"Todos los días a las 21:00 enciende la bombilla" -> lilith_routine create only.', prompt)
        self.assertIn("todos los días", tools["lilith_routine"]["description"])

    def test_d_explicit_routine_routes_to_lilith_routine(self):
        prompt, _, _ = self._prompt_and_tools()
        self.assertIn('"Crea una rutina para encender la bombilla cada día a las 21:00" -> lilith_routine create only.', prompt)

    def test_e_recurring_request_forbids_immediate_home_side_effect(self):
        prompt, tools, _ = self._prompt_and_tools()
        self.assertIn("Never call lilith_home_action as a side effect", prompt)
        self.assertIn("do NOT call this tool", tools["lilith_home_action"]["description"])

    def test_f_recurring_request_forbids_reminder_substitution(self):
        prompt, tools, _ = self._prompt_and_tools()
        self.assertIn("Never replace a recurring routine with reminder", prompt)
        self.assertIn("Never use for recurring", tools["reminder"]["description"])

    def test_g_incomplete_recurring_request_requires_clarification(self):
        prompt, tools, _ = self._prompt_and_tools()
        self.assertIn("Ask only when recurrence, time, target, or action is genuinely", prompt)
        self.assertIn("Ask only when time, recurrence, target, or action is genuinely ambiguous", tools["lilith_routine"]["description"])

    def test_windows_live_config_contains_current_routine_tool(self):
        _, tools, live_names = self._prompt_and_tools()
        self.assertIn("lilith_routine", tools)
        self.assertIn("lilith_routine", live_names)
        self.assertEqual(
            tools["lilith_routine"],
            next(item for item in TOOL_DECLARATIONS if item["name"] == "lilith_routine"),
        )


class TestJlA9ScheduleExecutionGuard(unittest.TestCase):
    """The side-effect boundary must not trust Gemini's selected tool."""

    @staticmethod
    def _home_client():
        client = AsyncMock()
        client.home_resolve.return_value = {
            "status": "resolved", "entity_id": "light.bombilla_mueble",
            "friendly_name": "Bombilla del mueble",
        }
        client.home_action.return_value = {}
        client.home_entity.return_value = {"state": "on"}
        client.command_submit.return_value = {
            "status": "completed", "correlation_id": "guard-corr", "response": {"routine_id": 31},
        }
        return client

    def test_a_immediate_home_action_is_unchanged(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("Enciende la bombilla", "voice")
        _run(jarvis._execute_tool_batch([_fake_fc("lilith_home_action", {
            "target": "bombilla", "action": "turn_on", "parameters": {"transition": 0},
        })]))
        client.home_action.assert_awaited_once_with(
            "light.bombilla_mueble", "turn_on", parameters={"transition": 0})
        client.command_submit.assert_not_awaited()

    def test_b_one_shot_reminder_is_unchanged(self):
        jarvis = _make_jarvis()
        jarvis._begin_schedule_turn("Recuérdame hoy a las 21:00 encender la bombilla", "voice")
        with patch("main.reminder", return_value="Reminder set") as action:
            _run(jarvis._execute_tool_batch([_fake_fc("reminder", {
                "date": "2026-10-06", "time": "21:00", "message": "Encender bombilla",
            })]))
        action.assert_called_once()

    def test_c_recurring_wrong_home_call_becomes_routine_before_side_effect(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("Todos los días a las 21:00 enciende la bombilla", "voice")
        _run(jarvis._execute_tool_batch([_fake_fc("lilith_home_action", {
            "target": "bombilla", "action": "turn_on",
        })]))
        client.home_action.assert_not_awaited()
        self.assertEqual(client.command_submit.await_args.kwargs["intent"], "routines.create")
        params = client.command_submit.await_args.kwargs["parameters"]
        self.assertEqual(params["schedule"], {"hour": 21, "minute": 0})
        self.assertEqual(params["action_parameters"]["entity_id"], "light.bombilla_mueble")

    def test_d_explicit_routine_reaches_existing_routine_tool(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("Crea una rutina para encender la bombilla cada día a las 21:00", "voice")
        args = {"operation": "create", "name": "Bombilla", "schedule_type": "daily",
                "schedule": {"hour": 21, "minute": 0}, "timezone": "Europe/Madrid",
                "action_intent": "home.action",
                "action_parameters": {"entity_id": "light.bombilla_mueble", "action": "turn_on"}}
        _run(jarvis._execute_tool_batch([_fake_fc("lilith_routine", args)]))
        self.assertEqual(client.command_submit.await_args.kwargs["intent"], "routines.create")

    def test_e_recurring_batch_never_executes_home_action(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("Todos los días a las nueve de la noche enciende la bombilla del mueble", "voice")
        routine = {"operation": "create", "name": "Bombilla", "schedule_type": "daily",
                   "schedule": {"hour": 21, "minute": 0}, "timezone": "Europe/Madrid",
                   "action_intent": "home.action",
                   "action_parameters": {"entity_id": "light.bombilla_mueble", "action": "turn_on"}}
        with patch("builtins.print") as output:
            _run(jarvis._execute_tool_batch([
                _fake_fc("lilith_home_action", {"target": "bombilla del mueble", "action": "turn_on"}),
                _fake_fc("lilith_routine", routine),
            ]))
        client.home_action.assert_not_awaited()
        self.assertEqual(client.command_submit.await_count, 1)
        console = " ".join(str(call) for call in output.call_args_list)
        self.assertIn("lilith_routine", console)
        self.assertNotIn("lilith_home_action", console)
        self.assertNotIn("reminder", console)

    def test_f_recurring_batch_never_executes_reminder(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("Todos los días a las 21:00 enciende la bombilla", "voice")
        routine = {"operation": "create", "name": "Bombilla", "schedule_type": "daily",
                   "schedule": {"hour": 21, "minute": 0}, "timezone": "Europe/Madrid",
                   "action_intent": "home.action",
                   "action_parameters": {"entity_id": "light.bombilla_mueble", "action": "turn_on"}}
        with patch("main.reminder") as action:
            _run(jarvis._execute_tool_batch([
                _fake_fc("reminder", {"time": "21:00", "message": "Encender bombilla"}),
                _fake_fc("lilith_routine", routine),
            ]))
        action.assert_not_called()
        self.assertEqual(client.command_submit.await_count, 1)

    def test_g_incomplete_recurring_request_clarifies_with_zero_side_effects(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("Todos los días enciende la bombilla", "voice")
        responses = _run(jarvis._execute_tool_batch([_fake_fc("lilith_home_action", {
            "target": "bombilla", "action": "turn_on",
        })]))
        self.assertIn("incomplete", responses[0].response["result"])
        client.home_action.assert_not_awaited()
        client.command_submit.assert_not_awaited()

    def test_h_immediate_home_parameters_remain_intact(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("Enciende la bombilla al cincuenta por ciento", "voice")
        _run(jarvis._execute_tool_batch([_fake_fc("lilith_home_action", {
            "target": "bombilla", "action": "turn_on", "parameters": {"brightness_pct": 50},
        })]))
        client.home_action.assert_awaited_once_with(
            "light.bombilla_mueble", "turn_on", parameters={"brightness_pct": 50})

    def test_i_missing_current_turn_blocks_home_and_reminder(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._last_input_transcript = "Enciende la bombilla"
        jarvis._last_input_transcript_at = main.time.monotonic()
        with patch("main.reminder") as reminder_action:
            responses = _run(jarvis._execute_tool_batch([
                _fake_fc("lilith_home_action", {"target": "bombilla", "action": "turn_on"}),
                _fake_fc("reminder", {"time": "21:00", "message": "Encender bombilla"}),
            ]))
        self.assertTrue(all("no safe association" in item.response["result"] for item in responses))
        client.home_action.assert_not_awaited()
        reminder_action.assert_not_called()

    def test_j_function_call_id_cannot_be_reused_by_a_later_turn(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        call = _fake_fc("lilith_home_action", {"target": "bombilla", "action": "turn_on"})
        jarvis._begin_schedule_turn("Enciende la bombilla", "voice")
        _run(jarvis._execute_tool_batch([call]))
        jarvis._begin_schedule_turn("Enciende la bombilla", "voice")
        response = _run(jarvis._execute_tool_batch([call]))[0]
        self.assertIn("another turn", response.response["result"])
        self.assertEqual(client.home_action.await_count, 1)

    def test_k_digit_nine_at_night_normalizes_to_2100(self):
        self.assertEqual(
            daily_time_from_text("todos los días a las 9 de la noche"),
            (21, 0),
        )

    def test_l_written_nine_at_night_normalizes_to_2100(self):
        self.assertEqual(
            daily_time_from_text("cada día a las nueve de la noche"),
            (21, 0),
        )

    def test_m_madrid_timezone_aliases_normalize(self):
        for value in ("Madrid", "hora de Madrid", "mi zona horaria", None):
            self.assertEqual(normalize_timezone(value), "Europe/Madrid")

    def test_n_full_digit_request_builds_valid_create_payload_only(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        text = "Todos los días a las 9 de la noche enciende la bombilla del mueble."
        jarvis._begin_schedule_turn(text, "voice")
        with patch("main.reminder") as reminder_action:
            _run(jarvis._execute_tool_batch([_fake_fc("lilith_home_action", {
                "target": "bombilla del mueble", "action": "turn_on",
            })]))
        kwargs = client.command_submit.await_args.kwargs
        self.assertEqual(kwargs["intent"], "routines.create")
        self.assertEqual(kwargs["parameters"]["schedule_type"], "daily")
        self.assertEqual(kwargs["parameters"]["schedule"], {"hour": 21, "minute": 0})
        self.assertEqual(kwargs["parameters"]["timezone"], "Europe/Madrid")
        self.assertEqual(kwargs["parameters"]["action_intent"], "home.action")
        client.home_action.assert_not_awaited()
        reminder_action.assert_not_called()

    def test_o_routine_tool_normalizes_madrid_before_client(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        text = "Todos los días a las 9 de la noche enciende la bombilla del mueble."
        jarvis._begin_schedule_turn(text, "voice")
        args = {
            "operation": "create", "name": "Bombilla habitación",
            "schedule_type": "daily", "schedule": {"hour": 9, "minute": 0},
            "timezone": "Madrid", "action_intent": "home.action",
            "action_parameters": {"target": "bombilla del mueble", "action": "turn_on"},
        }
        _run(jarvis._execute_tool_batch([_fake_fc("lilith_routine", args)]))
        params = client.command_submit.await_args.kwargs["parameters"]
        self.assertEqual(params["schedule"], {"hour": 21, "minute": 0})
        self.assertEqual(params["timezone"], "Europe/Madrid")
        self.assertEqual(params["action_parameters"]["entity_id"], "light.bombilla_mueble")

    def test_p_ambiguous_nine_requests_clarification_without_effect(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn(
            "Todos los días a las nueve enciende la bombilla del mueble.", "voice"
        )
        with patch("main.reminder") as reminder_action:
            response = _run(jarvis._execute_tool_batch([_fake_fc("lilith_home_action", {
                "target": "bombilla del mueble", "action": "turn_on",
            })]))[0]
        self.assertIn("incomplete", response.response["result"])
        client.command_submit.assert_not_awaited()
        client.home_action.assert_not_awaited()
        reminder_action.assert_not_called()

    def test_q_confirmed_followup_uses_session_bound_pending_recurring_intent(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn(
            "Todos los días a las 9 de la noche enciende la bombilla del mueble.", "voice"
        )
        jarvis._begin_schedule_turn("Sí, 21:00 hora de Madrid.", "voice")
        _run(jarvis._execute_tool_batch([_fake_fc("lilith_routine", {
            "operation": "create", "name": "Bombilla habitación",
            "schedule_type": "daily", "schedule": {"hour": 21, "minute": 0},
            "timezone": "Madrid", "action_intent": "home.action",
            "action_parameters": {"target": "bombilla del mueble", "action": "turn_on"},
        })]))
        self.assertEqual(client.command_submit.await_count, 1)
        client.home_action.assert_not_awaited()

    def _assert_read_only_routine_allowed(self, text, operation, **args):
        client = self._home_client()
        client.command_submit.return_value = {
            "status": "completed", "correlation_id": "read-only-corr",
            "response": {"count": 1, "routines": [{"routine_id": 4, "name": "Bombilla"}]},
        }
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn(text, "voice")
        with patch("main.reminder") as reminder_action:
            response = _run(jarvis._execute_tool_batch([
                _fake_fc("lilith_routine", {"operation": operation, **args})
            ]))[0]
        self.assertIn("confirmed routine", response.response["result"])
        self.assertEqual(client.command_submit.await_args.kwargs["intent"], f"routines.{operation}")
        client.home_action.assert_not_awaited()
        reminder_action.assert_not_called()
        return jarvis, client

    def test_r_list_what_routines_do_i_have_is_allowed(self):
        self._assert_read_only_routine_allowed("¿Qué rutinas tengo?", "list")

    def test_s_list_my_scheduled_routines_is_allowed(self):
        self._assert_read_only_routine_allowed("Dime mis rutinas programadas.", "list")

    def test_t_history_is_allowed_without_schedule_semantics(self):
        self._assert_read_only_routine_allowed(
            "Enséñame el historial de esta rutina.", "history", routine_id=4,
        )

    def test_t2_get_is_allowed_without_schedule_semantics(self):
        self._assert_read_only_routine_allowed(
            "Enséñame esta rutina.", "get", routine_id=4,
        )

    def test_u_read_only_duplicate_function_call_id_remains_blocked(self):
        client = self._home_client()
        client.command_submit.return_value = {
            "status": "completed", "correlation_id": "read-only-corr",
            "response": {"count": 0, "routines": []},
        }
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn("¿Qué rutinas tengo?", "voice")
        call = _fake_fc("lilith_routine", {"operation": "list"})
        responses = _run(jarvis._execute_tool_batch([call, call]))
        self.assertEqual(client.command_submit.await_count, 1)
        self.assertIn("duplicate blocked", responses[1].response["result"])
        client.home_action.assert_not_awaited()

    def test_v_partial_time_followup_completes_same_pending_routine(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn(
            "Todos los días enciende la bombilla del mueble.", "voice"
        )
        self.assertEqual(jarvis._pending_routine.pending_clarification, {"time"})

        jarvis._begin_schedule_turn("A las nueve de la noche, hora de Madrid.", "voice")
        _run(jarvis._execute_tool_batch([_fake_fc("lilith_routine", {
            "operation": "create",
        })]))

        params = client.command_submit.await_args.kwargs["parameters"]
        self.assertEqual(params["schedule"], {"hour": 21, "minute": 0})
        self.assertEqual(params["timezone"], "Europe/Madrid")
        self.assertEqual(params["action_parameters"]["entity_id"], "light.bombilla_mueble")
        self.assertEqual(params["action_parameters"]["action"], "turn_on")
        self.assertIsNone(jarvis._pending_routine)

    def test_w_lifecycle_writes_do_not_require_recurring_words(self):
        cases = (
            ("Actualiza esta rutina.", "update", {"routine_id": 4, "name": "Nueva"}),
            ("Activa esta rutina.", "enable", {"routine_id": 4}),
            ("Desactiva esta rutina.", "disable", {"routine_id": 4}),
            ("Borra esta rutina.", "delete", {"routine_id": 4}),
        )
        for text, operation, args in cases:
            with self.subTest(operation=operation):
                client = self._home_client()
                jarvis = _make_jarvis(lilith_client=client)
                jarvis._begin_schedule_turn(text, "voice")
                with patch("main.reminder") as reminder_action:
                    response = _run(jarvis._execute_tool_batch([_fake_fc(
                        "lilith_routine", {"operation": operation, **args}
                    )]))[0]
                self.assertIn("confirmed routine", response.response["result"])
                self.assertEqual(
                    client.command_submit.await_args.kwargs["intent"],
                    f"routines.{operation}",
                )
                client.home_action.assert_not_awaited()
                reminder_action.assert_not_called()

    def test_x_duplicate_create_with_different_call_ids_executes_once(self):
        client = self._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        jarvis._begin_schedule_turn(
            "Todos los días a las nueve de la noche enciende la bombilla del mueble.",
            "voice",
        )
        calls = [
            _fake_fc("lilith_routine", {"operation": "create"}),
            _fake_fc("lilith_routine", {"operation": "create"}),
        ]
        calls[1].id = "different-call-id"
        responses = _run(jarvis._execute_tool_batch(calls))
        self.assertEqual(client.command_submit.await_count, 1)
        self.assertIn("duplicate", responses[1].response["result"])


class TestGeminiLiveSchedulePath(unittest.TestCase):
    """Exercise the actual receive -> FunctionCall -> tool-response path."""

    class LiveSession:
        def __init__(self, jarvis, call):
            self.jarvis = jarvis
            self.call = call
            self.responses = []

        async def receive(self):
            transcript = SimpleNamespace(
                text="Todos los días a las nueve de la noche enciende la bombilla del mueble."
            )
            server_content = SimpleNamespace(
                output_transcription=None, input_transcription=transcript,
                turn_complete=False,
            )
            yield SimpleNamespace(
                server_content=server_content, tool_call=SimpleNamespace(function_calls=[self.call])
            )

        async def send_tool_response(self, *, function_responses):
            self.responses.extend(function_responses)
            self.jarvis._shutdown_requested.set()

    def _run_wrong_live_call(self, name, args):
        client = TestJlA9ScheduleExecutionGuard._home_client()
        jarvis = _make_jarvis(lilith_client=client)
        session = self.LiveSession(jarvis, _fake_fc(name, args))
        jarvis.session = session
        _run(jarvis._receive_audio())
        return client, session

    def test_live_recurring_request_cannot_execute_home_action(self):
        client, session = self._run_wrong_live_call(
            "lilith_home_action", {"target": "bombilla del mueble", "action": "turn_on"}
        )
        client.home_action.assert_not_awaited()
        self.assertEqual(client.command_submit.await_count, 1)
        self.assertEqual(len(session.responses), 1)

    def test_live_recurring_request_cannot_execute_reminder(self):
        with patch("main.reminder") as reminder_action:
            client, session = self._run_wrong_live_call(
                "reminder", {"time": "21:00", "message": "Encender bombilla del mueble"}
            )
        reminder_action.assert_not_called()
        self.assertEqual(client.command_submit.await_count, 1)
        self.assertEqual(len(session.responses), 1)


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

    def test_readback_waits_for_expected_state_instead_of_reporting_stale_state(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {
            "status": "resolved", "entity_id": "light.x", "friendly_name": "X",
        }
        mock.home_action.return_value = {}
        mock.home_entity.side_effect = [{"state": "off"}, {"state": "on"}]
        jarvis = _make_jarvis(lilith_client=mock)
        with patch("main.asyncio.sleep", new=AsyncMock()) as pause:
            resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
                "target": "X", "action": "turn_on",
            })))
        self.assertIn("Verified state: on", resp.response["result"])
        self.assertEqual(mock.home_entity.await_count, 2)
        pause.assert_awaited_once_with(0.25)

    def test_readback_never_claims_verification_when_state_stays_stale(self):
        mock = AsyncMock()
        mock.home_resolve.return_value = {
            "status": "resolved", "entity_id": "light.x", "friendly_name": "X",
        }
        mock.home_action.return_value = {}
        mock.home_entity.return_value = {"state": "off"}
        jarvis = _make_jarvis(lilith_client=mock)
        with patch("main.asyncio.sleep", new=AsyncMock()):
            resp = _run(jarvis._execute_tool(_fake_fc("lilith_home_action", {
                "target": "X", "action": "turn_on",
            })))
        self.assertIn("not verified", resp.response["result"])
        self.assertNotIn("Verified state", resp.response["result"])


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
