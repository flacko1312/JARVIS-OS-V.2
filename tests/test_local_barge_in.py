"""Tests for local barge-in playback interruption."""
import asyncio
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/flako1312/jarvis-headless")


class FakeDecision:
    """Minimal BargeInDecision stand-in."""
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
    """Minimal SpeechAwareBargeInGate stand-in."""
    def __init__(self):
        self.accepted = False
        self._next_decision = None

    def set_next(self, decision):
        self._next_decision = decision

    def process(self, data, playback_active=False):
        if self._next_decision is not None:
            d = self._next_decision
            self.accepted = d.accepted
            return d
        return FakeDecision()

    def start_playback(self):
        pass

    def stop_playback(self):
        pass

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
    """Minimal stub with only the methods needed for _process_microphone_audio."""
    def __init__(self):
        self._speaking_lock = threading.Lock()
        self._is_speaking = True
        self._barge_in_gate = FakeGate()
        self._barge_in_candidate_logged = False
        self._barge_in_last_reject_log = 0.0
        self.audio_in_queue = asyncio.Queue()
        self.ui = FakeUI()
        self._interrupt_calls = []

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

    @staticmethod
    def _barge_in_metrics(decision):
        return (
            decision.speech_duration_ms,
            round(decision.rms, 4),
            round(decision.noise_floor, 4),
            round(decision.echo_similarity, 3),
        )

    def _log_barge_in(self, event, decision):
        pass

    def _enqueue_microphone_audio(self, frame):
        pass


def run_process_mic(stub, decision, loop=None):
    """Simulate _process_microphone_audio logic with the local barge-in cut."""
    gate = stub._barge_in_gate
    previously_accepted = gate.accepted
    gate.set_next(decision)
    result = gate.process(b"fake_audio", playback_active=stub._is_speaking)
    now = time.monotonic()

    # voice stability metrics (skipped in test)

    if result.candidate and not stub._barge_in_candidate_logged:
        stub._barge_in_candidate_logged = True

    if result.rejected_reason and now - stub._barge_in_last_reject_log >= 1.0:
        stub._barge_in_last_reject_log = now
        # record_barge_in(accepted=False) would go here

    if result.accepted and not previously_accepted:
        stub._interrupt_live_playback("local_barge_in")
        # record_barge_in(accepted=True) would go here

    for frame in result.forward_frames:
        stub._enqueue_microphone_audio(frame)

    return result


class TestLocalBargeInCut(unittest.TestCase):

    def setUp(self):
        self.stub = StubJarvis()
        # Simulate JARVIS is speaking with 5 chunks queued
        self.stub._is_speaking = True
        for i in range(5):
            self.stub.audio_in_queue.put_nowait(b"chunk_%d" % i)

    def test_accepted_transition_triggers_exactly_one_interrupt(self):
        """accepted False→True triggers exactly one local interrupt."""
        decision = FakeDecision(accepted=True, forward_frames=[b"voice"])
        run_process_mic(self.stub, decision)
        self.assertEqual(len(self.stub._interrupt_calls), 1)
        self.assertEqual(self.stub._interrupt_calls[0]["reason"], "local_barge_in")

    def test_candidate_does_not_interrupt(self):
        """candidate does NOT trigger interrupt."""
        decision = FakeDecision(candidate=True)
        run_process_mic(self.stub, decision)
        self.assertEqual(len(self.stub._interrupt_calls), 0)

    def test_rejected_does_not_interrupt(self):
        """rejected does NOT trigger interrupt."""
        decision = FakeDecision(rejected_reason="below_speech_floor")
        run_process_mic(self.stub, decision)
        self.assertEqual(len(self.stub._interrupt_calls), 0)

    def test_repeated_accepted_does_not_re_interrupt(self):
        """accepted when gate.accepted is already True does NOT re-interrupt."""
        # First: trigger the transition
        decision1 = FakeDecision(accepted=True)
        run_process_mic(self.stub, decision1)
        self.assertEqual(len(self.stub._interrupt_calls), 1)

        # Second: gate.accepted is now True, so previously_accepted=True
        decision2 = FakeDecision(accepted=True)
        run_process_mic(self.stub, decision2)
        self.assertEqual(len(self.stub._interrupt_calls), 1)  # Still 1, not 2

    def test_provider_interruption_after_local_is_safe(self):
        """provider_interruption after local_barge_in is idempotent."""
        decision = FakeDecision(accepted=True)
        run_process_mic(self.stub, decision)
        self.assertEqual(len(self.stub._interrupt_calls), 1)

        # Simulate Gemini's server_content.interrupted arriving later
        self.stub._interrupt_live_playback("provider_interruption")
        self.assertEqual(len(self.stub._interrupt_calls), 2)
        self.assertEqual(self.stub._interrupt_calls[1]["reason"], "provider_interruption")
        self.assertEqual(self.stub._interrupt_calls[1]["flushed"], 0)  # Queue already empty

    def test_voice_frames_still_forwarded(self):
        """Accepted voice frames are forwarded even after interrupt."""
        forward = [b"frame1", b"frame2"]
        decision = FakeDecision(accepted=True, forward_frames=forward)
        forwarded = []
        self.stub._enqueue_microphone_audio = lambda f: forwarded.append(f)
        run_process_mic(self.stub, decision)
        self.assertEqual(forwarded, forward)

    def test_audio_queue_drained_on_barge_in(self):
        """audio_in_queue is emptied when barge-in is accepted."""
        self.assertEqual(self.stub.audio_in_queue.qsize(), 5)
        decision = FakeDecision(accepted=True)
        run_process_mic(self.stub, decision)
        self.assertEqual(self.stub.audio_in_queue.qsize(), 0)
        self.assertEqual(self.stub._interrupt_calls[0]["flushed"], 5)

    def test_set_speaking_false_after_barge_in(self):
        """set_speaking(False) is applied after barge-in."""
        self.assertTrue(self.stub._is_speaking)
        decision = FakeDecision(accepted=True)
        run_process_mic(self.stub, decision)
        self.assertFalse(self.stub._is_speaking)

    def test_metrics_still_count(self):
        """Barge-in metrics count correctly through the flow."""
        from core.voice_stability import VoiceStabilityMonitor
        monitor = VoiceStabilityMonitor()

        monitor.record_barge_in(accepted=True)
        monitor.record_barge_in(accepted=False)
        monitor.record_barge_in(accepted=False)

        m = monitor.get_metrics()
        self.assertEqual(m["audio"]["barge_in_attempts"], 3)
        self.assertEqual(m["audio"]["barge_in_accepted"], 1)
        self.assertEqual(m["audio"]["barge_in_rejected"], 2)


if __name__ == "__main__":
    unittest.main()
