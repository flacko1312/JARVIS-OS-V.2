"""Pure multiroom readiness simulator. No audio, network or device operations."""
from dataclasses import dataclass
from typing import Mapping, Sequence

from core.multiroom_dry_run import Route, RouteError


@dataclass(frozen=True)
class SpeakerProbe:
    """Synthetic probe data; all timestamps and delays are supplied by tests."""
    ready: bool
    latency_ms: int


@dataclass(frozen=True)
class Coordination:
    """Simulated playback start offset per zone, relative to a common clock."""
    zone: str
    speaker: str
    offset_ms: int


def simulate_sync(
    routes: Sequence[Route],
    probes: Mapping[str, SpeakerProbe],
    *,
    max_latency_ms: int = 500,
    max_skew_ms: int = 80,
) -> tuple[Coordination, ...]:
    """Fail closed if a speaker is absent, delayed, disconnected or out of sync.

    No command is sent to any device. Offsets model compensating for latency.
    """
    if not routes or isinstance(routes, (str, bytes)):
        raise RouteError("routes required")
    if max_latency_ms < 0 or max_skew_ms < 0:
        raise RouteError("invalid limits")
    seen = set()
    latencies = []
    for route in routes:
        if not isinstance(route, Route) or route.speaker in seen:
            raise RouteError("invalid or duplicate speaker")
        seen.add(route.speaker)
        probe = probes.get(route.speaker)
        if not isinstance(probe, SpeakerProbe) or not probe.ready:
            raise RouteError("speaker disconnected or not ready")
        if isinstance(probe.latency_ms, bool) or not isinstance(probe.latency_ms, int):
            raise RouteError("invalid latency")
        if not 0 <= probe.latency_ms <= max_latency_ms:
            raise RouteError("speaker latency exceeded")
        latencies.append(probe.latency_ms)
    if max(latencies) - min(latencies) > max_skew_ms:
        raise RouteError("sync skew exceeded")
    slowest = max(latencies)
    return tuple(
        Coordination(route.zone, route.speaker, slowest - latency)
        for route, latency in zip(routes, latencies)
    )
