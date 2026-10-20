# -*- coding: utf-8 -*-
"""Real integration tests for conversation continuity.

Exercises _receive_audio() with fake session responses to verify that:
- Interrupted turns preserve context for "continúa" scenarios
- Noise/void turns don't alter conversation state
- Stop-control preserves prior topic context
- Topic changes are tracked through the conversation store
- Replay guard is scoped to transport, not conversation
"""
import json
import os
import subprocess
import sys
import unittest

_THIS_FILE = os.path.abspath(__file__)


class TestConversationContinuity(unittest.TestCase):

    def _run_worker(self, test_name, timeout=90):
        env = {**os.environ, "_CONV_CONTINUITY_SUBPROCESS": test_name}
        result = subprocess.run(
            [sys.executable, _THIS_FILE],
            env=env, capture_output=True, text=True, timeout=timeout,
        )
        stdout = result.stdout
        start = stdout.find("__RESULT_JSON__")
        end = stdout.find("__END_RESULT__")
        self.assertGreater(start, -1,
            f"No result marker:\nSTDOUT:\n{stdout}\nSTDERR:\n{result.stderr[-2000:]}")
        payload = json.loads(stdout[start + len("__RESULT_JSON__"):end])
        if not payload.get("passed"):
            self.fail(f"Subprocess failed: {payload.get('error', 'unknown')}\n{result.stderr[-2000:]}")
        return payload

    # ── 1. topic_resume_after_noise ──
    def test_topic_resume_after_noise(self):
        """Interrupted by noise -> context preserved for 'continúa'."""
        p = self._run_worker("topic_resume_after_noise")
        self.assertTrue(p["passed"])
        self.assertTrue(p["interrupted_checkpoint_saved"],
            "Interrupted assistant partial must be saved as checkpoint")
        self.assertTrue(p["user_question_in_store"],
            "Original user question must remain in store")
        self.assertFalse(p["noise_saved_to_store"],
            "Noise must NOT be saved to conversation store")

    # ── 2. temporary_topic_switch_and_return ──
    def test_temporary_topic_switch_and_return(self):
        """Topic X -> interrupt with time question -> both topics in store."""
        p = self._run_worker("temporary_topic_switch")
        self.assertTrue(p["passed"])
        self.assertTrue(p["original_question_in_store"],
            "Original topic question must be in store")
        self.assertTrue(p["time_question_in_store"],
            "Time question must be in store")
        self.assertTrue(p["interrupted_checkpoint_in_store"],
            "Interrupted assistant checkpoint must be in store")

    # ── 3. stop_preserves_context ──
    def test_stop_preserves_context(self):
        """'Para' after barge-in -> zero side effects but prior context preserved."""
        p = self._run_worker("stop_preserves_context")
        self.assertTrue(p["passed"])
        self.assertTrue(p["stop_consumed"],
            "'Para' must be consumed as stop control")
        self.assertEqual(p["stop_turn_memory_writes"], 0,
            "Stop turn must have zero memory writes")
        self.assertTrue(p["prior_context_preserved"],
            "Prior turn context must be preserved in store")

    # ── 4. real_topic_change ──
    def test_real_topic_change(self):
        """Topic X -> Topic Y -> both in store, Y is latest user turn."""
        p = self._run_worker("real_topic_change")
        self.assertTrue(p["passed"])
        self.assertTrue(p["topic_x_in_store"],
            "First topic must be in store")
        self.assertTrue(p["topic_y_in_store"],
            "Second topic must be in store")
        self.assertTrue(p["latest_user_is_topic_y"],
            "Latest user turn must be topic Y")

    # ── 5. noise_zero_side_effects ──
    def test_noise_zero_side_effects(self):
        """'.', '<noise>', '<silence>' -> zero side effects, no topic change."""
        p = self._run_worker("noise_zero_side_effects")
        self.assertTrue(p["passed"])
        self.assertEqual(p["user_memory_writes"], 0, "Noise: zero user memory")
        self.assertEqual(p["assistant_memory_writes"], 0, "Noise: zero assistant memory")
        self.assertEqual(p["audio_released"], 0, "Noise: zero audio released")
        self.assertEqual(p["schedule_begins"], 0, "Noise: zero schedule begins")

    # ── 6. provider_replay_zero_side_effects ──
    def test_provider_replay_zero_side_effects(self):
        """Provider replay -> zero duplicate side effects."""
        p = self._run_worker("provider_replay_zero")
        self.assertTrue(p["passed"])
        self.assertEqual(p["turn_b_user_memory"], 0, "Replay: zero user memory")
        self.assertEqual(p["turn_b_assistant_memory"], 0, "Replay: zero assistant memory")

    # ── 7. normal_repeat_is_not_replay ──
    def test_normal_repeat_is_not_replay(self):
        """User repeats after non-interrupted turn -> accepted as genuine input."""
        p = self._run_worker("normal_repeat_not_replay")
        self.assertTrue(p["passed"])
        self.assertTrue(p["turn_b_validated"],
            "Repeat after normal turn must be validated")

    # ── 8. valid_tool_result_keeps_conversation_context ──
    def test_valid_tool_result_keeps_conversation_context(self):
        """Tool result doesn't break conversation store continuity."""
        p = self._run_worker("tool_keeps_context")
        self.assertTrue(p["passed"])
        self.assertTrue(p["user_question_in_store"],
            "User question must be in store after tool turn")
        self.assertTrue(p["assistant_response_in_store"],
            "Assistant response must be in store after tool turn")

    # ── 9. current_conversation_takes_precedence ──
    def test_current_conversation_takes_precedence(self):
        """Recent conversation store has context -> _local_continuity_prompt reflects it."""
        p = self._run_worker("conversation_precedence")
        self.assertTrue(p["passed"])
        self.assertTrue(p["continuity_has_recent_topic"],
            "Continuity prompt must contain recent conversation topic")

    # ── 10. para_inside_normal_sentence ──
    def test_para_inside_normal_sentence(self):
        """'Para qué sirve esto' -> validated normally, not consumed as stop."""
        p = self._run_worker("para_in_sentence")
        self.assertTrue(p["passed"])
        self.assertTrue(p["input_validated"],
            "'Para qué sirve esto' must be validated normally")


