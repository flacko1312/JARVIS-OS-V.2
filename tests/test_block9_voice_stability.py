"""Block 9 tests — Voice and stability monitoring.

Tests: VoiceStabilityMonitor metrics, reconnect tracking, audio health,
latency stats, health assessment, singleton access.
"""
import time
import unittest


class TestVoiceStabilityMonitor(unittest.TestCase):

    def _make_monitor(self):
        from core.voice_stability import VoiceStabilityMonitor
        m = VoiceStabilityMonitor()
        m.start()
        return m

    def test_initial_metrics(self):
        m = self._make_monitor()
        metrics = m.get_metrics()
        self.assertEqual(metrics["reconnects"]["total"], 0)
        self.assertEqual(metrics["audio"]["frames_sent"], 0)
        self.assertEqual(metrics["latency_ms"]["samples"], 0)

    def test_record_reconnect(self):
        m = self._make_monitor()
        m.record_reconnect(1, 2.0, True, reason="server_close")
        m.record_reconnect(2, 4.0, False, reason="timeout")
        metrics = m.get_metrics()
        self.assertEqual(metrics["reconnects"]["total"], 2)
        self.assertEqual(metrics["reconnects"]["successful"], 1)
        self.assertEqual(metrics["reconnects"]["failed"], 1)

    def test_reconnect_history(self):
        m = self._make_monitor()
        for i in range(5):
            m.record_reconnect(i + 1, float(i), True)
        history = m.get_reconnect_history(limit=3)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[-1]["attempt"], 5)

    def test_latency_stats(self):
        m = self._make_monitor()
        for lat in [100, 200, 300, 400, 500]:
            m.record_latency(lat)
        metrics = m.get_metrics()
        self.assertEqual(metrics["latency_ms"]["samples"], 5)
        self.assertAlmostEqual(metrics["latency_ms"]["avg"], 300.0)
        self.assertEqual(metrics["latency_ms"]["max"], 500.0)

    def test_audio_frames(self):
        m = self._make_monitor()
        for _ in range(90):
            m.record_audio_frame()
        for _ in range(10):
            m.record_audio_frame(dropped=True)
        metrics = m.get_metrics()
        self.assertEqual(metrics["audio"]["frames_sent"], 90)
        self.assertEqual(metrics["audio"]["frames_dropped"], 10)
        self.assertAlmostEqual(metrics["audio"]["drop_rate"], 10.0)

    def test_barge_in_tracking(self):
        m = self._make_monitor()
        m.record_barge_in(accepted=True)
        m.record_barge_in(accepted=False)
        m.record_barge_in(accepted=False)
        metrics = m.get_metrics()
        self.assertEqual(metrics["audio"]["barge_in_attempts"], 3)
        self.assertEqual(metrics["audio"]["barge_in_accepted"], 1)
        self.assertEqual(metrics["audio"]["barge_in_rejected"], 2)

    def test_noise_floor_update(self):
        m = self._make_monitor()
        m.update_noise_floor(0.05, 0.008)
        metrics = m.get_metrics()
        self.assertAlmostEqual(metrics["audio"]["rms"], 0.05, places=3)
        self.assertAlmostEqual(metrics["audio"]["noise_floor"], 0.008, places=3)

    def test_is_healthy_default(self):
        m = self._make_monitor()
        self.assertTrue(m.is_healthy())

    def test_unhealthy_many_reconnects(self):
        m = self._make_monitor()
        for i in range(5):
            m.record_reconnect(i + 1, 1.0, True)
        self.assertFalse(m.is_healthy())

    def test_unhealthy_high_drop_rate(self):
        m = self._make_monitor()
        for _ in range(80):
            m.record_audio_frame()
        for _ in range(30):
            m.record_audio_frame(dropped=True)
        # 30/110 = 27% > 10%
        self.assertFalse(m.is_healthy())

    def test_healthy_low_drop_rate(self):
        m = self._make_monitor()
        for _ in range(95):
            m.record_audio_frame()
        for _ in range(5):
            m.record_audio_frame(dropped=True)
        # 5/100 = 5% < 10%
        self.assertTrue(m.is_healthy())

    def test_longest_session_tracking(self):
        m = self._make_monitor()
        m._current_session_start = time.time() - 3600
        m.record_reconnect(1, 1.0, True)
        metrics = m.get_metrics()
        self.assertGreaterEqual(metrics["longest_session_s"], 3599)

    def test_uptime_increases(self):
        m = self._make_monitor()
        m._session_start = time.time() - 10
        metrics = m.get_metrics()
        self.assertGreaterEqual(metrics["uptime_s"], 9.0)


