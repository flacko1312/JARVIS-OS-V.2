import time
from collections import deque

import numpy as np

from core.spotify_aec import SpotifyProcessAEC


class FakeAEC:
    def __init__(self, cleaned_value=50):
        self.calls = 0
        self.resets = 0
        self.cleaned_value = cleaned_value

    def process(self, near, far):
        self.calls += 1
        return np.full_like(near, self.cleaned_value)

    def reset(self):
        self.resets += 1


class FakeVAD:
    def __init__(self, probability=0.1):
        self.probability = probability
        self.resets = 0

    def process(self, audio):
        return self.probability

    def reset(self):
        self.resets += 1


def manager(*, mode="shadow_v2", cleaned=50, probability=0.1):
    obj = SpotifyProcessAEC.__new__(SpotifyProcessAEC)
    obj.sample_rate = 16000
    obj.mode = mode
    obj.enabled = mode != "off"
    import threading
    obj._lock = threading.Lock()
    obj._buffer = bytearray()
    obj._last_reference_at = 0.0
    obj._aec = FakeAEC(cleaned)
    obj._vad = FakeVAD(probability)
    obj._warned = False
    obj._near_candidate_chunks = 0
    obj._near_speech_until = 0.0
    obj._pause_guard_until = 0.0
    obj._pause_guard_seconds = 0.35
    obj._preroll = deque(maxlen=4)
    obj._last_metrics = {}
    return obj


def pcm(value=1000, samples=320):
    return np.full(samples, value, dtype=np.int16).tobytes()


def fresh_reference(obj, value=800, samples=320):
    obj._buffer.extend(pcm(value, samples))
    obj._last_reference_at = time.monotonic()


def test_off_mode_is_absolute_raw_bypass():
    obj = manager(mode="off")
    raw = pcm(1234)
    assert obj.filter_input(raw) == (raw,)
    assert obj._aec.calls == 0


def test_fail_open_without_fresh_spotify_reference():
    obj = manager()
    raw = pcm()
    assert obj.filter_input(raw) == (raw,)
    assert obj._aec.calls == 0


def test_silent_spotify_reference_bypasses_gate():
    obj = manager()
    raw = pcm()
    fresh_reference(obj, 0)
    assert obj.filter_input(raw) == (raw,)
    assert obj._aec.calls == 0


def test_v1_spotify_only_audio_keeps_legacy_packet_gap_behavior():
    obj = manager(mode="shadow_v1", cleaned=50, probability=0.1)
    raw = pcm(1200)
    fresh_reference(obj)
    assert obj.filter_input(raw) == ()


def test_v2_spotify_only_audio_becomes_realtime_silence_not_packet_gap():
    obj = manager(mode="shadow_v2", cleaned=50, probability=0.1)
    raw = pcm(1200)
    fresh_reference(obj)
    forwarded = obj.filter_input(raw)
    assert forwarded == (bytes(len(raw)),)
    assert len(forwarded[0]) == len(raw)


def test_v2_rejects_voice_like_spotify_residual_when_aec_removed_most_near_energy():
    obj = manager(mode="shadow_v2", cleaned=500, probability=0.95)
    raw = pcm(1200)
    for _ in range(4):
        fresh_reference(obj, 800)
        assert obj.filter_input(raw) == (bytes(len(raw)),)
    assert obj.metrics["retention_ratio"] < 0.55
    assert obj.metrics["gate_open"] == 0.0


def test_v2_three_independent_near_speech_chunks_open_and_flush_original_preroll():
    obj = manager(mode="shadow_v2", cleaned=700, probability=0.9)
    raws = [pcm(900), pcm(920), pcm(940)]
    for raw in raws[:2]:
        fresh_reference(obj, 1400)
        assert obj.filter_input(raw) == (bytes(len(raw)),)
    fresh_reference(obj, 1400)
    forwarded = obj.filter_input(raws[2])
    assert forwarded == tuple(raws)
    assert np.frombuffer(forwarded[-1], dtype=np.int16)[0] == 940


def test_open_v2_gate_forwards_original_not_aec_output():
    obj = manager(mode="shadow_v2", cleaned=700, probability=0.9)
    obj._near_speech_until = time.monotonic() + 1.0
    raw = pcm(1400)
    fresh_reference(obj, 800)
    forwarded = obj.filter_input(raw)
    assert forwarded == (raw,)
    assert np.frombuffer(forwarded[0], dtype=np.int16)[0] == 1400


def test_old_reference_is_never_reused():
    obj = manager()
    raw = pcm()
    obj._buffer.extend(pcm(800))
    obj._last_reference_at = time.monotonic() - 1.0
    assert obj.filter_input(raw) == (raw,)
    assert obj._aec.calls == 0


def test_v3_short_pause_after_user_speech_is_packet_gap_not_silence():
    obj = manager(mode="shadow_v3", cleaned=700, probability=0.9)
    raw = pcm(1200)
    obj._near_speech_until = time.monotonic() - 0.01
    obj._pause_guard_until = time.monotonic() + 0.30
    fresh_reference(obj, 1400)
    assert obj.filter_input(raw) == ()


def test_v3_long_pause_after_guard_becomes_realtime_silence():
    obj = manager(mode="shadow_v3", cleaned=50, probability=0.1)
    raw = pcm(1200)
    obj._near_speech_until = time.monotonic() - 1.0
    obj._pause_guard_until = time.monotonic() - 0.01
    fresh_reference(obj, 1400)
    assert obj.filter_input(raw) == (bytes(len(raw)),)


def test_v3_detected_speech_refreshes_pause_guard():
    obj = manager(mode="shadow_v3", cleaned=900, probability=0.95)
    raws = [pcm(1200), pcm(1250), pcm(1300)]
    for raw in raws[:2]:
        fresh_reference(obj, 900)
        obj.filter_input(raw)
    fresh_reference(obj, 900)
    before = time.monotonic()
    forwarded = obj.filter_input(raws[2])
    assert forwarded[-1] == raws[2]
    assert obj._pause_guard_until >= before + 0.45
