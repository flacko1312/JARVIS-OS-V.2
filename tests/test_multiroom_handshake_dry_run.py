import pytest
from core.multiroom_handshake_dry_run import Handshake

def test_success():
    h = Handshake()
    assert h.prepare(0)
    assert h.ready(500)
    assert h.start()
    assert not h.start()

def test_timeout_retries_then_abort():
    h = Handshake(deadline_ms=100, max_retries=2)
    assert h.prepare(0)
    assert h.tick(100) == "waiting"
    assert h.attempts == 2
    assert h.tick(200) == "waiting"
    assert h.attempts == 3
    assert h.tick(300) == "aborted"
    assert not h.start()

def test_late_ready_aborts():
    h = Handshake(deadline_ms=100)
    h.prepare(0)
    assert not h.ready(101)
    assert h.state == "aborted"

def test_no_start_without_ready():
    h = Handshake()
    assert not h.start()
    h.prepare(0)
    assert not h.start()

def test_abort_terminal():
    h = Handshake()
    h.prepare(0)
    h.abort()
    assert not h.ready(1)
    assert not h.prepare(2)
    assert h.tick(10000) == "aborted"

def test_retrograde_clock_fails_closed():
    h = Handshake()
    h.prepare(100)
    assert h.tick(99) == "aborted"

@pytest.mark.parametrize("deadline,retries", [(0,1),(-1,1),(100,-1),(100,11),(True,1),(100,False)])
def test_invalid_configuration(deadline,retries):
    with pytest.raises(ValueError):
        Handshake(deadline_ms=deadline,max_retries=retries)

def test_invalid_ready_time():
    h = Handshake()
    h.prepare(10)
    assert not h.ready(9)
    assert h.state == "aborted"

def test_reject_duplicate_prepare():
    h = Handshake()
    assert h.prepare(0)
    assert not h.prepare(1)
    assert h.attempts == 1
