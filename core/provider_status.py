"""Provider/connectivity status snapshots without automatic side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable

from core.local_ai import LocalAIState, OllamaTextProvider


class Availability(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    TEMPORARY_FAILURE = "temporary_failure"
    AUTH_FAILURE = "auth_failure"
    NOT_CONFIGURED = "not_configured"
    MODEL_MISSING = "model_missing"


@dataclass(frozen=True)
class ProviderSnapshot:
    internet: Availability = Availability.UNKNOWN
    gemini: Availability = Availability.UNKNOWN
    ollama: Availability = Availability.UNKNOWN
    lilith: Availability = Availability.UNKNOWN
    offline_capabilities: tuple[str, ...] = ()
    details: dict[str, str] = field(default_factory=dict)


Probe = Callable[[], Awaitable[Availability]]


class ProviderStatusRegistry:
    """Keeps the latest explicit provider probe result and transition history."""

    def __init__(
        self,
        ollama: OllamaTextProvider,
        *,
        internet_probe: Probe,
        gemini_probe: Probe,
        lilith_probe: Probe,
    ):
        self._ollama = ollama
        self._internet_probe = internet_probe
        self._gemini_probe = gemini_probe
        self._lilith_probe = lilith_probe
        self.snapshot = ProviderSnapshot()
        self.transitions: list[tuple[str, str, str]] = []

    async def refresh(self) -> ProviderSnapshot:
        internet = await self._internet_probe()
        gemini = await self._gemini_probe()
        lilith = await self._lilith_probe()
        local = await self._ollama.status()
        ollama = {
            LocalAIState.ONLINE: Availability.AVAILABLE,
            LocalAIState.MODEL_MISSING: Availability.MODEL_MISSING,
            LocalAIState.DISABLED: Availability.NOT_CONFIGURED,
            LocalAIState.OFFLINE: Availability.UNAVAILABLE,
            LocalAIState.ERROR: Availability.TEMPORARY_FAILURE,
        }[local.state]
        new = ProviderSnapshot(
            internet=internet,
            gemini=gemini,
            ollama=ollama,
            lilith=lilith,
            offline_capabilities=("local_text",) if ollama == Availability.AVAILABLE else (),
            details={"ollama": local.message},
        )
        for name in ("internet", "gemini", "ollama", "lilith"):
            old_value = getattr(self.snapshot, name).value
            new_value = getattr(new, name).value
            if old_value != new_value:
                self.transitions.append((name, old_value, new_value))
        self.snapshot = new
        return new
