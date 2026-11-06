"""Regresiones aisladas: una sesion cancelada no afecta a otra."""
import pytest
from core.multiroom_protocol_dry_run import parse_message, SessionTracker
from core.multiroom_handshake_dry_run import Handshake

PEERS = frozenset({"windows", "ubuntu"})

def msg(session, sender, sequence, kind):
    return parse_message({
        "session": session, "sender": sender,
        "target": "ubuntu" if sender == "windows" else "windows",
        "kind": kind, "sequence": sequence, "delay_ms": 0,
    }, expected_session=session, peers=PEERS)

def test_abort_one_session_does_not_abort_other():
    tracker = SessionTracker()
    assert tracker.accept(msg("a", "windows", 0, "prepare"))
    assert tracker.accept(msg("b", "windows", 0, "prepare"))
    assert tracker.accept(msg("a", "windows", 1, "abort"))
    assert not tracker.accept(msg("a", "ubuntu", 0, "ready"))
    assert tracker.accept(msg("b", "ubuntu", 0, "ready"))

def test_sequence_is_scoped_by_session_and_sender():
    tracker = SessionTracker()
    assert tracker.accept(msg("a", "windows", 2, "prepare"))
    assert tracker.accept(msg("a", "ubuntu", 0, "ready"))
    assert tracker.accept(msg("b", "windows", 0, "prepare"))
    assert not tracker.accept(msg("a", "windows", 2, "start"))
    assert tracker.accept(msg("a", "windows", 3, "start"))

def test_reused_session_id_after_abort_is_rejected():
    tracker = SessionTracker()
    assert tracker.accept(msg("a", "windows", 0, "abort"))
    assert not tracker.accept(msg("a", "windows", 1, "prepare"))

def test_handshake_timeout_is_independent():
    first, second = Handshake(deadline_ms=100, max_retries=0), Handshake(deadline_ms=100, max_retries=0)
    assert first.prepare(0) and second.prepare(80)
    assert first.tick(100) == "aborted"
    assert second.ready(90)
    assert second.start()
    assert first.state == "aborted" and second.state == "started"

@pytest.mark.parametrize("session", ["", "wrong"])
def test_session_mismatch_rejected(session):
    with pytest.raises(ValueError):
        parse_message({
            "session": session, "sender": "windows", "target": "ubuntu",
            "kind": "prepare", "sequence": 0, "delay_ms": 0,
        }, expected_session="correct", peers=PEERS)
