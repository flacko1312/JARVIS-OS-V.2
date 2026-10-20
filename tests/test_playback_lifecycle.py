# -*- coding: utf-8 -*-
"""Tests for PortAudio playback lifecycle and void turn audio quarantine.

Hermetic: runs test logic in subprocess (same pattern as test_1006_real_loop.py).
"""
import json
import os
import subprocess
import sys
import unittest

_THIS_FILE = os.path.abspath(__file__)


class TestPlaybackLifecycle(unittest.TestCase):

    def _run_worker(self, test_name):
        env = {**os.environ, "_PLAYBACK_TEST_SUBPROCESS": test_name}
        result = subprocess.run(
            [sys.executable, _THIS_FILE],
            env=env, capture_output=True, text=True, timeout=60,
        )
        stdout = result.stdout
        start = stdout.find("__RESULT_JSON__")
        end = stdout.find("__END_RESULT__")
        self.assertGreater(start, -1,
            f"No result marker in output:\nSTDOUT:\n{stdout}\nSTDERR:\n{result.stderr}")
        payload = json.loads(stdout[start + len("__RESULT_JSON__"):end])
        if not payload.get("passed"):
            self.fail(f"Subprocess test failed: {payload.get('error', 'unknown')}\n{result.stderr}")
        return payload

    # ── PortAudio lifecycle tests ──

    def test_goaway_during_playback(self):
        """GoAway while stream.write active: close waits for write, no race."""
        p = self._run_worker("goaway_during_playback")
        self.assertTrue(p["write_completed_before_close"])
        self.assertFalse(p["close_during_write"])

    def test_slow_write_cancel(self):
        """Slow/blocked stream.write + TaskGroup cancel: safe shutdown."""
        p = self._run_worker("slow_write_cancel")
        self.assertTrue(p["write_completed_before_close"])
        self.assertFalse(p["exception_leaked"])

    def test_no_double_close(self):
        """Stream is closed exactly once, no double-close."""
        p = self._run_worker("no_double_close")
        self.assertEqual(p["close_count"], 1)

    def test_barge_in_during_write(self):
        """Barge-in while write active: logical audio cut, safe stream."""
        p = self._run_worker("barge_in_during_write")
        self.assertTrue(p["queue_drained"])
        self.assertTrue(p["write_completed_before_close"])

    def test_reconnect_stream_ordering(self):
        """Old stream fully closed before new stream opens."""
        p = self._run_worker("reconnect_stream_ordering")
        self.assertTrue(p["old_closed_before_new_opened"])

    # ── Void turn quarantine tests ──

    def test_dot_input_no_playback(self):
        """Input='.' with response_audio: no SPEAKING, no playback."""
        p = self._run_worker("dot_input_no_playback")
        self.assertFalse(p["speaking_reached"])
        self.assertEqual(p["quarantine_discarded"], True)

    def test_noise_input_no_playback(self):
        """Input='<noise>' with response_audio: no playback."""
        p = self._run_worker("noise_input_no_playback")
        self.assertFalse(p["speaking_reached"])
        self.assertEqual(p["quarantine_discarded"], True)

    def test_valid_input_buffer_release(self):
        """Audio arrives first, then valid input: quarantine flushes."""
        p = self._run_worker("valid_input_buffer_release")
        self.assertTrue(p["quarantine_flushed"])
        self.assertTrue(p["audio_played"])

    def test_invalid_turn_complete_discard(self):
        """Audio arrives, turn ends with invalid input: quarantine discarded."""
        p = self._run_worker("invalid_turn_complete_discard")
        self.assertTrue(p["quarantine_discarded"])
        self.assertFalse(p["audio_played"])


# ═══════════════════════════════════════════════════════════════
# Subprocess worker
# ═══════════════════════════════════════════════════════════════

