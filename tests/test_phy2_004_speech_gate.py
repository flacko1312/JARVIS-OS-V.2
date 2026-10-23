"""Deterministic speech/noise discrimination tests for PHY2-004 second fix."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

import main
from core.audio_barge_in import SpeechAwareBargeInGate


SR = 16000
FRAME = 1024


def pcm(signal: np.ndarray) -> bytes:
    return (np.clip(signal, -0.99, 0.99) * 32767).astype(np.int16).tobytes()


def voice_frame(*, sample_rate: int = SR, size: int = FRAME, amplitude: float = 0.08) -> bytes:
    t = np.arange(size) / sample_rate
    envelope = 0.72 + 0.28 * np.sin(2 * np.pi * 4.0 * t)
    voice = amplitude * envelope * (
        np.sin(2 * np.pi * 180 * t)
        + 0.50 * np.sin(2 * np.pi * 360 * t)
        + 0.25 * np.sin(2 * np.pi * 720 * t)
    )
    return pcm(voice)


def car_frame() -> bytes:
    t = np.arange(FRAME) / SR
    return pcm(0.10 * np.sin(2 * np.pi * 82 * t) + 0.035 * np.sin(2 * np.pi * 126 * t))


def broadband_frame(seed: int = 1) -> bytes:
    return pcm(0.07 * np.random.default_rng(seed).normal(size=FRAME))


def accept_speech(gate: SpeechAwareBargeInGate, frames: int = 3):
    decisions = [gate.process(voice_frame(), playback_active=True) for _ in range(frames)]
    return decisions


def test_para_like_spoken_interruption_is_accepted():
    decisions = accept_speech(SpeechAwareBargeInGate())
    assert decisions[-1].accepted
    assert len(decisions[-1].forward_frames) == 3


def test_natural_question_like_speech_is_accepted_without_keyword_matching():
    gate = SpeechAwareBargeInGate()
    decisions = [
        gate.process(voice_frame(amplitude=amplitude), playback_active=True)
        for amplitude in (0.06, 0.075, 0.09)
    ]
    assert decisions[-1].accepted
    assert decisions[-1].speech_duration_ms <= 200


def test_short_impulse_noise_is_rejected():
    impulse = np.zeros(FRAME)
    impulse[20:23] = (0.95, -0.85, 0.55)
    decision = SpeechAwareBargeInGate().process(pcm(impulse), playback_active=True)
    assert not decision.accepted
    assert not decision.forward_frames
    assert decision.rejected_reason in {"transient_noise", "broadband_noise", "non_speech_activity"}


def test_repeated_ambient_noise_never_accumulates_as_speech():
    gate = SpeechAwareBargeInGate()
    decisions = [gate.process(broadband_frame(index), playback_active=True) for index in range(20)]
    assert not any(decision.accepted for decision in decisions)
    assert all(not decision.forward_frames for decision in decisions)


def test_car_like_low_frequency_background_is_rejected():
    gate = SpeechAwareBargeInGate()
    decisions = [gate.process(car_frame(), playback_active=True) for _ in range(12)]
    assert {decision.rejected_reason for decision in decisions} == {"low_frequency_noise"}


def test_keyboard_transients_are_rejected():
    gate = SpeechAwareBargeInGate()
    for position in (30, 300, 700):
        samples = np.zeros(FRAME)
        samples[position:position + 2] = (0.8, -0.65)
        decision = gate.process(pcm(samples), playback_active=True)
        assert not decision.accepted
        assert not decision.forward_frames


def test_recent_speaker_playback_leakage_does_not_self_interrupt():
    gate = SpeechAwareBargeInGate()
    output = voice_frame(sample_rate=24000, size=1536, amplitude=0.12)
    gate.observe_playback(output, sample_rate=24000)
    leakage = voice_frame(amplitude=0.035)
    decisions = [gate.process(leakage, playback_active=True) for _ in range(5)]
    assert not any(decision.accepted for decision in decisions)
    assert all(decision.echo_similarity > 0.9 for decision in decisions)
    assert all(decision.rejected_reason == "playback_leakage" for decision in decisions)



def test_real_world_0844_playback_similarity_is_rejected_as_echo():
    gate = SpeechAwareBargeInGate()
    gate._echo_similarity = lambda _fingerprint: (0.844, 0.08)
    decision = gate.process(voice_frame(amplitude=0.035), playback_active=True)
    assert not decision.accepted
    assert decision.rejected_reason == "playback_leakage"


def test_distinct_human_speech_still_interrupts_quickly_during_playback():
    gate = SpeechAwareBargeInGate()
    gate._echo_similarity = lambda _fingerprint: (0.40, 0.08)
    first, second, third = [
        gate.process(voice_frame(amplitude=0.06), playback_active=True)
        for _ in range(3)
    ]
    assert first.candidate and second.candidate
    assert third.accepted
    assert third.speech_duration_ms < 250
def test_sustained_human_speech_interrupts_after_consecutive_frames():
    gate = SpeechAwareBargeInGate()
    first, second, third = accept_speech(gate)
    assert first.candidate and second.candidate
    assert third.accepted


def test_interruption_confirmation_latency_is_bounded_below_250ms():
    gate = SpeechAwareBargeInGate()
    decision = accept_speech(gate)[-1]
    assert decision.accepted
    assert 160 <= decision.speech_duration_ms < 250


def test_repeated_accepted_frames_emit_one_accept_and_no_duplicate_tasks():
    jarvis = main.JarvisLive(SimpleNamespace(
        muted=False, on_text_command=None, on_conversation_toggle=None,
        set_state=lambda _state: None,
    ), cloud_safe=True, api_key="test", external_audio=True)
    jarvis.out_queue = asyncio.Queue()
    jarvis.set_speaking(True)
    jarvis._log_barge_in = MagicMock()

    class ImmediateLoop:
        @staticmethod
        def call_soon_threadsafe(function, *args):
            function(*args)

    for _ in range(6):
        jarvis._process_microphone_audio(voice_frame(), ImmediateLoop())
    accepted = [
        call for call in jarvis._log_barge_in.call_args_list
        if call.args and call.args[0] == "accepted"
    ]
    assert len(accepted) == 1
    assert jarvis.out_queue.qsize() == 6


def test_context_remains_intact_after_accepted_interruption():
    jarvis = main.JarvisLive(SimpleNamespace(
        muted=False, on_text_command=None, on_conversation_toggle=None,
        set_state=lambda _state: None,
    ), cloud_safe=True, api_key="test", external_audio=True)
    jarvis._remember_conversation_text("user", "mi contexto sigue aquÃ­")
    before = list(jarvis._conversation_continuity)
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis.audio_in_queue.put_nowait(b"stale-output")
    jarvis._interrupt_live_playback("provider_interruption")
    assert jarvis._conversation_continuity == before


def test_non_playback_microphone_audio_remains_full_duplex_passthrough():
    gate = SpeechAwareBargeInGate()
    frame = broadband_frame()
    decision = gate.process(frame, playback_active=False)
    assert decision.forward_frames == (frame,)
    assert not decision.accepted


def test_muted_microphone_sends_nothing_during_playback():
    jarvis = main.JarvisLive(SimpleNamespace(
        muted=True, on_text_command=None, on_conversation_toggle=None,
        set_state=lambda _state: None,
    ), cloud_safe=True, api_key="test", external_audio=False)
    jarvis._conversation_requested.set()
    jarvis.out_queue = asyncio.Queue()
    jarvis.set_speaking(True)

    class Input:
        def __init__(self, **kwargs): self.callback = kwargs["callback"]
        def __enter__(self):
            self.callback(SimpleNamespace(tobytes=voice_frame), FRAME, None, None)
            jarvis._conversation_requested.clear()
            return self
        def __exit__(self, *_args): return False

    with patch.object(main.sd, "InputStream", Input):
        asyncio.run(jarvis._listen_audio())
    assert jarvis.out_queue.empty()


def test_gate_reset_on_standby_drops_candidate_but_not_future_listening_audio():
    gate = SpeechAwareBargeInGate()
    assert gate.process(voice_frame(), playback_active=True).candidate
    gate.stop_playback()
    frame = voice_frame()
    decision = gate.process(frame, playback_active=False)
    assert decision.forward_frames == (frame,)
    assert not gate.accepted


def test_high_echo_similarity_needs_longer_confirmation_before_barge_in():
    gate = SpeechAwareBargeInGate()
    with patch.object(gate, "_echo_similarity", return_value=(0.81, 0.05)):
        decisions = [gate.process(voice_frame(), playback_active=True) for _ in range(5)]
    assert decisions[2].candidate and not decisions[2].accepted
    assert decisions[3].candidate and not decisions[3].accepted
    assert decisions[4].accepted
    assert decisions[4].speech_duration_ms >= 300
