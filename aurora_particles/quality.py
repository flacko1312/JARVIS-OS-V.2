from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityPreset:
    name: str
    particle_count: int
    frame_ms: int
    point_size: float
    turbulence: float


class QualityManager:
    PRESETS = {
        # The Windows compositor quantizes 33/50 ms timers to lower-than-target
        # swap rates on the audited RX 5500 XT. 16 ms keeps medium/high vsynced;
        # low remains deliberately reduced for power-constrained systems.
        "low": QualityPreset("low", 4_000, 33, 2.0, 0.55),
        "medium": QualityPreset("medium", 10_000, 16, 2.2, 0.80),
        "high": QualityPreset("high", 20_000, 16, 2.4, 1.00),
    }

    def __init__(self, initial: str = "medium") -> None:
        self._name = self.normalize(initial)

    @classmethod
    def normalize(cls, value: str) -> str:
        value = str(value or "medium").lower()
        return value if value in cls.PRESETS else "medium"

    @property
    def current(self) -> QualityPreset:
        return self.PRESETS[self._name]

    def set(self, value: str) -> QualityPreset:
        self._name = self.normalize(value)
        return self.current
