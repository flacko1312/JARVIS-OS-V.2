"""Pure multiroom routing planner. No device discovery, audio or network I/O."""
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Route:
    zone: str
    speaker: str


class RouteError(ValueError):
    """Invalid or unavailable routing request."""


def plan_routes(
    requested_zones: Sequence[str],
    zone_speakers: Mapping[str, str],
    available_speakers: Sequence[str],
) -> tuple[Route, ...]:
    """Return a deterministic dry-run plan; never issue playback commands."""
    if isinstance(requested_zones, (str, bytes)) or not requested_zones:
        raise RouteError("at least one zone is required")
    if isinstance(available_speakers, (str, bytes)):
        raise RouteError("available_speakers must be a sequence")
    allowed = set(available_speakers)
    result = []
    seen_zones = set()
    seen_speakers = set()
    for zone in requested_zones:
        if not isinstance(zone, str) or not zone.strip() or zone != zone.strip():
            raise RouteError("invalid zone")
        if zone in seen_zones:
            raise RouteError("duplicate zone")
        seen_zones.add(zone)
        speaker = zone_speakers.get(zone)
        if not isinstance(speaker, str) or not speaker:
            raise RouteError("unknown zone")
        if speaker not in allowed:
            raise RouteError("speaker unavailable")
        if speaker in seen_speakers:
            raise RouteError("one speaker assigned to multiple zones")
        seen_speakers.add(speaker)
        result.append(Route(zone=zone, speaker=speaker))
    return tuple(result)
