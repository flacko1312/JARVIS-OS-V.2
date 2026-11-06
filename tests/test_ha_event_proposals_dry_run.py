"""B22: contratos puros, sin ejecutar rutinas ni conectar con Home Assistant."""
from core.ha_event_dry_run import EventRule
from core.ha_event_proposals_dry_run import RoutineProposal, propose_routines

RULE = EventRule("binary_sensor.puerta", "off", "on", "avisar_puerta")
def event(before="off", after="on"):
    return {"event_type": "state_changed", "data": {"entity_id": "binary_sensor.puerta", "old_state": {"state": before}, "new_state": {"state": after}}}

def test_proposal_is_data_only():
    assert propose_routines([RULE], event()) == (RoutineProposal("avisar_puerta", "binary_sensor.puerta"),)

def test_no_transition_no_proposal():
    assert propose_routines([RULE], event("on", "off")) == ()

def test_duplicate_routine_not_executed_or_duplicated():
    assert len(propose_routines([RULE, RULE], event())) == 1

def test_multiple_distinct_matching_routines():
    second = EventRule("binary_sensor.puerta", "off", "on", "registrar_puerta")
    assert [x.routine_id for x in propose_routines([RULE, second], event())] == ["avisar_puerta", "registrar_puerta"]

def test_bad_event_fails_closed():
    assert propose_routines([RULE], None) == ()

def test_bad_rule_skipped():
    assert propose_routines([None, RULE], event()) == (RoutineProposal("avisar_puerta", "binary_sensor.puerta"),)
