"""Low-latency, speech-aware gate for microphone audio during playback.

The gate never records audio. It keeps only a short in-memory pre-roll and
compact spectral fingerprints long enough to decide whether activity resembles
human speech rather than an impulse, broadband noise, low-frequency traffic, or
JARVIS's own recent playback.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BargeInDecision:
    forward_frames: tuple[bytes, ...] = ()
    candidate: bool = False
    accepted: bool = False
    rejected_reason: str | None = None
    speech_duration_ms: int = 0
    rms: float = 0.0
    noise_floor: float = 0.0
    echo_similarity: float = 0.0


class SpeechAwareBargeInGate:
    """Confirm sustained speech before forwarding mic audio during playback."""

    def __init__(
        self,
        *,
        input_sample_rate: int = 16000,
        minimum_speech_ms: int = 160,
        pre_roll_ms: int = 320,
    ) -> None:
        self.input_sample_rate = int(input_sample_rate)
        self.minimum_speech_ms = int(minimum_speech_ms)
        self.pre_roll_ms = int(pre_roll_ms)
        self._lock = threading.RLock()
        self._noise_floor = 0.006
        self._candidate_ms = 0.0
        self._accepted = False
        self._pre_roll: deque[bytes] = deque()
        self._pre_roll_ms = 0.0
        self._playback_fingerprints: deque[tuple[np.ndarray, float]] = deque(maxlen=24)

    @property
    def accepted(self) -> bool:
        with self._lock:
            return self._accepted

    def start_playback(self) -> None:
        with self._lock:
            self._candidate_ms = 0.0
            self._accepted = False
            self._pre_roll.clear()
            self._pre_roll_ms = 0.0
            self._playback_fingerprints.clear()

    def stop_playback(self) -> None:
        with self._lock:
            self._candidate_ms = 0.0
            self._accepted = False
            self._pre_roll.clear()
            self._pre_roll_ms = 0.0
            self._playback_fingerprints.clear()

    @staticmethod
    def _samples(pcm: bytes) -> np.ndarray:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        return samples / 32768.0

    @staticmethod
    def _fingerprint(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, dict[str, float]]:
        if samples.size < 16:
            return np.zeros(16, dtype=np.float32), {
                "rms": 0.0, "peak": 0.0, "crest": 0.0, "zcr": 0.0,
                "centroid": 0.0, "low_ratio": 1.0, "flatness": 1.0,
            }
        windowed = samples * np.hanning(samples.size)
        spectrum = np.abs(np.fft.rfft(windowed)) + 1e-9
        frequencies = np.fft.rfftfreq(samples.size, 1.0 / sample_rate)
        speech_mask = (frequencies >= 80.0) & (frequencies <= 4000.0)
        speech_spectrum = spectrum[speech_mask]
        speech_frequencies = frequencies[speech_mask]
        total = float(np.sum(speech_spectrum)) + 1e-9
        low = float(np.sum(speech_spectrum[speech_frequencies < 250.0])) / total
        centroid = float(np.sum(speech_spectrum * speech_frequencies) / total)
        flatness = float(
            math.exp(float(np.mean(np.log(speech_spectrum))))
            / (float(np.mean(speech_spectrum)) + 1e-9)
        )
        edges = np.geomspace(80.0, 4000.0, 17)
        bands = np.array([
            float(np.sum(spectrum[(frequencies >= edges[index]) & (frequencies < edges[index + 1])]))
            for index in range(16)
        ], dtype=np.float32)
        norm = float(np.linalg.norm(bands))
        if norm > 0:
            bands /= norm
        rms = float(np.sqrt(np.mean(samples * samples)))
        peak = float(np.max(np.abs(samples)))
        zcr = float(np.mean(np.signbit(samples[1:]) != np.signbit(samples[:-1])))
        return bands, {
            "rms": rms,
            "peak": peak,
            "crest": peak / max(rms, 1e-6),
            "zcr": zcr,
            "centroid": centroid,
            "low_ratio": low,
            "flatness": flatness,
        }

    def observe_playback(self, pcm: bytes, *, sample_rate: int = 24000) -> None:
        samples = self._samples(pcm)
        fingerprint, features = self._fingerprint(samples, sample_rate)
        if features["rms"] <= 0.002:
            return
        with self._lock:
            self._playback_fingerprints.append((fingerprint, features["rms"]))

    def _echo_similarity(self, fingerprint: np.ndarray) -> tuple[float, float]:
        if not self._playback_fingerprints:
            return 0.0, 0.0
        similarities = [float(np.dot(fingerprint, prior)) for prior, _ in self._playback_fingerprints]
        best_index = int(np.argmax(similarities))
        return similarities[best_index], self._playback_fingerprints[best_index][1]

    def _buffer(self, pcm: bytes, frame_ms: float) -> None:
        self._pre_roll.append(bytes(pcm))
        self._pre_roll_ms += frame_ms
        while self._pre_roll and self._pre_roll_ms > self.pre_roll_ms:
            removed = self._pre_roll.popleft()
            self._pre_roll_ms -= len(removed) / 2 / self.input_sample_rate * 1000.0

    def process(self, pcm: bytes, *, playback_active: bool) -> BargeInDecision:
        """Return mic frames only after speech is confirmed during playback."""
        if not pcm:
            return BargeInDecision(noise_floor=self._noise_floor)
        if not playback_active:
            self.stop_playback()
            return BargeInDecision(forward_frames=(bytes(pcm),), noise_floor=self._noise_floor)

        samples = self._samples(pcm)
        fingerprint, features = self._fingerprint(samples, self.input_sample_rate)
        frame_ms = samples.size / self.input_sample_rate * 1000.0
        with self._lock:
            if self._accepted:
                return BargeInDecision(
                    forward_frames=(bytes(pcm),), accepted=True,
                    speech_duration_ms=round(self._candidate_ms),
                    rms=features["rms"], noise_floor=self._noise_floor,
                )

            self._buffer(pcm, frame_ms)
            threshold = max(0.012, self._noise_floor * 3.2)
            echo_similarity, playback_rms = self._echo_similarity(fingerprint)
            echo_like = echo_similarity >= 0.93 and features["rms"] <= max(0.06, playback_rms * 0.55)

            reason = None
            if features["rms"] < threshold:
                self._noise_floor = self._noise_floor * 0.97 + features["rms"] * 0.03
                reason = "below_speech_floor"
            elif features["crest"] > 7.5:
                reason = "transient_noise"
            elif features["low_ratio"] > 0.76 or features["centroid"] < 170.0:
                reason = "low_frequency_noise"
            elif features["flatness"] > 0.72:
                reason = "broadband_noise"
            elif not 0.008 <= features["zcr"] <= 0.38:
                reason = "non_speech_activity"
            elif echo_like:
                reason = "playback_leakage"

            if reason is not None:
                prior_ms = self._candidate_ms
                self._candidate_ms = 0.0
                return BargeInDecision(
                    rejected_reason=reason,
                    speech_duration_ms=round(prior_ms), rms=features["rms"],
                    noise_floor=self._noise_floor, echo_similarity=echo_similarity,
                )

            self._candidate_ms += frame_ms
            if self._candidate_ms < self.minimum_speech_ms:
                return BargeInDecision(
                    candidate=True, speech_duration_ms=round(self._candidate_ms),
                    rms=features["rms"], noise_floor=self._noise_floor,
                    echo_similarity=echo_similarity,
                )

            self._accepted = True
            frames = tuple(self._pre_roll)
            self._pre_roll.clear()
            self._pre_roll_ms = 0.0
            return BargeInDecision(
                forward_frames=frames, accepted=True,
                speech_duration_ms=round(self._candidate_ms), rms=features["rms"],
                noise_floor=self._noise_floor, echo_similarity=echo_similarity,
            )
