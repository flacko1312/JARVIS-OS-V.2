from __future__ import annotations

import math
import numpy as np


def pcm16_features(pcm, sample_rate: int = 16_000) -> tuple[float, tuple[float, float, float]]:
    """Return display RMS and normalized bass/mid/treble energy without retaining PCM."""
    try:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if samples.size < 8:
            return 0.0, (0.0, 0.0, 0.0)
        samples /= 32768.0
        rms = min(1.0, math.sqrt(float(np.mean(samples * samples))) ** .5 * 2.0)
        n = min(samples.size, 2048)
        windowed = samples[-n:] * np.hanning(n)
        power = np.abs(np.fft.rfft(windowed)) / max(1.0, float(np.sum(np.hanning(n))) * .5)
        freq = np.fft.rfftfreq(n, 1.0 / max(1, sample_rate))
        def band(lo: float, hi: float) -> float:
            selected = power[(freq >= lo) & (freq < hi)]
            if selected.size == 0:
                return 0.0
            # Voice energy is normally concentrated in a few bins. A high
            # percentile followed by a square-root compressor remains useful
            # for speech without forcing quiet syllables back to zero.
            energy = float(np.max(selected))
            return min(1.0, math.sqrt(max(0.0, energy)) * 2.2)
        return rms, (band(30, 250), band(250, 2_000), band(2_000, 7_500))
    except Exception:
        return 0.0, (0.0, 0.0, 0.0)


class AudioAnalyzer:
    def __init__(self) -> None:
        self.input = np.zeros(3, dtype=np.float32)
        self.output = np.zeros(3, dtype=np.float32)

    def set_bands(self, kind: str, bands) -> None:
        target = np.clip(np.asarray(tuple(bands), dtype=np.float32), 0.0, 1.0)
        if target.shape != (3,):
            return
        current = self.output if kind == "output" else self.input
        attack = target > current
        factor = np.where(attack, .62, .14).astype(np.float32)
        current[:] += (target - current) * factor

    def decay(self, amount: float = .985) -> None:
        self.input *= amount
        self.output *= amount
