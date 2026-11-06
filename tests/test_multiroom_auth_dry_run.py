"""Seguridad hermetica: claves ficticias, sin red ni sonido."""
import pytest
from core.multiroom_auth_dry_run import AuthVerifier, sign

KEY = b"test-key-only-not-for-production-00000001"
PEERS = {"windows", "ubuntu"}

def payload(**changes):
    result = dict(session="s1", sender="windows", target="ubuntu",
                  kind="prepare", sequence=0, delay_ms=0)
    result.update(changes)
    return result

def test_valid_signed_message():
    v = AuthVerifier(KEY, PEERS)
    p = payload()
    assert v.verify(p, sign(p, KEY), "s1")

@pytest.mark.parametrize("field,value", [
    ("session", "s2"), ("sender", "intruder"), ("target", "intruder"),
    ("kind", "execute"), ("delay_ms", 9000), ("sequence", True),
])
def test_tampering_rejected(field, value):
    p = payload()
    sig = sign(p, KEY)
    p[field] = value
    assert not AuthVerifier(KEY, PEERS).verify(p, sig, "s1")

def test_replay_rejected():
    p = payload()
    v = AuthVerifier(KEY, PEERS)
    sig = sign(p, KEY)
    assert v.verify(p, sig, "s1")
    assert not v.verify(p, sig, "s1")

def test_wrong_key_rejected():
    p = payload()
    assert not AuthVerifier(KEY, PEERS).verify(p, sign(p, b"x"*32), "s1")

def test_bad_signature_rejected():
    assert not AuthVerifier(KEY, PEERS).verify(payload(), "invalid", "s1")

def test_wrong_expected_session_rejected():
    p = payload()
    assert not AuthVerifier(KEY, PEERS).verify(p, sign(p, KEY), "s2")

def test_abort_closes_session():
    v = AuthVerifier(KEY, PEERS)
    p = payload(kind="abort")
    assert v.verify(p, sign(p, KEY), "s1")
    later = payload(sequence=1)
    assert not v.verify(later, sign(later, KEY), "s1")

def test_separate_sessions():
    v = AuthVerifier(KEY, PEERS)
    for session in ("s1", "s2"):
        p = payload(session=session)
        assert v.verify(p, sign(p, KEY), session)

def test_short_key_rejected():
    with pytest.raises(ValueError):
        AuthVerifier(b"short", PEERS)

def test_extra_fields_rejected():
    p = payload(extra="unexpected")
    with pytest.raises(ValueError):
        sign(p, KEY)