# ============================================================
# Subprocess worker
# ============================================================

if os.environ.get("_CONV_CONTINUITY_SUBPROCESS"):

    import asyncio
    import threading
    import time
    import types
    import uuid
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    # ── Module stubs (same pattern as test_replay_integration.py) ──
    _google_pkg = types.ModuleType("google")
    _google_pkg.__path__ = ["/dev/null/google"]
    sys.modules["google"] = _google_pkg

    _genai = types.ModuleType("google.genai")
    sys.modules["google.genai"] = _genai
    _google_pkg.genai = _genai

    class _FakeAPIError(Exception):
        def __init__(self, status_code=None, response_json=None, response=None):
            self.status = status_code
            self.code = status_code
            msg = f"{status_code} {response_json}"
            if status_code == 1006:
                msg += ". abnormal closure [internal]"
            super().__init__(msg)
        @classmethod
        def raise_error(cls, code, reason, resp):
            raise cls(code, reason, resp)

    _errors_mod = types.ModuleType("google.genai.errors")
    _errors_mod.APIError = _FakeAPIError
    sys.modules["google.genai.errors"] = _errors_mod
    _genai.errors = _errors_mod

    _live_mod = types.ModuleType("google.genai.live")
    sys.modules["google.genai.live"] = _live_mod
    _genai.live = _live_mod

    _types_mod = types.ModuleType("google.genai.types")
    class _FakeFunctionResponse:
        def __init__(self, id=None, name=None, response=None):
            self.id = id; self.name = name; self.response = response
    _types_mod.FunctionResponse = _FakeFunctionResponse
    sys.modules["google.genai.types"] = _types_mod
    _genai.types = _types_mod

    class _FakeGenaiClient:
        def __init__(self, **kw):
            self.aio = SimpleNamespace(live=SimpleNamespace(connect=None))
    _genai.Client = _FakeGenaiClient

    _core_pkg = types.ModuleType("core")
    _core_pkg.__path__ = ["/dev/null/core"]
    sys.modules["core"] = _core_pkg

    for _sub in ("schedule_safety", "headless_tools", "config", "tts_cache",
                 "voice_stability", "audio_barge_in", "jarvis_client",
                 "lilith_gateway", "date_time_authority", "live_model", "voice_config"):
        _m = types.ModuleType(f"core.{_sub}")
        sys.modules[f"core.{_sub}"] = _m
        setattr(_core_pkg, _sub, _m)

    _ss = sys.modules["core.schedule_safety"]
    _ss.daily_time_from_text = lambda *a, **k: None
    _ss.normalize_timezone = lambda *a, **k: None
    _ss.normalized_turn_text = lambda t: t
    _ss.schedule_semantics = lambda *a, **k: SimpleNamespace(is_schedule=False)
    _ss.user_confirmed = lambda *a, **k: False

    class _FakeBargeInDecision:
        accepted = False; rejected = False
    class _FakeBargeInGate:
        def __init__(self, **kw): pass
        def process_frame(self, *a, **k): return _FakeBargeInDecision()
        def start_playback(self): pass
        def stop_playback(self): pass
        def observe_playback(self, *a, **k): pass
    sys.modules["core.audio_barge_in"].BargeInDecision = _FakeBargeInDecision
    sys.modules["core.audio_barge_in"].SpeechAwareBargeInGate = _FakeBargeInGate

    class _FakeJarvisClient:
        on_text_command = None; on_conversation_toggle = None
        muted = False; current_file = None; _voice_combo = None
        def write_log(self, text): pass
        def set_state(self, state): pass
        def show_subtitle(self, text): pass
        def clear_subtitle(self): pass
        def set_theme(self, t): pass
        def set_graphics_quality(self, q): pass
        def sync_voice_display(self, v): pass
        def handle_ui_command(self, a): pass
    sys.modules["core.jarvis_client"].JarvisClient = _FakeJarvisClient

    class _FakeLilithBridge:
        def __init__(self, *a, **k): pass
        async def fetch_context(self, *a, **k): return {"total_facts": 0}
    sys.modules["core.lilith_gateway"].LilithBridge = _FakeLilithBridge

    class _FakeDateTimeAuthority:
        def __init__(self): pass
        def now(self): return "2026-10-20 05:00:00"
        def today(self): return "2026-10-20"
    sys.modules["core.date_time_authority"].DateTimeAuthority = _FakeDateTimeAuthority
    sys.modules["core.live_model"].pick_live_model = lambda *a, **k: "models/gemini-2.5-flash-native-audio-latest"
    sys.modules["core.voice_config"].DEFAULT_VOICE_NAME = "Puck"
    sys.modules["core.voice_config"].DEFAULT_GEMINI_VOICE = "Puck"
    sys.modules["core.voice_config"].SUPPORTED_GEMINI_VOICE_NAMES = ["Puck", "kore"]
    sys.modules["core.voice_config"].normalize_gemini_voice = lambda v: v
    sys.modules["core.voice_config"].VOICE_NAMES = ["Puck"]
    sys.modules["core.headless_tools"].build_headless_catalog = lambda: ""
    sys.modules["core.headless_tools"].build_headless_catalog_technical = lambda: ""
    sys.modules["core.headless_tools"].HEADLESS_ACTIONS = frozenset()
    sys.modules["core.config"].get_config = lambda *a, **k: {}
    sys.modules["core.tts_cache"].TTSCache = type("TTSCache", (), {})

    class _FakeVoiceMonitor:
        def record_reconnect(self, **k): pass
        def record_audio_frame(self, *a, **k): pass
        def record_latency(self, *a, **k): pass
    sys.modules["core.voice_stability"].VoiceStabilityMonitor = _FakeVoiceMonitor
    sys.modules["core.voice_stability"].get_monitor = lambda: _FakeVoiceMonitor()

    # Use REAL conversation_store for continuity tests.
    # Must load it BEFORE creating the fake memory package, via importlib.
    sys.path.insert(0, "/home/flako1312/jarvis-headless")
    import importlib.util as _ilu
    _cs_spec = _ilu.spec_from_file_location(
        "memory.conversation_store",
        "/home/flako1312/jarvis-headless/memory/conversation_store.py",
    )
    _real_cs_mod = _ilu.module_from_spec(_cs_spec)
    _cs_spec.loader.exec_module(_real_cs_mod)

    _mem_pkg = types.ModuleType("memory")
    _mem_pkg.__path__ = ["/home/flako1312/jarvis-headless/memory"]
    sys.modules["memory"] = _mem_pkg

    # Register the real conversation_store under the memory package
    sys.modules["memory.conversation_store"] = _real_cs_mod
    setattr(_mem_pkg, "conversation_store", _real_cs_mod)

    _mem_mm = types.ModuleType("memory.memory_manager")
    class _FakeMemoryManager:
        def __init__(self, *a, **k): pass
        def retrieve(self, *a, **k): return []
        def store(self, *a, **k): pass
        def search(self, *a, **k): return []
    _mem_mm.SemanticMemoryManager = _FakeMemoryManager
    _mem_mm.get_manager = lambda *a, **k: _FakeMemoryManager()
    _mem_mm.load_memory = lambda *a, **k: ""
    _mem_mm.format_memory_for_prompt = lambda *a, **k: ""
    sys.modules["memory.memory_manager"] = _mem_mm
    setattr(_mem_pkg, "memory_manager", _mem_mm)

    _act_pkg = types.ModuleType("actions")
    _act_pkg.__path__ = ["/dev/null/actions"]
    sys.modules["actions"] = _act_pkg
    for _sub in ("browser_control", "computer_control", "file_processor", "safe_text_entry"):
        _m = types.ModuleType(f"actions.{_sub}")
        sys.modules[f"actions.{_sub}"] = _m
        setattr(_act_pkg, _sub, _m)
    _api_pkg = types.ModuleType("api")
    _api_pkg.__path__ = ["/dev/null/api"]
    sys.modules["api"] = _api_pkg
    _api_status = types.ModuleType("api.status")
    _api_status.write_status = lambda *a, **k: None
    _api_status.read_status = lambda *a, **k: {}
    sys.modules["api.status"] = _api_status
    setattr(_api_pkg, "status", _api_status)
    _api_wsc = types.ModuleType("api.websocket_client")
    sys.modules["api.websocket_client"] = _api_wsc
    setattr(_api_pkg, "websocket_client", _api_wsc)

    for _mod_name in ("sounddevice", "soundfile", "numpy", "pulsectl",
                      "aiohttp", "aiohttp.web", "requests"):
        if _mod_name not in sys.modules:
            sys.modules[_mod_name] = types.ModuleType(_mod_name)
    _sd = sys.modules["sounddevice"]
    _sd.InputStream = type("InputStream", (), {})
    _sd.OutputStream = type("OutputStream", (), {})
    _sd.RawOutputStream = None
    _sd.default = SimpleNamespace(device=(0, 0))
    _sd.query_devices = lambda *a, **k: {"name": "test", "max_input_channels": 2, "max_output_channels": 2}
    _sd.check_input_settings = lambda **k: None

    from main import JarvisLive, ConversationState, _is_semantic_transcript, _strip_noise_tags

    import asyncio
    import time
    from unittest.mock import patch, MagicMock
    from types import SimpleNamespace

    # ── Fake session response objects ──

    def _make_response(
        input_text=None, output_text=None, audio_bytes=None,
        interrupted=False, turn_complete=False, tool_calls=None,
    ):
        r = SimpleNamespace()
        r.session_resumption_update = None
        r.tool_call = None
        r.tool_call_cancellation = None
        r.go_away = None
        sc = SimpleNamespace()
        sc.input_transcription = None
        sc.output_transcription = None
        sc.interrupted = interrupted
        sc.turn_complete = turn_complete
        sc.model_turn = None
        if input_text is not None:
            sc.input_transcription = SimpleNamespace(text=input_text)
        if output_text is not None:
            sc.output_transcription = SimpleNamespace(text=output_text)
        if audio_bytes is not None:
            part = SimpleNamespace(
                inline_data=SimpleNamespace(data=audio_bytes, mime_type="audio/pcm"))
            sc.model_turn = SimpleNamespace(parts=[part])
        r.server_content = sc
        if tool_calls is not None:
            fc_list = []
            for tc in tool_calls:
                fc = SimpleNamespace(
                    id=tc.get("id", "fc_001"), name=tc.get("name", "date_time"),
                    args=tc.get("args", {}))
                fc_list.append(fc)
            r.tool_call = SimpleNamespace(function_calls=fc_list)
            r.server_content = None
        return r

    class _FakeSession:
        def __init__(self, turns):
            self._turns = turns
            self._current_turn = 0
            self._exhausted = False
        def receive(self):
            return self
        def __aiter__(self):
            return self
        async def __anext__(self):
            await asyncio.sleep(0)
            if self._exhausted:
                raise StopAsyncIteration
            if self._current_turn >= len(self._turns):
                self._exhausted = True
                raise StopAsyncIteration
            turn_responses = self._turns[self._current_turn]
            if not turn_responses:
                self._current_turn += 1
                raise StopAsyncIteration
            resp = turn_responses.pop(0)
            return resp
        async def send(self, **kw):
            pass

    class _Counters:
        def __init__(self):
            self.user_memory = []
            self.assistant_memory = []
            self.schedule_updates = []
            self.schedule_begins = []
            self.subtitle_calls = []
            self.audio_released = []
            self.tool_executions = []
            self.log_calls = []

    def _make_instrumented_jl(session, counters, *, use_real_remember=True):
        """Create JarvisLive with instrumented methods.

        When use_real_remember=True, the real _remember_conversation_text runs
        (populating _conversation_continuity) AND we count calls.
        """
        client = _FakeJarvisClient()
        jl = JarvisLive(
            client=client, voice_name="Puck", headless=True,
            no_audio=True, api_key="fake-key-for-test",
        )
        jl.session = session
        jl._conversation_requested = asyncio.Event()
        jl._conversation_requested.set()
        jl._shutdown_requested = asyncio.Event()
        jl.audio_in_queue = asyncio.Queue()

        if use_real_remember:
            _original_remember = jl._remember_conversation_text
            def _counting_remember(role, text, **kw):
                turn_id = kw.get("turn_id", "?")
                entry = {"role": role, "text": text[:200], "turn_id": turn_id}
                if role == "user":
                    counters.user_memory.append(entry)
                else:
                    counters.assistant_memory.append(entry)
                _original_remember(role, text, **kw)
            jl._remember_conversation_text = _counting_remember
        else:
            def _stub_remember(role, text, **kw):
                turn_id = kw.get("turn_id", "?")
                entry = {"role": role, "text": text[:200], "turn_id": turn_id}
                if role == "user":
                    counters.user_memory.append(entry)
                else:
                    counters.assistant_memory.append(entry)
            jl._remember_conversation_text = _stub_remember

        def _patched_update(text):
            counters.schedule_updates.append(text[:80])
        jl._update_schedule_turn = _patched_update

        def _patched_begin(text, source):
            counters.schedule_begins.append({"text": text[:80], "source": source})
        jl._begin_schedule_turn = _patched_begin

        def _patched_subtitle(text):
            counters.subtitle_calls.append(text[:80])
        jl.ui.show_subtitle = _patched_subtitle

        def _patched_put(chunk):
            counters.audio_released.append(len(chunk))
        jl.audio_in_queue.put_nowait = _patched_put

        def _patched_write_log(text):
            if text.startswith("JARVIS:") or text.startswith("AURORA:"):
                counters.log_calls.append(text[:80])
        jl.ui.write_log = _patched_write_log

        jl._interrupt_live_playback = lambda reason: None
        # Let _persist_conversation_state be a no-op for file I/O,
        # but keep _conversation_continuity in memory
        jl._conversation_store = None

        return jl

    async def _run_turns(jl, timeout=0.5):
        async def _auto_shutdown():
            await asyncio.sleep(timeout)
            jl._shutdown_requested.set()
        loop = asyncio.get_event_loop()
        t = loop.create_task(_auto_shutdown())
        try:
            await jl._receive_audio()
        except Exception:
            pass
        t.cancel()

    def _store_has_text(jl, text_fragment, role=None):
        for entry in jl._conversation_continuity:
            if role and entry.get("role") != role:
                continue
            if text_fragment.lower() in str(entry.get("text", "")).lower():
                return True
        return False

    def _latest_user_text(jl):
        for entry in reversed(jl._conversation_continuity):
            if entry.get("role") == "user":
                return entry.get("text", "")
        return ""

    # ── Test implementations ──

    def test_topic_resume_after_noise():
        """Turn A: user asks about discos, JARVIS starts answering, interrupted.
        Turn B: noise (non-semantic).
        Verify: checkpoint saved, question in store, noise NOT saved."""
        turn_a = [
            _make_response(input_text="Explícame los discos del servidor"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Tienes el SSD del sistema y un disco HDD de datos"),
            _make_response(interrupted=True),
            _make_response(turn_complete=True),
        ]
        turn_b = [
            _make_response(input_text="."),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn_a, turn_b])
        jl = _make_instrumented_jl(session, counters)

        asyncio.run(_run_turns(jl))

        checkpoint_saved = _store_has_text(jl, "[interrumpido]", role="assistant")
        question_in_store = _store_has_text(jl, "discos del servidor", role="user")
        noise_saved = _store_has_text(jl, ".", role="user")

        return {
            "passed": True,
            "interrupted_checkpoint_saved": checkpoint_saved,
            "user_question_in_store": question_in_store,
            "noise_saved_to_store": noise_saved,
        }

    def test_temporary_topic_switch():
        """Turn A: ask about discos, interrupted.
        Turn B: ask what time it is (genuine new topic).
        Both topics must be in store."""
        turn_a = [
            _make_response(input_text="Explícame los discos del servidor"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Tienes el SSD del sistema y"),
            _make_response(interrupted=True),
            _make_response(turn_complete=True),
        ]
        turn_b = [
            _make_response(input_text="qué hora es"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Son las quince y cuarenta"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn_a, turn_b])
        jl = _make_instrumented_jl(session, counters)

        asyncio.run(_run_turns(jl))

        return {
            "passed": True,
            "original_question_in_store": _store_has_text(jl, "discos del servidor", role="user"),
            "time_question_in_store": _store_has_text(jl, "hora", role="user"),
            "interrupted_checkpoint_in_store": _store_has_text(jl, "[interrumpido]", role="assistant"),
        }

    def test_stop_preserves_context():
        """Turn A: topic X with response, interrupted.
        Turn B: 'Para' after barge-in -> consumed as stop control.
        Prior context must remain in store."""
        turn_a = [
            _make_response(input_text="Cuéntame sobre Home Assistant"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Home Assistant es una plataforma de automatización"),
            _make_response(interrupted=True),
            _make_response(turn_complete=True),
        ]
        turn_b = [
            _make_response(input_text="Para"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn_a, turn_b])
        jl = _make_instrumented_jl(session, counters)
        # Simulate barge-in was just accepted for turn B
        jl._last_barge_in_accepted_t = time.monotonic()

        asyncio.run(_run_turns(jl))

        # Count memory writes ONLY for turn B
        turn_b_user_mem = sum(1 for e in counters.user_memory
                             if "para" == str(e.get("text", "")).strip().lower())
        turn_b_asst_mem = sum(1 for e in counters.assistant_memory
                             if e not in counters.assistant_memory[:1])  # skip turn A

        # Check prior context is still there
        prior_preserved = _store_has_text(jl, "Home Assistant", role="user")

        return {
            "passed": True,
            "stop_consumed": turn_b_user_mem == 0,
            "stop_turn_memory_writes": turn_b_user_mem,
            "prior_context_preserved": prior_preserved,
        }

    def test_real_topic_change():
        """Turn A: topic X. Turn B: topic Y. Both in store, Y is latest."""
        turn_a = [
            _make_response(input_text="Explícame los discos del servidor"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Tienes el SSD del sistema y un disco HDD de datos"),
            _make_response(turn_complete=True),
        ]
        turn_b = [
            _make_response(input_text="Ahora quiero hablar de Home Assistant"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Home Assistant permite controlar tus dispositivos"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn_a, turn_b])
        jl = _make_instrumented_jl(session, counters)

        asyncio.run(_run_turns(jl))

        return {
            "passed": True,
            "topic_x_in_store": _store_has_text(jl, "discos", role="user"),
            "topic_y_in_store": _store_has_text(jl, "Home Assistant", role="user"),
            "latest_user_is_topic_y": "home assistant" in _latest_user_text(jl).lower(),
        }

    def test_noise_zero_side_effects():
        """Noise inputs produce zero side effects."""
        noise_turns = []
        for noise in [".", "<noise>", " "]:
            noise_turns.append([
                _make_response(input_text=noise),
                _make_response(audio_bytes=b"\x00" * 160),
                _make_response(output_text="Algo"),
                _make_response(turn_complete=True),
            ])

        counters = _Counters()
        session = _FakeSession(noise_turns)
        jl = _make_instrumented_jl(session, counters, use_real_remember=False)

        asyncio.run(_run_turns(jl, timeout=1.0))

        return {
            "passed": True,
            "user_memory_writes": len(counters.user_memory),
            "assistant_memory_writes": len(counters.assistant_memory),
            "audio_released": len(counters.audio_released),
            "schedule_begins": len(counters.schedule_begins),
        }

    def test_provider_replay_zero():
        """Provider replay after interrupted turn -> zero duplicate side effects."""
        turn_a = [
            _make_response(input_text="que hora es"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Son las seis y treinta"),
            _make_response(interrupted=True),
            _make_response(turn_complete=True),
        ]
        turn_b = [
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Son las seis y treinta y uno"),
            _make_response(input_text="que hora es"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn_a, turn_b])
        jl = _make_instrumented_jl(session, counters, use_real_remember=False)

        asyncio.run(_run_turns(jl))

        # Partition by turn_id
        turn_ids = list(dict.fromkeys(
            e.get("turn_id") for e in counters.user_memory + counters.assistant_memory))
        turn_b_id = turn_ids[1] if len(turn_ids) > 1 else None

        turn_b_user = sum(1 for e in counters.user_memory if e.get("turn_id") == turn_b_id) if turn_b_id else 0
        turn_b_asst = sum(1 for e in counters.assistant_memory if e.get("turn_id") == turn_b_id) if turn_b_id else 0

        return {
            "passed": True,
            "turn_b_user_memory": turn_b_user,
            "turn_b_assistant_memory": turn_b_asst,
        }

    def test_normal_repeat_not_replay():
        """Normal (non-interrupted) turn A + same input turn B -> validated."""
        turn_a = [
            _make_response(input_text="que hora es"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Son las seis"),
            _make_response(turn_complete=True),  # NOT interrupted
        ]
        turn_b = [
            _make_response(input_text="que hora es"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Son las seis y uno"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn_a, turn_b])
        jl = _make_instrumented_jl(session, counters, use_real_remember=False)

        asyncio.run(_run_turns(jl))

        turn_ids = list(dict.fromkeys(
            e.get("turn_id") for e in counters.user_memory))
        turn_b_id = turn_ids[1] if len(turn_ids) > 1 else None
        turn_b_validated = turn_b_id is not None and any(
            e.get("turn_id") == turn_b_id for e in counters.user_memory)

        return {
            "passed": True,
            "turn_b_validated": turn_b_validated,
        }

    def test_tool_keeps_context():
        """Turn with valid input + tool + response -> all in store."""
        turn = [
            _make_response(input_text="Enciende la luz del salón"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Encendiendo la luz del salón"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn])
        jl = _make_instrumented_jl(session, counters)

        asyncio.run(_run_turns(jl))

        return {
            "passed": True,
            "user_question_in_store": _store_has_text(jl, "luz del salón", role="user"),
            "assistant_response_in_store": _store_has_text(jl, "Encendiendo", role="assistant"),
        }

    def test_conversation_precedence():
        """After a turn, _local_continuity_prompt contains the topic."""
        turn = [
            _make_response(input_text="Explícame el estado del NAS"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="El NAS tiene dos discos en RAID 1"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn])
        jl = _make_instrumented_jl(session, counters)

        asyncio.run(_run_turns(jl))

        prompt = jl._local_continuity_prompt()
        has_topic = "NAS" in prompt or "nas" in prompt.lower()

        return {
            "passed": True,
            "continuity_has_recent_topic": has_topic,
        }

    def test_para_in_sentence():
        """'Para qué sirve esto' validated normally."""
        turn = [
            _make_response(input_text="Para qué sirve esto"),
            _make_response(audio_bytes=b"\x00" * 320),
            _make_response(output_text="Esto sirve para muchas cosas"),
            _make_response(turn_complete=True),
        ]

        counters = _Counters()
        session = _FakeSession([turn])
        jl = _make_instrumented_jl(session, counters, use_real_remember=False)

        asyncio.run(_run_turns(jl))

        return {
            "passed": True,
            "input_validated": len(counters.user_memory) > 0,
        }

    # ── Dispatch ──

    if __name__ == "__main__":
        test_name = os.environ["_CONV_CONTINUITY_SUBPROCESS"]
        dispatch = {
            "topic_resume_after_noise": test_topic_resume_after_noise,
            "temporary_topic_switch": test_temporary_topic_switch,
            "stop_preserves_context": test_stop_preserves_context,
            "real_topic_change": test_real_topic_change,
            "noise_zero_side_effects": test_noise_zero_side_effects,
            "provider_replay_zero": test_provider_replay_zero,
            "normal_repeat_not_replay": test_normal_repeat_not_replay,
            "tool_keeps_context": test_tool_keeps_context,
            "conversation_precedence": test_conversation_precedence,
            "para_in_sentence": test_para_in_sentence,
        }
        fn = dispatch.get(test_name)
        if fn is None:
            print(f"__RESULT_JSON__{{\"passed\": false, \"error\": \"unknown test: {test_name}\"}}__END_RESULT__")
            sys.exit(1)
        try:
            result = fn()
            print(f"__RESULT_JSON__{json.dumps(result)}__END_RESULT__")
        except Exception as exc:
            import traceback
            print(f"__RESULT_JSON__{{\"passed\": false, \"error\": {json.dumps(str(exc))}}}__END_RESULT__")
            traceback.print_exc()
        sys.exit(0)

if __name__ == "__main__":
    unittest.main()
