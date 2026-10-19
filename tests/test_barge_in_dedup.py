"""Tests for barge-in dedup — one human interruption = one local cut."""
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
        self._next_decision = None

    @property
    def accepted(self):
        return self._accepted

    def set_next(self, decision):
        self._next_decision = decision

    def process(self, data, playback_active=False):
        if self._next_decision is not None:
            d = self._next_decision
            self._accepted = d.accepted
            return d
        return FakeDecision()

    def start_playback(self):
        self._accepted = False

    def stop_playback(self):
        self._accepted = False

    def observe_playback(self, chunk, sample_rate=24000):
        pass


class FakeUI:
    def __init__(self):
        self.muted = False
        self._state = "LISTENING"

    def set_state(self, s):
        self._state = s

    def set_input_audio_level(self, v):
        pass

    def set_output_audio_level(self, v):
        pass


class StubJarvis:
    def __init__(self):
        self._speaking_lock = threading.Lock()
        self._is_speaking = True
        self._barge_in_gate = FakeGate()
        self._barge_in_candidate_logged = False
        self._barge_in_last_reject_log = 0.0
        self._local_barge_in_active = False
        self.audio_in_queue = asyncio.Queue()
        self.ui = FakeUI()
        self._interrupt_calls = []
        self._forwarded_frames = []

    def set_speaking(self, value):
        with self._speaking_lock:
            previous = self._is_speaking
            self._is_speaking = value
        gate = self._barge_in_gate
        if gate is not None and value != previous:
            if value:
                gate.start_playback()
                self._barge_in_candidate_logged = False
                self._local_barge_in_active = False
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

    def _log_barge_in(self, event, decision):
        pass

    def _enqueue_microphone_audio(self, frame):
        self._forwarded_frames.append(frame)


def run_process_mic(stub, decision, monitor=None):
    """Simulate _process_microphone_audio with dedup logic."""
    gate = stub._barge_in_gate
    previously_accepted = gate.accepted
    gate.set_next(decision)
    result = gate.process(b"fake_audio", playback_active=stub._is_speaking)
    now = time.monotonic()

    if result.candidate and not stub._barge_in_candidate_logged:
        stub._barge_in_candidate_logged = True

    if result.rejected_reason and now - stub._barge_in_last_reject_log >= 1.0:
        stub._barge_in_last_reject_log = now
        if monitor:
            monitor.record_barge_in(accepted=False)

    if result.accepted and not previously_accepted and not stub._local_barge_in_active:
        stub._local_barge_in_active = True
        stub._interrupt_live_playback("local_barge_in")
        if monitor:
            monitor.record_barge_in(accepted=True)

    for frame in result.forward_frames:
        stub._enqueue_microphone_audio(frame)

    return result


class TestBargeInDedup(unittest.TestCase):

    def setUp(self):
        self.stub = StubJarvis()
        self.stub._is_speaking = True
        for i in range(5):
            self.stub.audio_in_queue.put_nowait(b"chunk_%d" % i)

    def test_first_accepted_triggers_one_interrupt(self):
        decision = FakeDecision(accepted=True)
        run_process_mic(self.stub, decision)
        self.assertEqual(len(self.stub._interrupt_calls), 1)
        self.assertEqual(self.stub._interrupt_calls[0]["reason"], "local_barge_in")

    def test_repeated_accepted_same_intervention_no_re_interrupt(self):
        """Multiple accepted from same speech → only 1 interrupt."""
        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.assertEqual(len(self.stub._interrupt_calls), 1)

        # Gate resets accepted via stop_playback, then re-accepts
        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.assertEqual(len(self.stub._interrupt_calls), 1)  # Still 1

        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.assertEqual(len(self.stub._interrupt_calls), 1)  # Still 1

    def test_voice_frames_still_forwarded_during_dedup(self):
        """Even when dedup blocks interrupts, voice frames are still forwarded."""
        run_process_mic(self.stub, FakeDecision(accepted=True, forward_frames=[b"f1"]))
        run_process_mic(self.stub, FakeDecision(accepted=True, forward_frames=[b"f2"]))
        self.assertEqual(self.stub._forwarded_frames, [b"f1", b"f2"])

    def test_provider_interruption_after_dedup_is_safe(self):
        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.stub._interrupt_live_playback("provider_interruption")
        self.assertEqual(len(self.stub._interrupt_calls), 2)
        self.assertEqual(self.stub._interrupt_calls[1]["flushed"], 0)

    def test_second_real_interruption_works(self):
        """After JARVIS speaks again, a new barge-in can interrupt."""
        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.assertEqual(len(self.stub._interrupt_calls), 1)

        # JARVIS starts speaking again (new turn)
        self.stub.set_speaking(True)
        for i in range(3):
            self.stub.audio_in_queue.put_nowait(b"new_chunk_%d" % i)

        # New barge-in should work
        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.assertEqual(len(self.stub._interrupt_calls), 2)
        self.assertEqual(self.stub._interrupt_calls[1]["reason"], "local_barge_in")
        self.assertEqual(self.stub._interrupt_calls[1]["flushed"], 3)

    def test_dedup_resets_on_set_speaking_true(self):
        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.assertTrue(self.stub._local_barge_in_active)

        self.stub.set_speaking(True)
        self.assertFalse(self.stub._local_barge_in_active)

    def test_no_audio_lost(self):
        """Forward frames from all decisions reach Gemini."""
        run_process_mic(self.stub, FakeDecision(accepted=True, forward_frames=[b"a", b"b"]))
        run_process_mic(self.stub, FakeDecision(accepted=True, forward_frames=[b"c"]))
        run_process_mic(self.stub, FakeDecision(accepted=False, forward_frames=[b"d"]))
        self.assertEqual(self.stub._forwarded_frames, [b"a", b"b", b"c", b"d"])

    def test_no_deadlock(self):
        """Rapid fire sequence completes without hanging."""
        for _ in range(100):
            run_process_mic(self.stub, FakeDecision(accepted=True, forward_frames=[b"x"]))
        self.assertEqual(len(self.stub._interrupt_calls), 1)
        self.assertEqual(len(self.stub._forwarded_frames), 100)

    def test_final_state_listening(self):
        run_process_mic(self.stub, FakeDecision(accepted=True))
        self.assertFalse(self.stub._is_speaking)
        self.assertEqual(self.stub.ui._state, "LISTENING")

    def test_metrics_no_duplicate_accepts(self):
        """One human barge-in = 1 barge_in_accepted, not N."""
        monitor = VoiceStabilityMonitor()
        run_process_mic(self.stub, FakeDecision(accepted=True), monitor=monitor)
        run_process_mic(self.stub, FakeDecision(accepted=True), monitor=monitor)
        run_process_mic(self.stub, FakeDecision(accepted=True), monitor=monitor)
        m = monitor.get_metrics()
        self.assertEqual(m["audio"]["barge_in_accepted"], 1)

    def test_metrics_second_real_barge_in_counted(self):
        """Second real barge-in after new turn is counted."""
        monitor = VoiceStabilityMonitor()
        run_process_mic(self.stub, FakeDecision(accepted=True), monitor=monitor)

        self.stub.set_speaking(True)
        run_process_mic(self.stub, FakeDecision(accepted=True), monitor=monitor)

        m = monitor.get_metrics()
        self.assertEqual(m["audio"]["barge_in_accepted"], 2)


if __name__ == "__main__":
    unittest.main()
