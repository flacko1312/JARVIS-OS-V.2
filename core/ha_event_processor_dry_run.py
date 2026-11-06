"""Procesador hermetico de eventos HA para B22.

No abre conexiones, no ejecuta rutinas y no modifica dispositivos. Convierte
eventos state_changed en propuestas deduplicadas y modela el ciclo de vida de
un consumidor para que la futura integracion pueda fallar de forma segura.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Iterable, Mapping

from core.ha_event_dry_run import EventRule
from core.ha_event_proposals_dry_run import RoutineProposal, propose_routines


@dataclass(frozen=True)
class ProcessResult:
    accepted: bool
    duplicate: bool
    proposals: tuple[RoutineProposal, ...] = ()
    error: str | None = None


class EventProcessor:
    """Deduplica eventos y devuelve propuestas, nunca efectos domésticos."""

    def __init__(
        self,
        rules: Iterable[EventRule],
        *,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self._rules = tuple(rules)
        self._seen: set[str] = set()
        self.connected = False
        self.reconnects = 0
        self.errors = 0
        self._logger = logger or (lambda _message: None)

    def on_connected(self) -> None:
        if self.connected:
            return
        self.connected = True
        self.reconnects += 1
        self._logger("ha_event_stream connected")

    def on_disconnected(self, reason: str) -> None:
        self.connected = False
        self._logger(f"ha_event_stream disconnected: {reason}")

    def process(self, event: Mapping[str, object]) -> ProcessResult:
        if not self.connected:
            return ProcessResult(False, False, error="event_stream_disconnected")
        if not isinstance(event, dict) or event.get("event_type") != "state_changed":
            return self._reject("invalid_state_changed_event")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            try:
                event_id = hashlib.sha256(
                    json.dumps(event, sort_keys=True, separators=(",", ":"), default=str).encode()
                ).hexdigest()
            except (TypeError, ValueError):
                return self._reject("event_not_serializable")
        if event_id in self._seen:
            self._logger(f"ha_event duplicate ignored: {event_id}")
            return ProcessResult(True, True)
        self._seen.add(event_id)
        proposals = propose_routines(self._rules, event)
        self._logger(f"ha_event accepted: {event_id} proposals={len(proposals)}")
        return ProcessResult(True, False, proposals)

    def _reject(self, reason: str) -> ProcessResult:
        self.errors += 1
        self._logger(f"ha_event rejected: {reason}")
        return ProcessResult(False, False, error=reason)
