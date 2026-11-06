"""Pure, read-only HA event rule evaluation; no device actions or network."""
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class EventRule:
    entity_id: str
    from_state: str
    to_state: str
    routine_id: str


def evaluate_event(rule: EventRule, event: Mapping[str, object]) -> Optional[str]:
    """Return a routine identifier for an exact state transition, never execute it."""
    if not rule.entity_id.startswith(("binary_sensor.", "sensor.")):
        return None
    if not rule.routine_id or not rule.from_state or not rule.to_state:
        return None
    if event.get("event_type") != "state_changed":
        return None
    data = event.get("data")
    if not isinstance(data, dict) or data.get("entity_id") != rule.entity_id:
        return None
    old, new = data.get("old_state"), data.get("new_state")
    if not isinstance(old, dict) or not isinstance(new, dict):
        return None
    if old.get("state") in ("unknown", "unavailable", None):
        return None
    if new.get("state") in ("unknown", "unavailable", None):
        return None
    if old.get("state") == rule.from_state and new.get("state") == rule.to_state:
        return rule.routine_id
    return None
