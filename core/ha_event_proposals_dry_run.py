"""Planificador aislado B22: traduce eventos HA a propuestas, nunca ejecuta rutinas."""
from dataclasses import dataclass
from typing import Iterable, Mapping
from core.ha_event_dry_run import EventRule, evaluate_event

@dataclass(frozen=True)
class RoutineProposal:
    routine_id: str
    entity_id: str
    reason: str = "sensor_state_transition"

def propose_routines(rules: Iterable[EventRule], event: Mapping[str, object]) -> tuple[RoutineProposal, ...]:
    """Solo propone identificadores; no red, HA, LILITH ni acciones."""
    if not isinstance(event, dict):
        return ()
    proposals = []
    seen = set()
    for rule in rules:
        if not isinstance(rule, EventRule):
            continue
        routine_id = evaluate_event(rule, event)
        if routine_id is not None and routine_id not in seen:
            seen.add(routine_id)
            proposals.append(RoutineProposal(routine_id, rule.entity_id))
    return tuple(proposals)