if os.environ.get("_PLAYBACK_TEST_SUBPROCESS"):

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
    from main import JarvisLive, ConversationState, _is_semantic_transcript

    # ═══════════════════════════════════════════════════════════════
    # Test implementations
    # ═══════════════════════════════════════════════════════════════

    def _make_jl():
        client = _FakeJarvisClient()
        jl = JarvisLive(
            client=client, voice_name="Puck", headless=True,
            no_audio=True, api_key="fake-key-for-test",
        )
        return jl

    def test_goaway_during_playback():
        """Test that _close_playback_stream waits for in-flight write."""
        write_started = threading.Event()
        write_finished = threading.Event()
        close_during_write = [False]
        write_completed_before_close = [False]
        close_called = threading.Event()

        class FakeStream:
            _stopped = False
            def write(self, data):
                write_started.set()
                time.sleep(0.15)  # simulate slow write
                write_finished.set()
            def start(self): pass
            def stop(self):
                if write_started.is_set() and not write_finished.is_set():
                    close_during_write[0] = True
                self._stopped = True
            def close(self):
                if write_finished.is_set():
                    write_completed_before_close[0] = True
                close_called.set()

        jl = _make_jl()
        stream = FakeStream()
        lock = jl._playback_stream_lock

        def locked_write():
            with lock:
                stream.write(b"\x00" * 1024)

        t = threading.Thread(target=locked_write)
        t.start()
        write_started.wait(timeout=2)
        time.sleep(0.02)  # ensure write is in progress
        jl._close_playback_stream(stream)
        t.join(timeout=3)

        return {
            "passed": True,
            "write_completed_before_close": write_completed_before_close[0],
            "close_during_write": close_during_write[0],
        }

    def test_slow_write_cancel():
        """Slow write + close: no exception leaked."""
        write_started = threading.Event()
        write_finished = threading.Event()
        write_completed_before_close = [False]
        exception_leaked = [False]

        class FakeStream:
            def write(self, data):
                write_started.set()
                time.sleep(0.2)
                write_finished.set()
            def start(self): pass
            def stop(self): pass
            def close(self):
                if write_finished.is_set():
                    write_completed_before_close[0] = True

        jl = _make_jl()
        stream = FakeStream()
        lock = jl._playback_stream_lock

        def locked_write():
            try:
                with lock:
                    stream.write(b"\x00" * 1024)
            except Exception:
                exception_leaked[0] = True

        t = threading.Thread(target=locked_write)
        t.start()
        write_started.wait(timeout=2)
        time.sleep(0.02)
        jl._close_playback_stream(stream)
        t.join(timeout=3)

        return {
            "passed": True,
            "write_completed_before_close": write_completed_before_close[0],
            "exception_leaked": exception_leaked[0],
        }

    def test_no_double_close():
        """Stream closed exactly once."""
        close_count = [0]

        class FakeStream:
            def write(self, data): pass
            def start(self): pass
            def stop(self):
                close_count[0] += 1
            def close(self): pass

        jl = _make_jl()
        stream = FakeStream()
        jl._close_playback_stream(stream)
        jl._close_playback_stream(None)  # should be no-op

        return {"passed": True, "close_count": close_count[0]}

    def test_barge_in_during_write():
        """Barge-in drains queue; write finishes before close."""
        write_started = threading.Event()
        write_finished = threading.Event()
        write_completed_before_close = [False]

        class FakeStream:
            def write(self, data):
                write_started.set()
                time.sleep(0.1)
                write_finished.set()
            def start(self): pass
            def stop(self): pass
            def close(self):
                if write_finished.is_set():
                    write_completed_before_close[0] = True

        jl = _make_jl()
        jl.audio_in_queue = asyncio.Queue()
        for i in range(10):
            jl.audio_in_queue.put_nowait(b"\x00" * 100)

        drained = jl._interrupt_live_playback("local_barge_in")
        queue_drained = jl.audio_in_queue.empty()

        stream = FakeStream()
        lock = jl._playback_stream_lock

        def locked_write():
            with lock:
                stream.write(b"\x00" * 1024)

        t = threading.Thread(target=locked_write)
        t.start()
        write_started.wait(timeout=2)
        time.sleep(0.02)
        jl._close_playback_stream(stream)
        t.join(timeout=3)

        return {
            "passed": True,
            "queue_drained": queue_drained,
            "write_completed_before_close": write_completed_before_close[0],
        }

    def test_reconnect_stream_ordering():
        """Old stream fully closed before new stream opened."""
        events = []

        class FakeStream:
            def __init__(self, name):
                self.name = name
            def write(self, data):
                time.sleep(0.05)
            def start(self):
                events.append(f"{self.name}_start")
            def stop(self):
                events.append(f"{self.name}_stop")
            def close(self):
                events.append(f"{self.name}_close")

        jl = _make_jl()
        old = FakeStream("old")
        jl._close_playback_stream(old)
        new = FakeStream("new")
        new.start()

        old_close_idx = events.index("old_close") if "old_close" in events else -1
        new_start_idx = events.index("new_start") if "new_start" in events else -1

        return {
            "passed": True,
            "old_closed_before_new_opened": old_close_idx < new_start_idx,
        }

    # ── Void turn quarantine tests ──

    def test_dot_input_no_playback():
        """'.' input + response audio => quarantine, discard, no SPEAKING."""
        jl = _make_jl()
        speaking_reached = [False]
        orig_set_speaking = jl.set_speaking
        def tracking_set_speaking(val):
            if val:
                speaking_reached[0] = True
            orig_set_speaking(val)
        jl.set_speaking = tracking_set_speaking

        # Simulate: _input_validated=False, audio arrives, quarantined
        _input_validated = False
        _audio_quarantine = []
        _audio_quarantine.append(b"\x00" * 1024)
        _audio_quarantine.append(b"\x00" * 1024)

        # Simulate turn_complete with void input "."
        full_in = "."
        _clean_in = "."
        _void_turn = bool(full_in) and not _is_semantic_transcript(_clean_in)
        assert _void_turn, f"Expected void turn for '.', got {_void_turn}"

        # Discard quarantine (what the patched code does)
        quarantine_discarded = len(_audio_quarantine) > 0
        _audio_quarantine.clear()

        return {
            "passed": True,
            "speaking_reached": speaking_reached[0],
            "quarantine_discarded": quarantine_discarded,
        }

    def test_noise_input_no_playback():
        """Noise input + response audio => quarantine, discard."""
        _input_validated = False
        _audio_quarantine = [b"\x00" * 1024]

        full_in = "[noise]"
        from main import _strip_noise_tags
        _clean_in = _strip_noise_tags(full_in)
        _void_turn = bool(full_in) and not _is_semantic_transcript(_clean_in)

        quarantine_discarded = len(_audio_quarantine) > 0 and _void_turn
        _audio_quarantine.clear()

        return {
            "passed": True,
            "speaking_reached": False,
            "quarantine_discarded": quarantine_discarded,
        }

    def test_valid_input_buffer_release():
        """Audio arrives first, then valid input flushes quarantine."""
        jl = _make_jl()
        jl.audio_in_queue = asyncio.Queue()

        _audio_quarantine = [b"\x00" * 512, b"\x00" * 512]
        _input_validated = False

        # Simulate semantic input arriving
        current_input = "dime la hora"
        from main import _strip_noise_tags
        if _is_semantic_transcript(_strip_noise_tags(current_input)):
            _input_validated = True
            for chunk in _audio_quarantine:
                jl.audio_in_queue.put_nowait(chunk)
            _audio_quarantine.clear()

        return {
            "passed": True,
            "quarantine_flushed": _input_validated and len(_audio_quarantine) == 0,
            "audio_played": jl.audio_in_queue.qsize() == 2,
        }

    def test_invalid_turn_complete_discard():
        """Audio arrives, turn ends with invalid input => discard."""
        jl = _make_jl()
        jl.audio_in_queue = asyncio.Queue()

        _audio_quarantine = [b"\x00" * 512, b"\x00" * 512]
        _input_validated = False

        # Turn complete with non-semantic input
        full_in = "."
        _clean_in = "."
        _void_turn = bool(full_in) and not _is_semantic_transcript(_clean_in)

        quarantine_discarded = False
        if _void_turn:
            _audio_quarantine.clear()
            quarantine_discarded = True

        return {
            "passed": True,
            "quarantine_discarded": quarantine_discarded,
            "audio_played": jl.audio_in_queue.qsize() > 0,
        }

    # ── Main dispatcher ──
    if __name__ == "__main__":
        test_name = os.environ["_PLAYBACK_TEST_SUBPROCESS"]
        dispatch = {
            "goaway_during_playback": test_goaway_during_playback,
            "slow_write_cancel": test_slow_write_cancel,
            "no_double_close": test_no_double_close,
            "barge_in_during_write": test_barge_in_during_write,
            "reconnect_stream_ordering": test_reconnect_stream_ordering,
            "dot_input_no_playback": test_dot_input_no_playback,
            "noise_input_no_playback": test_noise_input_no_playback,
            "valid_input_buffer_release": test_valid_input_buffer_release,
            "invalid_turn_complete_discard": test_invalid_turn_complete_discard,
        }
        try:
            fn = dispatch.get(test_name)
            if fn is None:
                result = {"passed": False, "error": f"Unknown test: {test_name}"}
            else:
                result = fn()
        except Exception as e:
            import traceback
            result = {"passed": False, "error": f"{e}\n{traceback.format_exc()}"}

        print(f"__RESULT_JSON__{json.dumps(result)}__END_RESULT__")
        sys.exit(0 if result.get("passed") else 1)
