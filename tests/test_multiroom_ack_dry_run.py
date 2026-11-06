"""ACK correlacionado, replays y aislamiento de sesiones (solo mocks)."""
import pytest
from core.multiroom_protocol_dry_run import parse_message
from core.multiroom_ack_dry_run import AckLedger

PEERS = frozenset({"windows", "ubuntu"})

def message(session="s1", sender="windows", kind="prepare", sequence=0):
    return parse_message(dict(session=session, sender=sender,
        target="ubuntu" if sender == "windows" else "windows",
        kind=kind, sequence=sequence, delay_ms=0),
        expected_session=session, peers=PEERS)

def test_ack_valid_and_replay_rejected():
    ledger = AckLedger()
    assert ledger.register(message())
    ack = message(sender="ubuntu", kind="ack")
    assert ledger.acknowledge(ack, original_sequence=0)
    assert not ledger.acknowledge(ack, original_sequence=0)

@pytest.mark.parametrize("original_sequence", [1, -1, True])
def test_wrong_original_sequence_rejected(original_sequence):
    ledger = AckLedger()
    assert ledger.register(message())
    assert not ledger.acknowledge(message(sender="ubuntu", kind="ack"), original_sequence=original_sequence)

def test_wrong_sender_rejected():
    ledger = AckLedger()
    assert ledger.register(message())
    assert not ledger.acknowledge(message(kind="ack"), original_sequence=0)

def test_cross_session_replay_rejected():
    ledger = AckLedger()
    assert ledger.register(message("s1"))
    assert not ledger.acknowledge(message("s2", sender="ubuntu", kind="ack"), original_sequence=0)

def test_close_invalidates_pending_and_future_reuse():
    ledger = AckLedger()
    assert ledger.register(message())
    ledger.close("s1")
    assert not ledger.acknowledge(message(sender="ubuntu", kind="ack"), original_sequence=0)
    assert not ledger.register(message(sequence=1))

def test_sessions_remain_independent():
    ledger = AckLedger()
    assert ledger.register(message("s1"))
    assert ledger.register(message("s2"))
    ledger.close("s1")
    assert ledger.acknowledge(message("s2", sender="ubuntu", kind="ack"), original_sequence=0)

def test_ack_cannot_be_registered_as_pending():
    assert not AckLedger().register(message(kind="ack"))

def test_duplicate_pending_rejected():
    ledger = AckLedger()
    assert ledger.register(message())
    assert not ledger.register(message())
