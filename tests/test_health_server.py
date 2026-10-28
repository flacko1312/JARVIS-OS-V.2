from types import SimpleNamespace

import health_server


def test_functional_state_requires_listening():
    for state, expected in (("LISTENING", True), ("CONNECTING", False), ("RECONNECTING", False), ("STOPPING", False)):
        jarvis = SimpleNamespace(_conversation_state=SimpleNamespace(value=state))
        assert (health_server._state_name(jarvis) in health_server._FUNCTIONAL_STATES) is expected


def test_lilith_availability_is_truthful_and_unknown_when_absent():
    assert health_server._lilith_available(SimpleNamespace()) is None
    online = SimpleNamespace(_lilith=SimpleNamespace(_runtime=SimpleNamespace(lilith_available=True)))
    offline = SimpleNamespace(_lilith=SimpleNamespace(_runtime=SimpleNamespace(lilith_available=False)))
    assert health_server._lilith_available(online) is True
    assert health_server._lilith_available(offline) is False
