"""Voice and connection stability monitoring for JARVIS Headless.

Tracks reconnection events, audio health metrics, latency,
and provides data for the health endpoint and soak analysis.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.voice_stability")

_MAX_EVENTS = 500
_MAX_LATENCY_SAMPLES = 200


@dataclass
class ReconnectEvent:
    timestamp: float
    attempt: int
    delay: float
    success: bool
    reason: str = ""
    duration_ms: float = 0.0


@dataclass
class AudioMetrics:
    """Per-session audio health metrics."""
    frames_sent: int = 0
    frames_dropped: int = 0
    barge_in_attempts: int = 0
    barge_in_accepted: int = 0
    barge_in_rejected: int = 0
    avg_rms: float = 0.0
    noise_floor: float = 0.0
    last_activity: float = 0.0


class VoiceStabilityMonitor:
    """Collects voice and connection stability metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reconnect_events: deque[ReconnectEvent] = deque(maxlen=_MAX_EVENTS)
        self._latency_samples: deque[float] = deque(maxlen=_MAX_LATENCY_SAMPLES)
        self._session_start: float = 0.0
        self._total_reconnects: int = 0
        self._successful_reconnects: int = 0
        self._failed_reconnects: int = 0
        self._last_disconnect: float = 0.0
        self._audio = AudioMetrics()
        self._longest_session_s: float = 0.0
        self._current_session_start: float = 0.0

    def start(self) -> None:
        """Mark the start of monitoring."""
        self._session_start = time.time()
        self._current_session_start = time.time()

    def record_reconnect(self, attempt: int, delay: float, success: bool,
                          reason: str = "", duration_ms: float = 0.0) -> None:
        """Record a reconnection event."""
        event = ReconnectEvent(
            timestamp=time.time(),
            attempt=attempt,
            delay=delay,
            success=success,
            reason=reason,
            duration_ms=duration_ms,
        )
        with self._lock:
            self._reconnect_events.append(event)
            self._total_reconnects += 1
            if success:
                self._successful_reconnects += 1
                # Track longest continuous session
                now = time.time()
                session_len = now - self._current_session_start
                if session_len > self._longest_session_s:
                    self._longest_session_s = session_len
                self._current_session_start = now
            else:
                self._failed_reconnects += 1
            self._last_disconnect = time.time()

    def record_latency(self, latency_ms: float) -> None:
        """Record a response latency sample."""
        with self._lock:
            self._latency_samples.append(latency_ms)

    def record_audio_frame(self, *, dropped: bool = False) -> None:
        """Record an audio frame event."""
        with self._lock:
            if dropped:
                self._audio.frames_dropped += 1
            else:
                self._audio.frames_sent += 1
            self._audio.last_activity = time.time()

    def record_barge_in(self, accepted: bool) -> None:
        """Record a barge-in attempt."""
        with self._lock:
            self._audio.barge_in_attempts += 1
            if accepted:
                self._audio.barge_in_accepted += 1
            else:
                self._audio.barge_in_rejected += 1

    def update_noise_floor(self, rms: float, noise_floor: float) -> None:
        """Update audio level metrics."""
        with self._lock:
            self._audio.avg_rms = rms
            self._audio.noise_floor = noise_floor

    def get_metrics(self) -> dict[str, Any]:
        """Get current stability metrics snapshot."""
        with self._lock:
            now = time.time()
            uptime = now - self._session_start if self._session_start else 0
            current_session = now - self._current_session_start if self._current_session_start else 0

            # Latency stats
            latencies = list(self._latency_samples)
            if latencies:
                avg_lat = sum(latencies) / len(latencies)
                p50 = sorted(latencies)[len(latencies) // 2]
                p95 = sorted(latencies)[int(len(latencies) * 0.95)]
                max_lat = max(latencies)
            else:
                avg_lat = p50 = p95 = max_lat = 0.0

            # Recent reconnect rate (last hour)
            one_hour_ago = now - 3600
            recent = sum(1 for e in self._reconnect_events if e.timestamp > one_hour_ago)

            return {
                "uptime_s": round(uptime, 1),
                "current_session_s": round(current_session, 1),
                "longest_session_s": round(max(self._longest_session_s, current_session), 1),
                "reconnects": {
                    "total": self._total_reconnects,
                    "successful": self._successful_reconnects,
                    "failed": self._failed_reconnects,
                    "last_hour": recent,
                    "last_disconnect": self._last_disconnect if self._last_disconnect else None,
                },
                "latency_ms": {
                    "avg": round(avg_lat, 1),
                    "p50": round(p50, 1),
                    "p95": round(p95, 1),
                    "max": round(max_lat, 1),
                    "samples": len(latencies),
                },
                "audio": {
                    "frames_sent": self._audio.frames_sent,
                    "frames_dropped": self._audio.frames_dropped,
                    "drop_rate": (
                        round(self._audio.frames_dropped / max(1, self._audio.frames_sent + self._audio.frames_dropped) * 100, 2)
                    ),
                    "barge_in_attempts": self._audio.barge_in_attempts,
                    "barge_in_accepted": self._audio.barge_in_accepted,
                    "barge_in_rejected": self._audio.barge_in_rejected,
                    "rms": round(self._audio.avg_rms, 4),
                    "noise_floor": round(self._audio.noise_floor, 4),
                    "last_activity": self._audio.last_activity,
                },
            }

    def get_reconnect_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent reconnect events."""
        with self._lock:
            events = list(self._reconnect_events)[-limit:]
        return [
            {
                "timestamp": e.timestamp,
                "attempt": e.attempt,
                "delay": e.delay,
                "success": e.success,
                "reason": e.reason,
                "duration_ms": e.duration_ms,
            }
            for e in events
        ]

    def is_healthy(self) -> bool:
        """Quick health assessment."""
        with self._lock:
            now = time.time()
            # Unhealthy if >3 reconnects in the last 10 minutes
            ten_min_ago = now - 600
            recent = sum(1 for e in self._reconnect_events if e.timestamp > ten_min_ago)
            if recent > 3:
                return False
            # Unhealthy if >10% audio frame drop rate (over substantial samples)
            total_frames = self._audio.frames_sent + self._audio.frames_dropped
            if total_frames > 100:
                drop_rate = self._audio.frames_dropped / total_frames
                if drop_rate > 0.10:
                    return False
            return True


# Singleton instance
_monitor: VoiceStabilityMonitor | None = None


def get_monitor() -> VoiceStabilityMonitor:
    """Get or create the singleton monitor."""
    global _monitor
    if _monitor is None:
        _monitor = VoiceStabilityMonitor()
    return _monitor