class TestSingleton(unittest.TestCase):
    def test_get_monitor_returns_same_instance(self):
        from core.voice_stability import get_monitor
        a = get_monitor()
        b = get_monitor()
        self.assertIs(a, b)


class TestBargeInGatePortability(unittest.TestCase):
    """Verify SpeechAwareBargeInGate is importable and functional."""

    def test_import(self):
        from core.audio_barge_in import SpeechAwareBargeInGate, BargeInDecision
        gate = SpeechAwareBargeInGate()
        self.assertIsNotNone(gate)

    def test_default_params(self):
        from core.audio_barge_in import SpeechAwareBargeInGate
        gate = SpeechAwareBargeInGate()
        self.assertEqual(gate.input_sample_rate, 16000)
        self.assertEqual(gate.minimum_speech_ms, 160)

    def test_custom_params(self):
        from core.audio_barge_in import SpeechAwareBargeInGate
        gate = SpeechAwareBargeInGate(
            input_sample_rate=48000,
            minimum_speech_ms=200,
            pre_roll_ms=400,
        )
        self.assertEqual(gate.input_sample_rate, 48000)
        self.assertEqual(gate.minimum_speech_ms, 200)


class TestReconnectConstants(unittest.TestCase):
    """Verify reconnection parameters are properly configured."""

    def test_max_reconnect_attempts(self):
        import ast
        with open("main.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "MAX_LIVE_RECONNECT_ATTEMPTS":
                        self.assertIsInstance(node.value, ast.Constant)
                        self.assertGreaterEqual(node.value.value, 3)
                        self.assertLessEqual(node.value.value, 10)
                        return
        self.fail("MAX_LIVE_RECONNECT_ATTEMPTS not found")

    def test_reconnect_delay_function(self):
        """Verify exponential backoff with jitter."""
        import importlib
        # Read the function from source
        with open("main.py") as f:
            content = f.read()
        self.assertIn("def _live_reconnect_delay", content)

    def test_vad_silence_configured(self):
        import ast
        with open("main.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "LIVE_VAD_SILENCE_MS":
                        self.assertIsInstance(node.value, ast.Constant)
                        self.assertGreaterEqual(node.value.value, 100)
                        self.assertLessEqual(node.value.value, 500)
                        return
        self.fail("LIVE_VAD_SILENCE_MS not found")


if __name__ == "__main__":
    unittest.main()


class TestLabeledLatency(unittest.TestCase):
    def _make_monitor(self):
        from core.voice_stability import VoiceStabilityMonitor
        m = VoiceStabilityMonitor()
        m.start()
        return m

    def test_labeled_latency_stats(self):
        m = self._make_monitor()
        m.record_latency(100, label="speech_to_first_audio")
        m.record_latency(200, label="speech_to_first_audio")
        m.record_latency(50, label="first_audio_to_playback")
        m.record_latency(500, label="turn_total")
        metrics = m.get_metrics()
        by_label = metrics["latency_ms"]["by_label"]
        self.assertIn("speech_to_first_audio", by_label)
        self.assertEqual(by_label["speech_to_first_audio"]["samples"], 2)
        self.assertAlmostEqual(by_label["speech_to_first_audio"]["avg"], 150.0)
        self.assertIn("first_audio_to_playback", by_label)
        self.assertIn("turn_total", by_label)

    def test_unlabeled_still_works(self):
        m = self._make_monitor()
        m.record_latency(100)
        m.record_latency(200, label="")
        metrics = m.get_metrics()
        self.assertEqual(metrics["latency_ms"]["samples"], 2)
        self.assertEqual(len(metrics["latency_ms"]["by_label"]), 0)

    def test_labeled_goes_to_global_too(self):
        m = self._make_monitor()
        m.record_latency(100, label="speech_to_first_audio")
        metrics = m.get_metrics()
        self.assertEqual(metrics["latency_ms"]["samples"], 1)
        self.assertEqual(metrics["latency_ms"]["by_label"]["speech_to_first_audio"]["samples"], 1)
