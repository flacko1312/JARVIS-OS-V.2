import asyncio
import pytest

from core.ha_event_bridge import EventExecutionBlocked, HAEventBridge
from core.ha_event_dry_run import EventRule


class FakeLilith:
    def __init__(self):
        self.calls = []

    async def command_submit(self, **kwargs):
        self.calls.append(kwargs)
        return {"routine": {"id": kwargs["parameters"]["routine_id"]}}


def _event(event_id="evt-1"):
    return {
        "id": event_id,
        "event_type": "state_changed",
        "data": {
            "entity_id": "sensor.motion",
            "old_state": {"state": "off"},
            "new_state": {"state": "on"},
        },
    }


def _bridge(client=None):
    return HAEventBridge(
        (EventRule("sensor.motion", "off", "on", "routine.arrival"),),
        client or FakeLilith(),
    )


def test_inspect_verifies_existing_routine_without_execution():
    client = FakeLilith()
    bridge = _bridge(client)
    bridge.on_connected()
    result, envelopes = asyncio.run(bridge.inspect_event(_event()))
    assert result.accepted and not result.duplicate
    assert envelopes[0].verified is True
    assert envelopes[0].executable is False
    assert client.calls[0]["intent"] == "routines.get"


def test_duplicate_event_does_not_call_lilith_twice():
    client = FakeLilith()
    bridge = _bridge(client)
    bridge.on_connected()
    asyncio.run(bridge.inspect_event(_event()))
    result, envelopes = asyncio.run(bridge.inspect_event(_event()))
    assert result.duplicate is True
    assert envelopes == ()
    assert len(client.calls) == 1


def test_disconnected_event_fails_closed_without_lilith_call():
    client = FakeLilith()
    bridge = _bridge(client)
    result, envelopes = asyncio.run(bridge.inspect_event(_event()))
    assert result.error == "event_stream_disconnected"
    assert envelopes == ()
    assert client.calls == []


def test_execution_requires_explicit_authorization():
    bridge = _bridge()
    bridge.on_connected()
    _, envelopes = asyncio.run(bridge.inspect_event(_event()))
    with pytest.raises(EventExecutionBlocked):
        asyncio.run(bridge.execute(envelopes[0]))


def test_execution_stays_blocked_until_lilith_exposes_contract():
    bridge = _bridge()
    bridge.on_connected()
    _, envelopes = asyncio.run(bridge.inspect_event(_event()))
    with pytest.raises(EventExecutionBlocked, match="contract exposes"):
        asyncio.run(bridge.execute(envelopes[0], authorized=True))
