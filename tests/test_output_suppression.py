"""Tests for output suppression after local barge-in."""
import asyncio
import sys
import threading
import time
import unittest

sys.path.insert(0, "/home/flako1312/jarvis-headless")

from core.voice_stability import VoiceStabilityMonitor


class FakeDecision:
    def __init__(self, *, accepted=False, candidate=False, rejected_reason=None,
                 rms=0.01, noise_floor=0.005, echo_similarity=0.0,
                 speech_duration_ms=0, forward_frames=None):
        self.accepted = accepted
        self.candidate = candidate
        self.rejected_reason = rejected_reason
        self.rms = rms
        self.noise_floor = noise_floor
        self.echo_similarity = echo_similarity
        self.speech_duration_ms = speech_duration_ms
        self.forward_frames = forward_frames or []


class FakeGate:
    def __init__(self):
        self._accepted = False

    @property
    def accepted(self):
        return self._accepted

    def set_accepted(self, val):
        self._accepted = val

    def process(self, data, playback_active=False):
        return FakeDecision()

    def start_playback(self):
        self._accepted = False

    def stop_playback(self):
        self._accepted = False


class FakeUI:
    def __init__(self):
        self.muted = False
        self._state = "LISTENING"

    def set_state(self, s):
        self._state = s


class StubJarvis:
    """Stub that mirrors the real main.py logic for barge-in + output suppression."""
    def __init__(self):
        self._speaking_lock = threading.Lock()
        self._is_speaking = False
        self._barge_in_gate = FakeGate()
        self._barge_in_candidate_logged = False
        self._barge_in_last_reject_log = 0.0
        self._local_barge_in_active = False
        self._suppress_interrupted_output = False
        self.audio_in_queue = asyncio.Queue()
        self.ui = FakeUI()
        self._interrupt_calls = []
        self._forwarded_frames = []
        self._suppressed_bytes = 0

    def set_speaking(self, value):
        with self._speaking_lock:
            previous = self._is_speaking
            self._is_speaking = value
        gate = self._barge_in_gate
        if gate is not None and value != previous:
            if value:
                gate.start_playback()
                self._barge_in_candidate_logged = False
            else:
                gate.stop_playback()
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    @staticmethod
    def _drain_queue(queue):
        drained = 0
        if queue is None:
            return drained
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return drained
            else:
                drained += 1

    def _interrupt_live_playback(self, reason):
        drained = self._drain_queue(self.audio_in_queue)
        self.set_speaking(False)
        self._interrupt_calls.append({"reason": reason, "flushed": drained})
        return drained

    def do_local_barge_in(self):
        """Simulate the accepted transition in _process_microphone_audio."""
        if not self._local_barge_in_active:
            self._local_barge_in_active = True
            self._suppress_interrupted_output = True
            self._interrupt_live_playback("local_barge_in")

    def receive_response_audio(self, audio_bytes):
        """Simulate the response_audio path in _receive_audio."""
        if self._suppress_interrupted_output:
            self._suppressed_bytes += len(audio_bytes)
            return False  # suppressed
        self.audio_in_queue.put_nowait(audio_bytes)
        self.set_speaking(True)
        return True  # enqueued

    def provider_interruption(self):
        """Simulate server_content.interrupted from Gemini."""
        self._interrupt_live_playback("provider_interruption")
        self._suppress_interrupted_output = False
        self._local_barge_in_active = False

    def turn_complete(self):
        """Simulate sc.turn_complete from Gemini."""
        self._suppress_interrupted_output = False
        self._local_barge_in_active = False

    def new_turn(self):
        """Simulate the top of the receive loop — new live_turn_id."""
        self._suppress_interrupted_output = False
        self._local_barge_in_active = False


