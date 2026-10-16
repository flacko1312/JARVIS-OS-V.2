"""Tests for Loop Guards — Phase 6 of GREEN Foundation."""
from __future__ import annotations

import unittest

from core.green.loop_guard import LoopDetection, LoopGuard


class TestLoopGuard(unittest.TestCase):
    def test_no_loop_single_op(self):
        guard = LoopGuard()
        result = guard.check_operation(action="read", tool="file_controller")
        assert not result.detected

    def test_same_op_loop_detected(self):
        guard = LoopGuard(max_same_operation=3)
        for _ in range(2):
            r = guard.check_operation(action="read", tool="file", arguments={"path": "/a"})
            assert not r.detected
        r = guard.check_operation(action="read", tool="file", arguments={"path": "/a"})
        assert r.detected
        assert "same operation repeated 3 times" in r.reason

    def test_changing_arguments_no_loop(self):
        guard = LoopGuard(max_same_operation=3)
        for i in range(5):
            r = guard.check_operation(action="read", tool="file", arguments={"path": f"/file{i}"})
        assert not r.detected

    def test_changing_results_no_loop(self):
        guard = LoopGuard(max_same_operation=3)
        for i in range(5):
            r = guard.check_operation(action="read", tool="file", result_category=f"cat{i}")
        assert not r.detected

    def test_same_error_loop(self):
        guard = LoopGuard(max_same_error=3, max_same_operation=10)
        for _ in range(2):
            r = guard.check_operation(action="try", tool="api", error_category="timeout")
            assert not r.detected
        r = guard.check_operation(action="try", tool="api", error_category="timeout")
        assert r.detected
        assert "same error repeated" in r.reason

    def test_different_errors_no_loop(self):
        guard = LoopGuard(max_same_error=3, max_same_operation=10)
        r = guard.check_operation(action="try", tool="api", error_category="timeout")
        r = guard.check_operation(action="try", tool="api", error_category="connection")
        r = guard.check_operation(action="try", tool="api", error_category="auth")
        assert not r.detected

    def test_no_progress_stagnation(self):
        guard = LoopGuard(max_no_progress=3, max_same_operation=20)
        guard.check_operation(action="work", tool="t", arguments={"i": 0}, progress_marker="step1")
        for i in range(1, 4):
            r = guard.check_operation(action="work", tool="t", arguments={"i": i}, progress_marker="step1")
        assert r.detected
        assert "no progress" in r.reason

    def test_progress_resets_count(self):
        guard = LoopGuard(max_no_progress=3)
        guard.check_operation(progress_marker="step1")
        guard.check_operation(progress_marker="step1")
        guard.check_operation(progress_marker="step2")
        guard.check_operation(progress_marker="step2")
        guard.check_operation(progress_marker="step2")
        r = guard.check_operation(progress_marker="step2")
        assert r.detected

    def test_reset(self):
        guard = LoopGuard(max_same_operation=3)
        guard.check_operation(action="x", tool="y")
        guard.check_operation(action="x", tool="y")
        guard.reset()
        r = guard.check_operation(action="x", tool="y")
        assert not r.detected
        assert guard.operation_count == 1

    def test_configurable_thresholds(self):
        guard = LoopGuard(max_same_operation=5)
        for _ in range(4):
            r = guard.check_operation(action="a", tool="b")
        assert not r.detected
        r = guard.check_operation(action="a", tool="b")
        assert r.detected

    def test_structured_reason(self):
        guard = LoopGuard(max_same_operation=2)
        guard.check_operation(action="a", tool="b")
        r = guard.check_operation(action="a", tool="b")
        assert r.detected
        assert r.repeat_count == 2
        assert r.fingerprint != ""
        assert r.recommendation == "stop"

    def test_read_progress_not_falsely_blocked(self):
        guard = LoopGuard(max_same_operation=3)
        r1 = guard.check_operation(action="read", tool="file", arguments={"path": "/a"})
        r2 = guard.check_operation(action="read", tool="file", arguments={"path": "/b"})
        r3 = guard.check_operation(action="read", tool="file", arguments={"path": "/c"})
        assert not r1.detected
        assert not r2.detected
        assert not r3.detected


class TestLoopDetection(unittest.TestCase):
    def test_not_detected(self):
        ld = LoopDetection(detected=False)
        assert not ld.detected
        assert ld.reason == ""

    def test_detected(self):
        ld = LoopDetection(detected=True, reason="loop", repeat_count=3)
        assert ld.detected
        assert ld.repeat_count == 3


if __name__ == "__main__":
    unittest.main()
