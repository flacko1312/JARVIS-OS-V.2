from core.ha_event_dry_run import EventRule
from core.ha_event_processor_dry_run import EventProcessor


def _event(event_id="e1", old="off", new="on"):
    return {
        "id": event_id,
        "event_type": "state_changed",
        "data": {
            "entity_id": "binary_sensor.door",
            "old_state": {"state": old},
            "new_state": {"state": new},
        },
    }


def _processor(log=None):
    return EventProcessor(
        [EventRule("binary_sensor.door", "off", "on", "routine.opened")],
        logger=(log.append if log is not None else None),
    )


def test_requires_connection_before_processing():
    result = _processor().process(_event())
    assert result.accepted is False
    assert result.error == "event_stream_disconnected"


def test_accepts_once_and_deduplicates_replay():
    processor = _processor()
    processor.on_connected()
    first = processor.process(_event())
    second = processor.process(_event())
    assert first.accepted and not first.duplicate
    assert [item.routine_id for item in first.proposals] == ["routine.opened"]
    assert second.accepted and second.duplicate and not second.proposals


def test_deterministic_id_deduplicates_events_without_id():
    processor = _processor()
    processor.on_connected()
    event = _event(event_id=None)
    assert processor.process(event).accepted
    assert processor.process(event).duplicate


def test_invalid_event_is_rejected_and_logged():
    log = []
    processor = _processor(log)
    processor.on_connected()
    result = processor.process({"event_type": "call_service"})
    assert result.accepted is False
    assert result.error == "invalid_state_changed_event"
    assert processor.errors == 1
    assert any("rejected" in line for line in log)


def test_disconnect_fails_closed_and_reconnect_is_observable():
    log = []
    processor = _processor(log)
    processor.on_connected()
    processor.on_disconnected("timeout")
    assert processor.process(_event()).accepted is False
    processor.on_connected()
    assert processor.process(_event("e2")).proposals
    assert processor.reconnects == 2
    assert any("disconnected" in line for line in log)
