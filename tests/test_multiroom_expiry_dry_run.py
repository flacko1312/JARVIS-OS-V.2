"""Tests hermeticos de caducidad y cupo multiroom."""
import pytest
from core.multiroom_auth_dry_run import sign
from core.multiroom_expiry_dry_run import ExpiringAuthVerifier

KEY = b"test-key-only-not-for-production-00000001"

def payload(session="s1", sequence=0):
    return dict(session=session, sender="windows", target="ubuntu", kind="prepare", sequence=sequence, delay_ms=0)

def setup(ttl=10, cap=2):
    ticks = [100.0]
    guard = ExpiringAuthVerifier(KEY, {"windows", "ubuntu"}, lambda: ticks[0], ttl_seconds=ttl, max_sessions=cap)
    return guard, ticks

def test_valid_before_expiry():
    g, ticks = setup()
    assert g.register("s1")
    ticks[0] = 109.99
    p = payload()
    assert g.verify(p, sign(p, KEY), "s1")

def test_expiry_boundary_and_no_revival():
    g, ticks = setup()
    assert g.register("s1")
    ticks[0] = 110
    p = payload()
    assert not g.verify(p, sign(p, KEY), "s1")
    ticks[0] = 101
    assert not g.register("s1")
    assert not g.verify(p, sign(p, KEY), "s1")

def test_unregistered_session_rejected():
    g, _ = setup()
    p = payload()
    assert not g.verify(p, sign(p, KEY), "s1")

def test_cap_blocks_new_sessions():
    g, _ = setup(cap=1)
    assert g.register("s1")
    assert not g.register("s2")

def test_duplicate_registration_rejected():
    g, _ = setup()
    assert g.register("s1")
    assert not g.register("s1")

def test_expiry_isolation():
    g, ticks = setup()
    assert g.register("s1")
    ticks[0] = 105
    assert g.register("s2")
    ticks[0] = 110
    for session, expected in [("s1", False), ("s2", True)]:
        p = payload(session)
        assert g.verify(p, sign(p, KEY), session) is expected

@pytest.mark.parametrize("ttl", [0, -1, float("nan"), float("inf"), True])
def test_bad_ttl_rejected(ttl):
    with pytest.raises(ValueError):
        ExpiringAuthVerifier(KEY, {"windows", "ubuntu"}, lambda: 1, ttl_seconds=ttl)

def test_bad_clock_fails_closed():
    g, ticks = setup()
    assert g.register("s1")
    ticks[0] = float("nan")
    p = payload()
    assert not g.verify(p, sign(p, KEY), "s1")
