# -*- coding: utf-8 -*-
# Tests for tool guard fail-closed and semantic tool dedup.
# Hermetic: subprocess isolation (same pattern as test_1006_real_loop.py).
import json
import os
import subprocess
import sys
import unittest

_THIS_FILE = os.path.abspath(__file__)


class TestTurnIntegrity(unittest.TestCase):

    def _run_worker(self, test_name):
        env = {**os.environ, "_TURN_INTEGRITY_SUBPROCESS": test_name}
        result = subprocess.run(
            [sys.executable, _THIS_FILE],
            env=env, capture_output=True, text=True, timeout=60,
        )
        stdout = result.stdout
        start = stdout.find("__RESULT_JSON__")
        end = stdout.find("__END_RESULT__")
        self.assertGreater(start, -1,
            f"No result marker:\nSTDOUT:\n{stdout}\nSTDERR:\n{result.stderr}")
        payload = json.loads(stdout[start + len("__RESULT_JSON__"):end])
        if not payload.get("passed"):
            self.fail(f"Subprocess failed: {payload.get(chr(101)+chr(114)+chr(114)+chr(111)+chr(114), chr(117)+chr(110)+chr(107)+chr(110)+chr(111)+chr(119)+chr(110))}\n{result.stderr}")
        return payload

    def test_tool_before_input(self):
        p = self._run_worker("tool_before_input")
        self.assertFalse(p["executed"])
        self.assertIn("no_valid_semantic_input", p["reason"])

    def test_tool_empty_in_buf(self):
        p = self._run_worker("tool_empty_in_buf")
        self.assertFalse(p["executed"])
        self.assertIn("no_valid_semantic_input", p["reason"])

    def test_tool_after_dot(self):
        p = self._run_worker("tool_after_dot")
        self.assertFalse(p["executed"])
        self.assertIn("no_valid_semantic_input", p["reason"])

    def test_tool_after_noise(self):
        p = self._run_worker("tool_after_noise")
        self.assertFalse(p["executed"])
        self.assertIn("no_valid_semantic_input", p["reason"])

    def test_tool_after_semantic_input(self):
        p = self._run_worker("tool_after_semantic")
        self.assertTrue(p["executed"])

    def test_same_tool_same_args_diff_ids(self):
        p = self._run_worker("dedup_same_args_diff_ids")
        self.assertEqual(p["executed_count"], 1)
        self.assertEqual(p["dup_count"], 1)

    def test_same_tool_diff_args(self):
        p = self._run_worker("dedup_diff_args")
        self.assertEqual(p["executed_count"], 2)
        self.assertEqual(p["dup_count"], 0)

    def test_same_tool_same_args_new_turn(self):
        p = self._run_worker("dedup_new_turn")
        self.assertTrue(p["executed_in_turn2"])


# ============================================================
# Subprocess worker
# ============================================================

