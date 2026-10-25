from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityPreset:
    name: str
    particle_count: int
    edge_count: int
    frame_ms: int
    point_size: float
    turbulence: float


class QualityManager:
    PRESETS = {
        # The Windows compositor quantizes 33/50 ms timers to lower-than-target
        # swap rates on the audited RX 5500 XT. 16 ms keeps medium/high vsynced;
        # low remains deliberately reduced for power-constrained systems.
        "low": QualityPreset("low", 450, 2_000, 33, 2.45, 0.55),
        "medium": QualityPreset("medium", 800, 3_200, 16, 2.70, 0.80),
        "high": QualityPreset("high", 1_200, 5_500, 16, 2.90, 1.00),
    }

    def __init__(self, initial: str = "medium") -> None:
        self._name = self.normalize(initial)
        self._slow_seconds = 0.0
        self._cooldown_seconds = 0.0

    @classmethod
    def normalize(cls, value: str) -> str:
        value = str(value or "medium").lower()
        return value if value in cls.PRESETS else "medium"

    @property
    def current(self) -> QualityPreset:
        return self.PRESETS[self._name]

    def set(self, value: str) -> QualityPreset:
        self._name = self.normalize(value)
        self._slow_seconds = 0.0
        self._cooldown_seconds = 4.0
        return self.current

    def observe_frame(self, dt: float) -> str | None:
        """Return a lower runtime preset after sustained sub-24 FPS rendering."""
        dt = max(0.0, min(.25, float(dt)))
        if self._cooldown_seconds > 0.0:
            self._cooldown_seconds = max(0.0, self._cooldown_seconds - dt)
            return None
        if self._name == "low":
            return None
        if dt > (1.0 / 24.0):
            self._slow_seconds += dt
        else:
            self._slow_seconds = max(0.0, self._slow_seconds - dt * 1.8)
        if self._slow_seconds < 3.0:
            return None
        return "medium" if self._name == "high" else "low"
