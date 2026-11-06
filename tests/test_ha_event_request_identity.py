"""B22: separate sensor events must not share a LILITH idempotency key."""
import asyncio

from core.ha_event_bridge import HAEventBridge
from core.ha_event_dry_run import EventRule


class ReadOnlyClient:
    def __init__(self):
        self.calls = []

    async def command_submit(self, **kwargs):
        self.calls.append(kwargs)
        return {"routine": {"id": kwargs["parameters"]["routine_id"]}}


def event(event_id):
    return {"id": event_id, "event_type": "state_changed", "data": {
        "entity_id": "sensor.motion", "old_state": {"state": "off"},
        "new_state": {"state": "on"}}}


def test_distinct_events_have_distinct_request_ids():
    client = ReadOnlyClient()
    bridge = HAEventBridge((EventRule("sensor.motion", "off", "on", "routine.arrival"),), client)
    bridge.on_connected()
    first = asyncio.run(bridge.inspect_event(event("event-1")))[1][0]
    second = asyncio.run(bridge.inspect_event(event("event-2")))[1][0]
    assert first.request_id != second.request_id
    assert first.idempotency_key == first.request_id
    assert second.idempotency_key == second.request_id
    assert all(call["intent"] == "routines.get" for call in client.calls)


def test_same_event_replayed_is_deduplicated():
    client = ReadOnlyClient()
    bridge = HAEventBridge((EventRule("sensor.motion", "off", "on", "routine.arrival"),), client)
    bridge.on_connected()
    asyncio.run(bridge.inspect_event(event("event-1")))
    result, envelopes = asyncio.run(bridge.inspect_event(event("event-1")))
    assert result.duplicate and envelopes == ()
    assert len(client.calls) == 1
