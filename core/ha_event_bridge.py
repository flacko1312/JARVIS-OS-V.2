"""Puente seguro JARVIS -> LILITH para propuestas derivadas de eventos HA.

Este módulo no se suscribe a Home Assistant ni ejecuta rutinas. Su función es
la parte que sí puede cerrar JARVIS sin cambiar LILITH: validar un evento,
consultar que la rutina propuesta existe en LILITH y devolver un sobre listo
para una futura entrega autorizada. ``execute=False`` es obligatorio por
defecto y cualquier intento de saltárselo falla cerrado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.ha_event_dry_run import EventRule
from core.ha_event_processor_dry_run import EventProcessor, ProcessResult


class EventExecutionBlocked(PermissionError):
    """Raised when a caller attempts to execute without an external approval."""


@dataclass(frozen=True)
class RoutineEnvelope:
    routine_id: str
    request_id: str
    idempotency_key: str
    verified: bool
    executable: bool = False


class HAEventBridge:
    """Read-only event bridge with LILITH routine verification."""

    def __init__(self, rules: tuple[EventRule, ...], lilith_client: Any, *, logger=None) -> None:
        self._processor = EventProcessor(rules, logger=logger)
        self._client = lilith_client

    def on_connected(self) -> None:
        self._processor.on_connected()

    def on_disconnected(self, reason: str) -> None:
        self._processor.on_disconnected(reason)

    async def inspect_event(self, event: Mapping[str, object]) -> tuple[ProcessResult, tuple[RoutineEnvelope, ...]]:
        """Process one event and read-verify each proposed LILITH routine."""
        result = self._processor.process(event)
        if not result.accepted or result.duplicate:
            return result, ()
        envelopes: list[RoutineEnvelope] = []
        for proposal in result.proposals:
            request_id = f"jarvis:ha-event:{proposal.routine_id}"
            response = await self._client.command_submit(
                intent="routines.get",
                parameters={"routine_id": proposal.routine_id},
                request_id=request_id,
                idempotency_key=request_id,
            )
            verified = bool(response.get("routine") or response.get("id") or response.get("data"))
            envelopes.append(RoutineEnvelope(
                routine_id=proposal.routine_id,
                request_id=request_id,
                idempotency_key=request_id,
                verified=verified,
            ))
        return result, tuple(envelopes)

    async def execute(self, envelope: RoutineEnvelope, *, authorized: bool = False) -> None:
        """Never execute from the event bridge without an explicit outer gate."""
        if not authorized or not envelope.verified:
            raise EventExecutionBlocked("event routine execution requires explicit authorization")
        raise EventExecutionBlocked(
            "LILITH integration contract exposes routine verification, not event execution"
        )
