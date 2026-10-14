"""Tests for Gemini Live session error handling, reconnection, and context restoration."""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import main
from main import (
    ConversationState,
    InitialHistoryRejected,
    RecoverableLiveDisconnect,
    _SESSION_RESUMPTION_HANDLE_MAX_AGE,
    _exception_leaves,
    _is_invalid_argument_1007,
    _is_normal_live_close_error,
    _is_recoverable_live_disconnect,
    _is_resumption_handle_rejected,
    _is_session_not_found_1008,
    _is_transient_live_connection_error,
    _live_reconnect_delay,
)


class FakeUI:
    def __init__(self):
        self.states = []
        self.logs = []
        self.muted = False
        self.on_text_command = None
        self.on_conversation_toggle = None
        self.operational_ready = True

    def set_state(self, state):
        self.states.append(state)

    def write_log(self, text):
        self.logs.append(text)

    def clear_subtitle(self):
        pass

    def show_subtitle(self, _text):
        pass

    def sync_voice_display(self, _voice):
        pass


def _make_api_error(code, message):
    """Build a fake genai.errors.APIError with the given code and message."""
    exc = Exception(message)
    exc.code = code
    exc.__class__.__name__ = "APIError"
    return exc


# ── Error classification tests ────────────────────────────────────


class TestSessionNotFound1008(unittest.TestCase):
    def test_detects_1008_session_not_found(self):
        exc = Exception("WebSocket closed: 1008 session not found")
        self.assertTrue(_is_session_not_found_1008(exc))

    def test_rejects_non_1008(self):
        exc = Exception("WebSocket closed: 1000 (OK)")
        self.assertFalse(_is_session_not_found_1008(exc))

    def test_rejects_1008_without_session_not_found(self):
        exc = Exception("WebSocket closed: 1008 something else")
        self.assertFalse(_is_session_not_found_1008(exc))

    def test_nested_exception_group(self):
        inner = Exception("1008 session not found")
        group = ExceptionGroup("ws errors", [inner])
        self.assertTrue(_is_session_not_found_1008(group))


class TestInvalidArgument1007(unittest.TestCase):
    def test_detects_1007_invalid_argument(self):
        exc = Exception("1007 invalid argument: history too large")
        self.assertTrue(_is_invalid_argument_1007(exc))

    def test_rejects_non_1007(self):
        exc = Exception("1008 session not found")
        self.assertFalse(_is_invalid_argument_1007(exc))


class TestRecoverableDisconnect(unittest.TestCase):
    def test_1008_is_recoverable(self):
        exc = Exception("WebSocket closed: 1008 session not found")
        self.assertTrue(_is_recoverable_live_disconnect(exc))

    def test_1007_is_recoverable(self):
        exc = Exception("1007 invalid argument: bad request")
        self.assertTrue(_is_recoverable_live_disconnect(exc))

    def test_goaway_is_recoverable(self):
        exc = RecoverableLiveDisconnect("server GoAway")
        self.assertTrue(_is_recoverable_live_disconnect(exc))

    def test_transient_is_recoverable(self):
        exc = ConnectionResetError("connection reset")
        self.assertTrue(_is_recoverable_live_disconnect(exc))

    def test_random_error_is_not_recoverable(self):
        exc = ValueError("something completely wrong")
        self.assertFalse(_is_recoverable_live_disconnect(exc))


class TestReconnectDelay(unittest.TestCase):
    def test_exponential_backoff(self):
        self.assertEqual(_live_reconnect_delay(1), 1.0)
        self.assertEqual(_live_reconnect_delay(2), 2.0)
        self.assertEqual(_live_reconnect_delay(3), 4.0)
        self.assertEqual(_live_reconnect_delay(4), 8.0)

    def test_capped_at_30(self):
        self.assertEqual(_live_reconnect_delay(10), 30.0)
        self.assertEqual(_live_reconnect_delay(100), 30.0)


class TestResumptionHandleRejected(unittest.TestCase):
    def test_detects_session_resumption(self):
        exc = Exception("session resumption handle expired")
        self.assertTrue(_is_resumption_handle_rejected(exc))

    def test_detects_invalid_handle(self):
        exc = Exception("invalid handle: not found")
        self.assertTrue(_is_resumption_handle_rejected(exc))

    def test_rejects_unrelated(self):
        exc = Exception("something else")
        self.assertFalse(_is_resumption_handle_rejected(exc))


# ── JarvisLive session management tests ───────────────────────────


class TestJarvisLiveSessionManagement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "conversation_state.json"

    def tearDown(self):
        self.temp.cleanup()

    def make_jarvis(self):
        return main.JarvisLive(
            FakeUI(),
            api_key="test",
            external_audio=True,
            conversation_store_path=self.store_path,
        )

    def test_initial_state_is_standby(self):
        jarvis = self.make_jarvis()
        self.assertEqual(jarvis.conversation_state, ConversationState.STANDBY)

    def test_start_conversation_transitions_to_connecting(self):
        jarvis = self.make_jarvis()
        result = jarvis.start_conversation()
        self.assertTrue(result)
        self.assertEqual(jarvis.conversation_state, ConversationState.CONNECTING)

    def test_stop_conversation_transitions_to_stopping(self):
        jarvis = self.make_jarvis()
        jarvis.start_conversation()
        result = jarvis.stop_conversation()
        self.assertTrue(result)
        self.assertEqual(jarvis.conversation_state, ConversationState.STOPPING)

    def test_double_start_is_rejected(self):
        jarvis = self.make_jarvis()
        jarvis.start_conversation()
        self.assertFalse(jarvis.start_conversation())

    def test_new_conversation_resets_handles(self):
        jarvis = self.make_jarvis()
        jarvis._session_resumption_handle = "some-handle"
        jarvis._session_resumption_handle_at = time.monotonic()
        jarvis.new_conversation()
        self.assertIsNone(jarvis._session_resumption_handle)
        self.assertIsNone(jarvis._session_resumption_handle_at)


