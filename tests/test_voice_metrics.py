"""Tests for VoiceStabilityMonitor metric wiring."""
import sys
import unittest

sys.path.insert(0, "/home/flako1312/jarvis-headless")

from core.voice_stability import VoiceStabilityMonitor


class TestVoiceMetricsWiring(unittest.TestCase):

    def setUp(self):
        self.monitor = VoiceStabilityMonitor()

    def test_record_audio_frame_increments(self):
        self.monitor.record_audio_frame(dropped=False)
        self.monitor.record_audio_frame(dropped=False)
        self.monitor.record_audio_frame(dropped=True)
        m = self.monitor.get_metrics()
        self.assertEqual(m["audio"]["frames_sent"], 2)
        self.assertEqual(m["audio"]["frames_dropped"], 1)

    def test_record_barge_in_increments(self):
        self.monitor.record_barge_in(accepted=True)
        self.monitor.record_barge_in(accepted=False)
        self.monitor.record_barge_in(accepted=False)
        m = self.monitor.get_metrics()
        self.assertEqual(m["audio"]["barge_in_attempts"], 3)
        self.assertEqual(m["audio"]["barge_in_accepted"], 1)
        self.assertEqual(m["audio"]["barge_in_rejected"], 2)

    def test_update_noise_floor(self):
        self.monitor.update_noise_floor(0.05, 0.02)
        m = self.monitor.get_metrics()
        self.assertAlmostEqual(m["audio"]["rms"], 0.05)
        self.assertAlmostEqual(m["audio"]["noise_floor"], 0.02)

    def test_metrics_structure(self):
        m = self.monitor.get_metrics()
        self.assertIn("audio", m)
        audio = m["audio"]
        for key in ("frames_sent", "frames_dropped", "rms", "noise_floor",
                     "last_activity", "barge_in_attempts", "barge_in_accepted",
                     "barge_in_rejected"):
            self.assertIn(key, audio, f"Key '{key}' missing from audio metrics")

    def test_frames_sent_zero_initially(self):
        m = self.monitor.get_metrics()
        self.assertEqual(m["audio"]["frames_sent"], 0)
        self.assertEqual(m["audio"]["frames_dropped"], 0)

    def test_barge_in_zero_initially(self):
        m = self.monitor.get_metrics()
        self.assertEqual(m["audio"]["barge_in_attempts"], 0)
        self.assertEqual(m["audio"]["barge_in_accepted"], 0)
        self.assertEqual(m["audio"]["barge_in_rejected"], 0)

    def test_drop_rate_computed(self):
        self.monitor.record_audio_frame(dropped=False)
        self.monitor.record_audio_frame(dropped=False)
        self.monitor.record_audio_frame(dropped=True)
        m = self.monitor.get_metrics()
        drop_rate = m["audio"]["drop_rate"]
        self.assertGreater(drop_rate, 0)
        self.assertLess(drop_rate, 100)


if __name__ == "__main__":
    unittest.main()