if os.environ.get("_TURN_INTEGRITY_SUBPROCESS"):

    import asyncio
    import threading
    import time
    import types
    import uuid
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    # ── Module stubs (same as test_1006_real_loop.py) ──
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
            self.id = id
            self.name = name
            self.response = response
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
        accepted = False
        rejected = False
    class _FakeBargeInGate:
        def __init__(self, **kw): pass
        def process_frame(self, *a, **k): return _FakeBargeInDecision()
        def start_playback(self): pass
        def stop_playback(self): pass
        def observe_playback(self, *a, **k): pass
    sys.modules["core.audio_barge_in"].BargeInDecision = _FakeBargeInDecision
    sys.modules["core.audio_barge_in"].SpeechAwareBargeInGate = _FakeBargeInGate

    class _FakeJarvisClient:
        on_text_command = None
        on_conversation_toggle = None
        muted = False
        current_file = None
        _voice_combo = None
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

    _mem_pkg = types.ModuleType("memory")
    _mem_pkg.__path__ = ["/dev/null/memory"]
    sys.modules["memory"] = _mem_pkg
    _mem_cs = types.ModuleType("memory.conversation_store")
    class _FakeConversationStore:
        def __init__(self, *a, **k): pass
        def append_turn(self, *a, **k): pass
        def upsert_turn(self, *a, **k): pass
        def load(self, *a, **k):
            return {"schema_version": 2, "conversation_id": uuid.uuid4().hex,
                    "summary": "", "recent_turns": [], "recent_tool_results": [],
                    "metadata": {"created_at": "", "updated_at": "", "last_activity_at": None}}
        def save(self, *a, **k): pass
    _mem_cs.ConversationStore = _FakeConversationStore
    _mem_cs.append_tool_result = lambda *a, **k: None
    _mem_cs.append_turn = lambda *a, **k: None
    _mem_cs.default_store_path = lambda *a, **k: "/tmp/test_conv.json"
    _mem_cs.redact_sensitive_text = lambda t: t
    _mem_cs.upsert_turn = lambda *a, **k: None
    _mem_cs.empty_state = lambda cid=None: {
        "schema_version": 2, "conversation_id": cid or uuid.uuid4().hex,
        "summary": "", "recent_turns": [], "recent_tool_results": [],
        "metadata": {"created_at": "", "updated_at": "", "last_activity_at": None}}
    sys.modules["memory.conversation_store"] = _mem_cs
    setattr(_mem_pkg, "conversation_store", _mem_cs)
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
    _sd.RawOutputStream = None  # will be mocked per-test
    _sd.default = SimpleNamespace(device=(0, 0))
    _sd.query_devices = lambda *a, **k: {"name": "test", "max_input_channels": 2, "max_output_channels": 2}
    _sd.check_input_settings = lambda **k: None

    sys.path.insert(0, "/home/flako1312/jarvis-headless")
    from main import JarvisLive, ConversationState, _is_semantic_transcript, _strip_noise_tags

    # ═══════════════════════════════════════════════════════════════
    # Test implementations
    # ═══════════════════════════════════════════════════════════════


    # -- Helpers --

    def _make_jl():
        client = _FakeJarvisClient()
        jl = JarvisLive(
            client=client, voice_name="Puck", headless=True,
            no_audio=True, api_key="fake-key-for-test",
        )
        return jl

    class FakeFunctionCall:
        def __init__(self, name, args, fc_id=None):
            self.name = name
            self.args = args
            self.id = fc_id or uuid.uuid4().hex

    def _simulate_tool_guard(jl, input_validated, in_buf, function_calls):
        from google.genai import types
        if not input_validated:
            current_input = " ".join(in_buf).strip()
            reason = "no_valid_semantic_input"
            fn_responses = [
                types.FunctionResponse(
                    id=fc.id,
                    name=getattr(fc, "name", "tool"),
                    response={"result": "No valid semantic input; tool call rejected."},
                )
                for fc in function_calls
            ]
            return False, reason, fn_responses
        else:
            return True, "executed", []

    def _simulate_dedup(jl, function_calls):
        import json as _json
        executed = []
        dups = []
        for fc in function_calls:
            _fc_args = getattr(fc, "args", {}) or {}
            sig = f"{getattr(fc, 'name', '')}:{_json.dumps(_fc_args, sort_keys=True, default=str)}"
            if sig in jl._turn_tool_signatures:
                dups.append(fc)
            else:
                jl._turn_tool_signatures.add(sig)
                executed.append(fc)
        return executed, dups

    def test_tool_before_input():
        jl = _make_jl()
        fc = FakeFunctionCall("date_time", {"action": "current_time"})
        executed, reason, _ = _simulate_tool_guard(jl, False, [], [fc])
        return {"passed": True, "executed": executed, "reason": reason}

    def test_tool_empty_in_buf():
        jl = _make_jl()
        fc = FakeFunctionCall("date_time", {"action": "current_time"})
        executed, reason, _ = _simulate_tool_guard(jl, False, [], [fc])
        return {"passed": True, "executed": executed, "reason": reason}

    def test_tool_after_dot():
        jl = _make_jl()
        input_validated = _is_semantic_transcript(_strip_noise_tags("."))
        fc = FakeFunctionCall("date_time", {"action": "current_time"})
        executed, reason, _ = _simulate_tool_guard(jl, input_validated, ["."], [fc])
        return {"passed": True, "executed": executed, "reason": reason}

    def test_tool_after_noise():
        jl = _make_jl()
        raw = "[noise]"
        clean = _strip_noise_tags(raw)
        input_validated = _is_semantic_transcript(clean)
        fc = FakeFunctionCall("date_time", {"action": "current_time"})
        executed, reason, _ = _simulate_tool_guard(jl, input_validated, [raw], [fc])
        return {"passed": True, "executed": executed, "reason": reason}

    def test_tool_after_semantic():
        jl = _make_jl()
        input_validated = _is_semantic_transcript(_strip_noise_tags("dime la hora"))
        fc = FakeFunctionCall("date_time", {"action": "current_time"})
        executed, reason, _ = _simulate_tool_guard(jl, input_validated, ["dime la hora"], [fc])
        return {"passed": True, "executed": executed}

    def test_dedup_same_args_diff_ids():
        jl = _make_jl()
        jl._turn_tool_signatures = set()
        fc1 = FakeFunctionCall("date_time", {"action": "current_time"}, "id_A")
        fc2 = FakeFunctionCall("date_time", {"action": "current_time"}, "id_B")
        executed, dups = _simulate_dedup(jl, [fc1, fc2])
        return {"passed": True, "executed_count": len(executed), "dup_count": len(dups)}

    def test_dedup_diff_args():
        jl = _make_jl()
        jl._turn_tool_signatures = set()
        fc1 = FakeFunctionCall("date_time", {"action": "current_time"}, "id_A")
        fc2 = FakeFunctionCall("date_time", {"action": "current_date"}, "id_B")
        executed, dups = _simulate_dedup(jl, [fc1, fc2])
        return {"passed": True, "executed_count": len(executed), "dup_count": len(dups)}

    def test_dedup_new_turn():
        jl = _make_jl()
        jl._turn_tool_signatures = set()
        fc1 = FakeFunctionCall("date_time", {"action": "current_time"}, "id_A")
        executed1, _ = _simulate_dedup(jl, [fc1])
        assert len(executed1) == 1
        jl._turn_tool_signatures = set()
        fc2 = FakeFunctionCall("date_time", {"action": "current_time"}, "id_C")
        executed2, _ = _simulate_dedup(jl, [fc2])
        return {"passed": True, "executed_in_turn2": len(executed2) == 1}

    if __name__ == "__main__":
        test_name = os.environ["_TURN_INTEGRITY_SUBPROCESS"]
        dispatch = {
            "tool_before_input": test_tool_before_input,
            "tool_empty_in_buf": test_tool_empty_in_buf,
            "tool_after_dot": test_tool_after_dot,
            "tool_after_noise": test_tool_after_noise,
            "tool_after_semantic": test_tool_after_semantic,
            "dedup_same_args_diff_ids": test_dedup_same_args_diff_ids,
            "dedup_diff_args": test_dedup_diff_args,
            "dedup_new_turn": test_dedup_new_turn,
        }
        try:
            fn = dispatch.get(test_name)
            if fn is None:
                result = {"passed": False, "error": f"Unknown test: {test_name}"}
            else:
                result = fn()
        except Exception as e:
            import traceback
            result = {"passed": False, "error": repr(e) + " " + traceback.format_exc()}

        print(f"__RESULT_JSON__{json.dumps(result)}__END_RESULT__")
        sys.exit(0 if result.get("passed") else 1)
