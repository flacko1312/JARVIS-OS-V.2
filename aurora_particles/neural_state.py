"""Inertial visual-state blending for the single AURORA neural entity."""
from __future__ import annotations

from collections import deque

import numpy as np


MODES = ("standby", "listening", "processing", "speaking")
MODE_INDEX = {name: index for index, name in enumerate(MODES)}


class NeuralStateController:
    def __init__(self, initial: str = "standby") -> None:
        self.current = initial if initial in MODE_INDEX else "standby"
        self.target = self.current
        self.weights = np.zeros(4, dtype=np.float32)
        self.weights[MODE_INDEX[self.current]] = 1.0
        self._start = self.weights.copy()
        self.progress = 1.0
        self.duration = .8
        self.hold_remaining = 0.0
        self._queue: deque[str] = deque()

    @property
    def stable(self) -> bool:
        return self.progress >= 1.0 and self.hold_remaining <= 0.0

    def request(self, mode: str) -> bool:
        mode = mode if mode in MODE_INDEX else "standby"
        if not self.stable:
            pending = self._queue[-1] if self._queue else self.target
            if pending == mode:
                return False
            if len(self._queue) >= 4:
                if len(self._queue) > 1 and self._queue[-2] == mode:
                    self._queue.pop()
                self._queue[-1] = mode
            else:
                self._queue.append(mode)
            return False
        if mode == self.current:
            return False
        self._begin(mode)
        return True

    def _begin(self, mode: str) -> None:
        durations = {
            ("standby", "listening"): .65,
            ("listening", "processing"): .72,
            ("processing", "speaking"): .90,
            ("speaking", "standby"): 1.05,
        }
        self.target = mode
        self.duration = durations.get((self.current, mode), .82)
        self.progress = 0.0
        self._start = self.weights.copy()

    def update(self, dt: float) -> str | None:
        dt = max(0.0, float(dt))
        if self.progress < 1.0:
            self.progress = min(1.0, self.progress + dt / max(.05, self.duration))
            t = self.progress
            eased = t * t * (3.0 - 2.0 * t)
            destination = np.zeros(4, dtype=np.float32)
            destination[MODE_INDEX[self.target]] = 1.0
            self.weights[:] = self._start * (1.0 - eased) + destination * eased
            if self.progress >= 1.0:
                self.current = self.target
                self.hold_remaining = .42 if self.current == "processing" and self._queue else 0.0
                return self.current
            return None
        if self.hold_remaining > 0.0:
            self.hold_remaining = max(0.0, self.hold_remaining - dt)
            return None
        if self._queue:
            self._begin(self._queue.popleft())
        return None
