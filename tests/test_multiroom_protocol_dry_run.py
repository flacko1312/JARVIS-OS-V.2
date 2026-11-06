import pytest
from core.multiroom_protocol_dry_run import parse_message, SessionTracker

PEERS = frozenset({"windows", "ubuntu"})
BASE = dict(session="s1", sender="windows", target="ubuntu", kind="prepare", sequence=0, delay_ms=20)

def parse(**updates):
    return parse_message({**BASE, **updates}, expected_session="s1", peers=PEERS)

def test_valid():
    assert parse().kind == "prepare"

@pytest.mark.parametrize("change", [
    {"session":"other"}, {"sender":"rogue"}, {"target":"rogue"},
    {"target":"windows"}, {"kind":"execute"}, {"sequence":-1},
    {"sequence":True}, {"delay_ms":-1}, {"delay_ms":2001},
    {"delay_ms":True}, {"sender":""}
])
def test_rejects(change):
    with pytest.raises(ValueError):
        parse(**change)

def test_extra_field_rejected():
    with pytest.raises(ValueError):
        parse_message({**BASE, "command":"play"}, expected_session="s1", peers=PEERS)

def test_missing_field_rejected():
    with pytest.raises(ValueError):
        parse_message({"session":"s1"}, expected_session="s1", peers=PEERS)

def test_replay_and_out_of_order():
    t = SessionTracker()
    assert t.accept(parse(sequence=2))
    assert not t.accept(parse(sequence=2))
    assert not t.accept(parse(sequence=1))
    assert t.accept(parse(sequence=3))

def test_abort_fails_closed():
    t = SessionTracker()
    assert t.accept(parse(kind="abort"))
    assert not t.accept(parse(kind="start", sequence=1))

def test_independent_senders():
    t = SessionTracker()
    assert t.accept(parse())
    assert t.accept(parse(sender="ubuntu", target="windows"))