class TestResumptionHandleExpiry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "conversation_state.json"

    def tearDown(self):
        self.temp.cleanup()

    def make_jarvis(self):
        return main.JarvisLive(
            FakeUI(),
            api_key="test",
            external_audio=True,
            conversation_store_path=self.store_path,
        )

    def test_fresh_handle_is_used(self):
        jarvis = self.make_jarvis()
        jarvis._session_resumption_handle = "fresh-handle"
        jarvis._session_resumption_handle_at = time.monotonic()
        self.assertIsNotNone(jarvis._session_resumption_handle)

    def test_stale_handle_constant_defined(self):
        self.assertEqual(_SESSION_RESUMPTION_HANDLE_MAX_AGE, 600.0)


# ── Durable continuity tests ─────────────────────────────────────


class TestDurableContinuity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "conversation_state.json"

    def tearDown(self):
        self.temp.cleanup()

    def make_jarvis(self):
        return main.JarvisLive(
            FakeUI(),
            api_key="test",
            external_audio=True,
            conversation_store_path=self.store_path,
        )

    def test_empty_continuity_gives_empty_prompt(self):
        jarvis = self.make_jarvis()
        self.assertEqual(jarvis._local_continuity_prompt(), "")

    def test_continuity_turns_built_from_store(self):
        jarvis = self.make_jarvis()
        jarvis._conversation_continuity = [
            {"role": "user", "text": "Hola"},
            {"role": "assistant", "text": "Hola, flako"},
        ]
        turns = jarvis._durable_continuity_turns()
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0].role, "user")
        self.assertEqual(turns[1].role, "model")

    def test_empty_text_turns_are_skipped(self):
        jarvis = self.make_jarvis()
        jarvis._conversation_continuity = [
            {"role": "user", "text": ""},
            {"role": "assistant", "text": "real text"},
        ]
        turns = jarvis._durable_continuity_turns()
        self.assertEqual(len(turns), 1)

    def test_history_diagnostics(self):
        jarvis = self.make_jarvis()
        jarvis._conversation_continuity = [
            {"role": "user", "text": "Hola"},
            {"role": "assistant", "text": "Buenos días"},
        ]
        stats = jarvis._durable_history_diagnostics()
        self.assertEqual(stats["items"], 2)
        self.assertEqual(stats["user"], 1)
        self.assertEqual(stats["model"], 1)
        self.assertEqual(stats["empty"], 0)

    def test_continuity_prompt_includes_conversation_id(self):
        jarvis = self.make_jarvis()
        jarvis._conversation_continuity = [
            {"role": "user", "text": "Test message"},
        ]
        prompt = jarvis._local_continuity_prompt()
        self.assertIn("DURABLE JARVIS CONVERSATION CONTINUITY", prompt)
        self.assertIn(jarvis._conversation_id, prompt)


# ── HistoryConfig build tests ─────────────────────────────────────


class TestBuildConfig(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "conversation_state.json"

    def tearDown(self):
        self.temp.cleanup()

    def make_jarvis(self):
        return main.JarvisLive(
            FakeUI(),
            api_key="test",
            external_audio=True,
            conversation_store_path=self.store_path,
        )

    def test_config_without_initial_history(self):
        jarvis = self.make_jarvis()
        config = jarvis._build_config(initial_history=False)
        self.assertIsNone(config.history_config)

    def test_config_with_initial_history(self):
        jarvis = self.make_jarvis()
        config = jarvis._build_config(initial_history=True)
        self.assertIsNotNone(config.history_config)
        self.assertTrue(config.history_config.initial_history_in_client_content)

    def test_config_includes_session_resumption(self):
        jarvis = self.make_jarvis()
        config = jarvis._build_config(resumption_handle="test-handle")
        self.assertEqual(config.session_resumption.handle, "test-handle")

    def test_config_without_resumption_handle(self):
        jarvis = self.make_jarvis()
        config = jarvis._build_config()
        self.assertIsNone(config.session_resumption.handle)

    def test_config_includes_local_continuity_in_system_instruction(self):
        jarvis = self.make_jarvis()
        config = jarvis._build_config(
            local_continuity="[DURABLE CONTINUITY] test data"
        )
        self.assertIn("[DURABLE CONTINUITY] test data", config.system_instruction)


# ── Exception leaf extraction tests ───────────────────────────────


class TestExceptionLeaves(unittest.TestCase):
    def test_simple_exception(self):
        exc = ValueError("simple")
        leaves = list(_exception_leaves(exc))
        self.assertEqual(len(leaves), 1)
        self.assertIs(leaves[0], exc)

    def test_exception_group(self):
        inner1 = ValueError("a")
        inner2 = TypeError("b")
        group = ExceptionGroup("group", [inner1, inner2])
        leaves = list(_exception_leaves(group))
        self.assertEqual(len(leaves), 2)

    def test_nested_groups(self):
        inner = ValueError("deep")
        mid = ExceptionGroup("mid", [inner])
        outer = ExceptionGroup("outer", [mid])
        leaves = list(_exception_leaves(outer))
        self.assertEqual(len(leaves), 1)
        self.assertIs(leaves[0], inner)


if __name__ == "__main__":
    unittest.main()
