"""Loop Guards — deterministic loop/stagnation protection for agent execution.

Detects repeated operations, identical errors, and lack of progress.
Returns structured LOOP_DETECTED information — it does NOT autonomously
choose alternative actions. The caller decides what happens next.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from core.green.execution_trace import redact_secrets

logger = logging.getLogger("jarvis.green.loop_guard")


@dataclass
class LoopDetection:
    """Structured result from loop detection."""

    detected: bool
    reason: str = ""
    fingerprint: str = ""
    repeat_count: int = 0
    recommendation: str = "stop"


def _fingerprint(action: str, tool: str, arguments: dict[str, Any], result_category: str) -> str:
    """Produce a deterministic fingerprint for an operation."""
    sanitized = redact_secrets(arguments) if arguments else {}
    key = f"{action}|{tool}|{_stable_repr(sanitized)}|{result_category}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _stable_repr(obj: Any) -> str:
    """Produce a stable string representation for fingerprinting."""
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda x: str(x[0]))
        return "{" + ",".join(f"{k!r}:{_stable_repr(v)}" for k, v in items) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_stable_repr(x) for x in obj) + "]"
    return repr(obj)


class LoopGuard:
    """Tracks operation fingerprints and detects repetition loops.

    Thresholds are configurable. When a loop is detected, the guard
    returns structured information but takes no autonomous action.
    """

    def __init__(
        self,
        max_same_operation: int = 3,
        max_same_error: int = 3,
        max_no_progress: int = 5,
    ) -> None:
        self._max_same_op = max_same_operation
        self._max_same_error = max_same_error
        self._max_no_progress = max_no_progress

        self._fingerprints: list[str] = []
        self._error_fingerprints: list[str] = []
        self._progress_markers: list[str] = []
        self._no_progress_count = 0

    def check_operation(
        self,
        action: str = "",
        tool: str = "",
        arguments: dict[str, Any] | None = None,
        result_category: str = "",
        error_category: str = "",
        progress_marker: str = "",
    ) -> LoopDetection:
        """Record an operation and check for loops."""
        fp = _fingerprint(action, tool, arguments or {}, result_category)
        self._fingerprints.append(fp)

        # Check same-operation loop
        recent = self._fingerprints[-self._max_same_op:]
        if len(recent) == self._max_same_op and len(set(recent)) == 1:
            return LoopDetection(
                detected=True,
                reason=f"same operation repeated {self._max_same_op} times",
                fingerprint=fp,
                repeat_count=self._max_same_op,
            )

        # Check same-error loop
        if error_category:
            self._error_fingerprints.append(error_category)
            recent_errors = self._error_fingerprints[-self._max_same_error:]
            if len(recent_errors) == self._max_same_error and len(set(recent_errors)) == 1:
                return LoopDetection(
                    detected=True,
                    reason=f"same error repeated {self._max_same_error} times: {error_category}",
                    fingerprint=fp,
                    repeat_count=self._max_same_error,
                )

        # Check no-progress stagnation
        if progress_marker:
            if self._progress_markers and self._progress_markers[-1] == progress_marker:
                self._no_progress_count += 1
            else:
                self._no_progress_count = 0
            self._progress_markers.append(progress_marker)

            if self._no_progress_count >= self._max_no_progress:
                return LoopDetection(
                    detected=True,
                    reason=f"no progress for {self._no_progress_count} operations",
                    fingerprint=fp,
                    repeat_count=self._no_progress_count,
                )

        return LoopDetection(detected=False, fingerprint=fp)

    def reset(self) -> None:
        """Clear all tracking state."""
        self._fingerprints.clear()
        self._error_fingerprints.clear()
        self._progress_markers.clear()
        self._no_progress_count = 0

    @property
    def operation_count(self) -> int:
        return len(self._fingerprints)
