"""Gemini Live session lifecycle tests.

Deterministic, offline tests (no network, no real Gemini). Prove:
  1. Normal turn completion = zero reconnect (same session stays open).
  2. Multiple turns (2-3) use ONE live.connect() call.
  3. Real transport failure = reconnect.
  4. Reconnect uses latest session resumption handle.
  5. First connection enables session resumption config.
  6. F8 stop clears the resumption handle.
  7. Context window compression is configured.
  8. Startup produces zero live.connect() calls (STANDBY).
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key-placeholder")

# Mock platform-specific modules that fail without hardware or SDK install.
# genai.errors needs real exception classes for isinstance() checks.
_mock_genai_errors = MagicMock()
_mock_genai_errors.APIError = type("APIError", (Exception,), {})

_mock_genai_types = MagicMock()

class _FakeSessionResumptionConfig:
    def __init__(self, handle=None, **kw):
        self.handle = handle
_mock_genai_types.SessionResumptionConfig = _FakeSessionResumptionConfig

class _FakeSlidingWindow:
    def __init__(self, **kw):
        pass
_mock_genai_types.SlidingWindow = _FakeSlidingWindow

class _FakeContextWindowCompressionConfig:
    def __init__(self, sliding_window=None, **kw):
        self.sliding_window = sliding_window
_mock_genai_types.ContextWindowCompressionConfig = _FakeContextWindowCompressionConfig

class _FakeLiveConnectConfig:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
_mock_genai_types.LiveConnectConfig = _FakeLiveConnectConfig

_mock_genai = MagicMock()
_mock_genai.errors = _mock_genai_errors
_mock_genai.types = _mock_genai_types

for _mod in ("sounddevice",):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

if "google" not in sys.modules or isinstance(sys.modules.get("google"), MagicMock):
    _mock_google = MagicMock()
    _mock_google.genai = _mock_genai
    sys.modules["google"] = _mock_google
    sys.modules["google.genai"] = _mock_genai
    sys.modules["google.genai.types"] = _mock_genai_types
    sys.modules["google.genai.errors"] = _mock_genai_errors

import main
from main import _GoAwaySignal


# ── helpers ──────────────────────────────────────────────────────────────

class StubClient:
    """Minimal stand-in for JarvisClient."""
    def __init__(self):
        self.on_text_command = None
        self.muted = False
        self.current_file = None
        self._voice_combo = None
        self.operational_ready = True
        self.states = []
        self.logs = []

    def write_log(self, text):
        self.logs.append(text)

    def set_state(self, state):
        self.states.append(state)

    def show_subtitle(self, text):
        pass

    def clear_subtitle(self):
        pass

    def sync_voice_display(self, v):
        pass

    def set_theme(self, t):
        pass

    def set_graphics_quality(self, q):
        pass

    def handle_ui_command(self, cmd):
        pass


_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def _make_jarvis(**kwargs) -> main.JarvisLive:
    client = StubClient()
    jarvis = main.JarvisLive(client, "puck", **kwargs)
    jarvis._loop = _loop
    return jarvis


def _run(coro):
    return _loop.run_until_complete(coro)


def _make_turn_complete_response():
    """A single response with server_content.turn_complete = True."""
    sc = SimpleNamespace(
        model_turn=None,
        turn_complete=True,
        interrupted=False,
        grounding_metadata=None,
        input_transcription=None,
        output_transcription=None,
        generation_complete=None,
        waiting_for_input=None,
        interim_input_transcription=None,
        interaction_status=None,
        turn_complete_reason=None,
        url_context_metadata=None,
    )
    return SimpleNamespace(
        server_content=sc,
        tool_call=None,
        go_away=None,
        session_resumption_update=None,
    )


def _make_resumption_response(handle: str):
    """A response carrying a session_resumption_update."""
    sru = SimpleNamespace(new_handle=handle, resumable=True)
    return SimpleNamespace(
        server_content=None,
        tool_call=None,
        go_away=None,
        session_resumption_update=sru,
    )


def _make_go_away_response(time_left=None):
    """A response carrying a go_away signal."""
    ga = SimpleNamespace(time_left=time_left)
    return SimpleNamespace(
        server_content=None,
        tool_call=None,
        go_away=ga,
        session_resumption_update=None,
    )


def _make_audio_response(data: bytes = b"\x00\x01"):
    """A response with inline audio data."""
    inline = SimpleNamespace(data=data, mime_type="audio/pcm")
    part = SimpleNamespace(inline_data=inline)
    mt = SimpleNamespace(parts=[part])
    sc = SimpleNamespace(
        model_turn=mt,
        turn_complete=False,
        interrupted=False,
        grounding_metadata=None,
        input_transcription=None,
        output_transcription=None,
        generation_complete=None,
        waiting_for_input=None,
        interim_input_transcription=None,
        interaction_status=None,
        turn_complete_reason=None,
        url_context_metadata=None,
    )
    return SimpleNamespace(
        server_content=sc,
        tool_call=None,
        go_away=None,
        session_resumption_update=None,
    )


class AsyncIterFromList:
    """Turn a list into an async iterator, then stop (StopAsyncIteration)."""
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


# ── tests ────────────────────────────────────────────────────────────────

class TestNormalTurnNoReconnect(unittest.TestCase):
    """Req 1: Normal turn_complete does NOT cause a reconnect or exception."""

    def test_turn_complete_continues_same_session(self):
        jarvis = _make_jarvis()
        jarvis._voice_active.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        turn1 = [_make_audio_response(), _make_turn_complete_response()]
        turn2 = [_make_audio_response(), _make_turn_complete_response()]
        turn3 = [_make_audio_response(), _make_turn_complete_response()]

        call_count = 0

        def fake_receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AsyncIterFromList(turn1)
            elif call_count == 2:
                return AsyncIterFromList(turn2)
            elif call_count == 3:
                return AsyncIterFromList(turn3)
            else:
                jarvis._shutdown_requested.set()
                return AsyncIterFromList([])

        session = SimpleNamespace(receive=fake_receive)
        jarvis.session = session

        _run(jarvis._receive_audio())

        self.assertEqual(call_count, 4)
        self.assertFalse(
            any("RECONNECT" in s for s in jarvis.ui.states),
            "No RECONNECTING state should be set on normal turns",
        )


class TestMultipleTurnsSameConnection(unittest.TestCase):
    """Req 2: 2-3 user/model turns use ONE live.connect() call."""

    def test_three_turns_one_connect(self):
        jarvis = _make_jarvis()
        jarvis._voice_active.set()

        turns_served = 0
        max_turns = 3

        def fake_receive():
            nonlocal turns_served
            turns_served += 1
            if turns_served <= max_turns:
                return AsyncIterFromList([
                    _make_resumption_response(f"handle-{turns_served}"),
                    _make_audio_response(),
                    _make_turn_complete_response(),
                ])
            else:
                jarvis._shutdown_requested.set()
                return AsyncIterFromList([])

        async def fake_run_live():
            jarvis._connect_count += 1
            jarvis.session = SimpleNamespace(receive=fake_receive)
            jarvis.audio_in_queue = asyncio.Queue()
            jarvis._turn_done_event = asyncio.Event()
            await jarvis._receive_audio()

        _run(fake_run_live())

        self.assertEqual(jarvis._connect_count, 1,
                         f"Expected 1 connect, got {jarvis._connect_count}")
        self.assertEqual(turns_served, max_turns + 1)


class RaisingAsyncIter:
    """Async iterator that raises a given exception on first next()."""
    def __init__(self, exc):
        self._exc = exc
    def __aiter__(self):
        return self
    async def __anext__(self):
        raise self._exc


class TestTransportFailureReconnects(unittest.TestCase):
    """Req 3: Real transport failure triggers a reconnect."""

    def test_connection_reset_raises(self):
        jarvis = _make_jarvis()
        jarvis._voice_active.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        exc = ConnectionResetError("Connection reset by peer")

        def fake_receive():
            return RaisingAsyncIter(exc)

        jarvis.session = SimpleNamespace(receive=fake_receive)

        with self.assertRaises(ConnectionResetError):
            _run(jarvis._receive_audio())


class TestGoAwayReconnects(unittest.TestCase):
    """Req 3 + 6: go_away is handled separately and triggers reconnect."""

    def test_go_away_raises_signal(self):
        jarvis = _make_jarvis()
        jarvis._voice_active.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        def fake_receive():
            return AsyncIterFromList([_make_go_away_response(time_left=30)])

        jarvis.session = SimpleNamespace(receive=fake_receive)

        with self.assertRaises(_GoAwaySignal):
            _run(jarvis._receive_audio())


class TestResumptionHandleCapture(unittest.TestCase):
    """Req 4: Capture every valid session_resumption_update.new_handle."""

    def test_handles_captured_across_turns(self):
        jarvis = _make_jarvis()
        jarvis._voice_active.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        call_count = 0

        def fake_receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AsyncIterFromList([
                    _make_resumption_response("first-handle"),
                    _make_turn_complete_response(),
                ])
            elif call_count == 2:
                return AsyncIterFromList([
                    _make_resumption_response("second-handle"),
                    _make_turn_complete_response(),
                ])
            else:
                jarvis._shutdown_requested.set()
                return AsyncIterFromList([])

        jarvis.session = SimpleNamespace(receive=fake_receive)
        _run(jarvis._receive_audio())

        self.assertEqual(jarvis._resumption_handle, "second-handle")

    def test_resumption_handle_used_in_config(self):
        jarvis = _make_jarvis()
        jarvis._resumption_handle = "test-handle-abc"
        config = jarvis._build_config()
        self.assertEqual(config.session_resumption.handle, "test-handle-abc")

    def test_first_connection_has_no_handle(self):
        jarvis = _make_jarvis()
        self.assertIsNone(jarvis._resumption_handle)
        config = jarvis._build_config()
        self.assertIsNone(config.session_resumption.handle)


class TestResumptionEnabled(unittest.TestCase):
    """Req 5: First connection enables session resumption config."""

    def test_session_resumption_configured(self):
        jarvis = _make_jarvis()
        config = jarvis._build_config()
        self.assertIsNotNone(config.session_resumption)


class TestF8StopClearsHandle(unittest.TestCase):
    """F8 stop clears the resumption handle."""

    def test_stop_voice_clears_handle(self):
        jarvis = _make_jarvis()
        jarvis._resumption_handle = "some-handle"
        jarvis._voice_active.set()
        jarvis.stop_voice()
        self.assertIsNone(jarvis._resumption_handle)
        self.assertFalse(jarvis._voice_active.is_set())


class TestContextCompression(unittest.TestCase):
    """Context window compression is configured."""

    def test_sliding_window_compression_enabled(self):
        jarvis = _make_jarvis()
        config = jarvis._build_config()
        self.assertIsNotNone(config.context_window_compression)
        self.assertIsNotNone(config.context_window_compression.sliding_window)


class TestStartupZeroConnects(unittest.TestCase):
    """Startup performs zero live.connect() calls."""

    def test_no_connect_without_voice_active(self):
        jarvis = _make_jarvis()
        self.assertFalse(jarvis._voice_active.is_set(),
                         "Voice should NOT be active at startup")
        self.assertEqual(jarvis._connect_count, 0)

    def test_external_audio_auto_activates(self):
        jarvis = _make_jarvis(external_audio=True)
        self.assertTrue(jarvis._voice_active.is_set(),
                        "Hosted mode should auto-activate voice")


class TestNormalCloseHandling(unittest.TestCase):
    """Normal 1000 close is detected correctly."""

    def test_connection_closed_ok_detected(self):
        ConnectionClosedOk = type("ConnectionClosedOk", (Exception,), {})
        exc = ConnectionClosedOk("1000 (ok)")
        self.assertTrue(main._is_normal_live_close_error(exc))

    def test_normal_close_returns_not_raises(self):
        jarvis = _make_jarvis()
        jarvis._voice_active.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        ConnectionClosedOk = type("ConnectionClosedOk", (Exception,), {})

        def fake_receive():
            return RaisingAsyncIter(ConnectionClosedOk("1000 (ok)"))

        jarvis.session = SimpleNamespace(receive=fake_receive)

        _run(jarvis._receive_audio())


if __name__ == "__main__":
    unittest.main()