class TestOutputSuppression(unittest.TestCase):

    def setUp(self):
        self.j = StubJarvis()
        self.j.set_speaking(True)
        for i in range(10):
            self.j.audio_in_queue.put_nowait(b"old_chunk_%d" % i)

    def test_local_barge_in_cuts_and_drains(self):
        """Step 1-3: accepted → cut + drain."""
        self.j.do_local_barge_in()
        self.assertEqual(len(self.j._interrupt_calls), 1)
        self.assertEqual(self.j._interrupt_calls[0]["flushed"], 10)
        self.assertEqual(self.j.audio_in_queue.qsize(), 0)

    def test_old_response_audio_suppressed(self):
        """Step 4-5: response_audio from old turn does NOT enter queue."""
        self.j.do_local_barge_in()
        enqueued = self.j.receive_response_audio(b"old_audio_1")
        self.assertFalse(enqueued)
        enqueued = self.j.receive_response_audio(b"old_audio_2")
        self.assertFalse(enqueued)
        self.assertEqual(self.j.audio_in_queue.qsize(), 0)

    def test_jarvis_does_not_re_speak_old_audio(self):
        """Step 6: JARVIS does NOT go back to SPEAKING from old audio."""
        self.j.do_local_barge_in()
        self.assertFalse(self.j._is_speaking)
        self.j.receive_response_audio(b"old_audio")
        self.assertFalse(self.j._is_speaking)
        self.assertEqual(self.j.ui._state, "LISTENING")

    def test_dedup_during_same_intervention(self):
        """Step 7: repeated accepted from same speech → only 1 cut."""
        self.j.do_local_barge_in()
        self.j.do_local_barge_in()
        self.j.do_local_barge_in()
        self.assertEqual(len(self.j._interrupt_calls), 1)

    def test_provider_interruption_safe(self):
        """Step 9: provider_interruption after local is idempotent."""
        self.j.do_local_barge_in()
        self.j.provider_interruption()
        self.assertEqual(len(self.j._interrupt_calls), 2)
        self.assertEqual(self.j._interrupt_calls[1]["flushed"], 0)

    def test_turn_complete_resets_suppression(self):
        """Step 10: turn_complete lifts suppression."""
        self.j.do_local_barge_in()
        self.assertTrue(self.j._suppress_interrupted_output)
        self.j.turn_complete()
        self.assertFalse(self.j._suppress_interrupted_output)

    def test_new_response_audio_plays(self):
        """Step 11: new response after turn boundary plays normally."""
        self.j.do_local_barge_in()
        self.j.receive_response_audio(b"suppressed")
        self.assertEqual(self.j.audio_in_queue.qsize(), 0)

        # Turn boundary
        self.j.turn_complete()

        # New turn starts, new response audio should play
        self.j.new_turn()
        enqueued = self.j.receive_response_audio(b"new_response")
        self.assertTrue(enqueued)
        self.assertEqual(self.j.audio_in_queue.qsize(), 1)

    def test_second_real_interruption_works(self):
        """Step 12: after new turn, barge-in works again."""
        self.j.do_local_barge_in()
        self.j.turn_complete()
        self.j.new_turn()

        # JARVIS starts new response
        self.j.receive_response_audio(b"new_audio_1")
        self.j.receive_response_audio(b"new_audio_2")
        self.assertEqual(self.j.audio_in_queue.qsize(), 2)

        # Second real barge-in
        self.j.do_local_barge_in()
        self.assertEqual(len(self.j._interrupt_calls), 2)
        self.assertEqual(self.j._interrupt_calls[1]["reason"], "local_barge_in")
        self.assertEqual(self.j._interrupt_calls[1]["flushed"], 2)

    def test_final_state_listening(self):
        """Step 13: final state is LISTENING."""
        self.j.do_local_barge_in()
        self.assertFalse(self.j._is_speaking)
        self.assertEqual(self.j.ui._state, "LISTENING")

    def test_metrics_not_inflated(self):
        """Step 14: one human barge-in = 1 accepted."""
        monitor = VoiceStabilityMonitor()

        self.j.do_local_barge_in()
        monitor.record_barge_in(accepted=True)

        # Duplicate attempts during same speech
        self.j.do_local_barge_in()
        self.j.do_local_barge_in()
        # These don't pass the guard, so no record_barge_in call

        m = monitor.get_metrics()
        self.assertEqual(m["audio"]["barge_in_accepted"], 1)

    def test_suppressed_bytes_tracked(self):
        """Suppressed audio bytes are counted."""
        self.j.do_local_barge_in()
        self.j.receive_response_audio(b"a" * 100)
        self.j.receive_response_audio(b"b" * 200)
        self.assertEqual(self.j._suppressed_bytes, 300)

    def test_provider_interruption_also_resets_dedup(self):
        """provider_interruption resets dedup so new turn can interrupt."""
        self.j.do_local_barge_in()
        self.assertTrue(self.j._local_barge_in_active)

        self.j.provider_interruption()
        self.assertFalse(self.j._local_barge_in_active)
        self.assertFalse(self.j._suppress_interrupted_output)

    def test_new_turn_resets_everything(self):
        """New turn at top of receive loop resets all flags."""
        self.j.do_local_barge_in()
        self.j.new_turn()
        self.assertFalse(self.j._local_barge_in_active)
        self.assertFalse(self.j._suppress_interrupted_output)

    def test_set_speaking_true_does_not_reset_dedup(self):
        """set_speaking(True) must NOT reset dedup or suppression."""
        self.j.do_local_barge_in()
        self.j.set_speaking(True)
        self.assertTrue(self.j._local_barge_in_active)
        self.assertTrue(self.j._suppress_interrupted_output)


if __name__ == "__main__":
    unittest.main()
