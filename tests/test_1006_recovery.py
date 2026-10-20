# -*- coding: utf-8 -*-
"""Regression tests for 1006 WebSocket abnormal closure recovery.

Real log fixture (02:08:46 oct 20 2026):
  ExceptionGroup with 2 sub-exceptions:
    1. google.genai.errors.APIError: 1006 None. abnormal closure [internal]
    2. ConnectionResetError: [Errno 104] Connection reset by peer
"""
import re
import sys
import types
import unittest
import logging

# ── Stub genai ──
class FakeAPIError(Exception):
    def __init__(self, status_code, response_json=None, response=None):
        self.status = status_code
        self.code = status_code
        msg = f"{status_code} {response_json}"
        if status_code == 1006:
            msg += ". abnormal closure [internal]"
        super().__init__(msg)

_genai_mod = types.ModuleType("genai")
_errors_mod = types.ModuleType("genai.errors")
_errors_mod.APIError = FakeAPIError
_genai_mod.errors = _errors_mod


# ── Extract classifier functions from main.py source ──
MAIN_PATH = "/home/flako1312/jarvis-headless/main.py"

with open(MAIN_PATH, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

# Find _exception_leaves (start) and end after _is_session_not_found_1008
start_idx = None
end_idx = None
for i, line in enumerate(all_lines):
    if "def _exception_leaves(" in line and start_idx is None:
        start_idx = i
    if "def _is_session_not_found_1008(" in line:
        # Find the end of this function
        for j in range(i + 1, len(all_lines)):
            stripped = all_lines[j].rstrip()
            if stripped and not stripped.startswith(" ") and not stripped.startswith(")"):
                end_idx = j
                break
        break

assert start_idx is not None, "Could not find _exception_leaves"
assert end_idx is not None, "Could not find end of _is_session_not_found_1008"

source_block = "".join(all_lines[start_idx:end_idx])

_ns = {
    "genai": _genai_mod,
    "re": re,
    "logging": logging,
    "asyncio": __import__("asyncio"),
    "__builtins__": __builtins__,
}

exec(compile(source_block, f"{MAIN_PATH}:{start_idx+1}", "exec"), _ns)

_exception_leaves = _ns["_exception_leaves"]
_is_normal_live_close_error = _ns["_is_normal_live_close_error"]
_is_transient_live_connection_error = _ns["_is_transient_live_connection_error"]
_is_websocket_abnormal_close = _ns["_is_websocket_abnormal_close"]
_is_recoverable_live_disconnect = _ns["_is_recoverable_live_disconnect"]
RecoverableLiveDisconnect = _ns["RecoverableLiveDisconnect"]
_RECOVERABLE_WS_CLOSE_CODES = _ns["_RECOVERABLE_WS_CLOSE_CODES"]


class FakeConnectionClosedError(Exception):
    pass
FakeConnectionClosedError.__name__ = "ConnectionClosedError"
FakeConnectionClosedError.__qualname__ = "ConnectionClosedError"


# ═══════════════════════════ TESTS ═══════════════════════════

class TestWebsocketAbnormalClose(unittest.TestCase):

    def test_api_error_1006_recognized(self):
        self.assertTrue(_is_websocket_abnormal_close(FakeAPIError(1006)))

    def test_api_error_1001_recognized(self):
        self.assertTrue(_is_websocket_abnormal_close(FakeAPIError(1001)))

    def test_api_error_1011_recognized(self):
        self.assertTrue(_is_websocket_abnormal_close(FakeAPIError(1011)))

    def test_connection_closed_error_recognized(self):
        self.assertTrue(_is_websocket_abnormal_close(
            FakeConnectionClosedError("no close frame received or sent")))

    def test_no_close_frame_message_recognized(self):
        self.assertTrue(_is_websocket_abnormal_close(
            Exception("no close frame received or sent")))

    def test_abnormal_closure_message_recognized(self):
        self.assertTrue(_is_websocket_abnormal_close(
            Exception("1006 abnormal closure [internal]")))

    def test_normal_api_error_400_not_matched(self):
        self.assertFalse(_is_websocket_abnormal_close(FakeAPIError(400)))

    def test_random_exception_not_matched(self):
        self.assertFalse(_is_websocket_abnormal_close(ValueError("unrelated")))


class TestRecoverableDisconnectWith1006(unittest.TestCase):

    def _eg(self, *exceptions):
        return ExceptionGroup("unhandled errors in a TaskGroup", list(exceptions))

    def test_real_crash_recoverable(self):
        """Exact reproduction of the 02:08:46 crash."""
        eg = self._eg(
            FakeAPIError(1006, None, None),
            ConnectionResetError("[Errno 104] Connection reset by peer"),
        )
        self.assertTrue(_is_recoverable_live_disconnect(eg))

    def test_api_error_1006_alone(self):
        self.assertTrue(_is_recoverable_live_disconnect(FakeAPIError(1006)))

    def test_connection_reset_alone(self):
        self.assertTrue(_is_recoverable_live_disconnect(
            ConnectionResetError("reset")))

    def test_connection_closed_error_alone(self):
        self.assertTrue(_is_recoverable_live_disconnect(
            FakeConnectionClosedError("no close frame")))

    def test_mixed_all_recoverable(self):
        eg = self._eg(
            FakeAPIError(1006),
            FakeConnectionClosedError("no close frame"),
            ConnectionResetError("reset"),
        )
        self.assertTrue(_is_recoverable_live_disconnect(eg))

    def test_fatal_mixed_NOT_recoverable(self):
        eg = self._eg(
            FakeAPIError(1006),
            RuntimeError("fatal unexpected error"),
        )
        self.assertFalse(_is_recoverable_live_disconnect(eg))

    def test_recoverable_disconnect_plus_1006(self):
        eg = self._eg(
            RecoverableLiveDisconnect("GoAway", category="provider_goaway"),
            FakeAPIError(1006),
        )
        self.assertTrue(_is_recoverable_live_disconnect(eg))

    def test_empty_leaves_not_recoverable(self):
        class EmptyGroup(BaseException):
            exceptions = []
        self.assertFalse(_is_recoverable_live_disconnect(EmptyGroup()))


class TestExceptionLeaves(unittest.TestCase):

    def test_flat(self):
        self.assertEqual(len(list(_exception_leaves(ValueError("x")))), 1)

    def test_group_two(self):
        eg = ExceptionGroup("g", [ValueError("a"), TypeError("b")])
        self.assertEqual(len(list(_exception_leaves(eg))), 2)

    def test_nested(self):
        inner = ExceptionGroup("i", [ValueError("a"), TypeError("b")])
        outer = ExceptionGroup("o", [inner, RuntimeError("c")])
        self.assertEqual(len(list(_exception_leaves(outer))), 3)

    def test_real_crash_structure(self):
        eg = ExceptionGroup("TaskGroup", [
            FakeAPIError(1006), ConnectionResetError("104")])
        leaves = list(_exception_leaves(eg))
        self.assertEqual(len(leaves), 2)


class TestCloseCodes(unittest.TestCase):

    def test_expected_codes(self):
        self.assertEqual(_RECOVERABLE_WS_CLOSE_CODES,
                         {1001, 1006, 1011, 1012, 1013, 1014})

    def test_1000_excluded(self):
        self.assertNotIn(1000, _RECOVERABLE_WS_CLOSE_CODES)


class TestNoRegression(unittest.TestCase):

    def test_connection_reset_transient(self):
        self.assertTrue(_is_transient_live_connection_error(
            ConnectionResetError("reset")))

    def test_timeout_transient(self):
        self.assertTrue(_is_transient_live_connection_error(
            TimeoutError("timed out")))

    def test_recoverable_disconnect_works(self):
        self.assertTrue(_is_recoverable_live_disconnect(
            RecoverableLiveDisconnect("test", category="transport")))

    def test_normal_close_1000(self):
        exc = FakeAPIError(1000, "ok")
        exc.args = ("1000 (ok)",)
        self.assertTrue(_is_normal_live_close_error(exc))


if __name__ == "__main__":
    unittest.main()
