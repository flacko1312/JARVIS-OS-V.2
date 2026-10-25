from __future__ import annotations

from collections import deque
from enum import Enum


class MorphState(str, Enum):
    STABLE = "STABLE"
    DISSOLVING = "DISSOLVING"
    DISPERSED = "DISPERSED"
    REASSEMBLING = "REASSEMBLING"
    STABILIZING = "STABILIZING"


class MorphController:
    """Deterministic transition state machine; requests made mid-morph are queued."""

    def __init__(self, initial: str = "core", duration: float = 1.05) -> None:
        self.current_shape = initial
        self.target_shape = initial
        self.state = MorphState.STABLE
        self.progress = 1.0
        self.duration = max(0.2, float(duration))
        self._elapsed = 0.0
        self._queue: deque[str] = deque()

    def request(self, shape: str) -> bool:
        if shape == self.target_shape and self.state is not MorphState.STABLE:
            return False
        if self.state is MorphState.STABLE:
            if shape == self.current_shape:
                return False
            self.target_shape = shape
            self.progress = 0.0
            self._elapsed = 0.0
            self.state = MorphState.DISSOLVING
            return True
        if not self._queue or self._queue[-1] != shape:
            self._queue.append(shape)
        return False

    def update(self, dt: float) -> bool:
        if self.state is MorphState.STABLE:
            return False
        self._elapsed += max(0.0, float(dt))
        self.progress = min(1.0, self._elapsed / self.duration)
        p = self.progress
        self.state = (MorphState.DISSOLVING if p < .24 else
                      MorphState.DISPERSED if p < .48 else
                      MorphState.REASSEMBLING if p < .88 else
                      MorphState.STABILIZING if p < 1.0 else MorphState.STABLE)
        if p >= 1.0:
            self.current_shape = self.target_shape
            if self._queue:
                self.request(self._queue.popleft())
            return True
        return False

    @property
    def dissolve(self) -> float:
        return max(0.0, 1.0 - abs(self.progress * 2.0 - 1.0))
