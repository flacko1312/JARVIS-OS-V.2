"""Hermetic tests: no Home Assistant connection and no routine execution."""
from core.ha_event_dry_run import EventRule, evaluate_event


RULE = EventRule("binary_sensor.puerta", "off", "on", "avisar_puerta")


def event(before="off", after="on", entity="binary_sensor.puerta"):
    return {"event_type": "state_changed", "data": {
        "entity_id": entity, "old_state": {"state": before}, "new_state": {"state": after}}}


def test_exact_transition_returns_identifier_only():
    assert evaluate_event(RULE, event()) == "avisar_puerta"


def test_other_entity_is_ignored():
    assert evaluate_event(RULE, event(entity="binary_sensor.otra")) is None


def test_wrong_transition_is_ignored():
    assert evaluate_event(RULE, event("on", "off")) is None


def test_unavailable_state_is_ignored():
    assert evaluate_event(RULE, event("unavailable", "on")) is None


def test_malformed_event_fails_closed():
    assert evaluate_event(RULE, {"event_type": "state_changed", "data": []}) is None


def test_non_sensor_rule_is_rejected():
    assert evaluate_event(EventRule("light.salon", "off", "on", "x"), event(entity="light.salon")) is None


def test_unrelated_event_is_ignored():
    e = event()
    e["event_type"] = "call_service"
    assert evaluate_event(RULE, e) is None
