"""Pruebas adicionales de rechazo de mensajes multiroom malformados.

Solo datos sinteticos: no red, altavoces ni credenciales reales.
"""
import pytest
from core.multiroom_auth_dry_run import AuthVerifier, sign

KEY = b"test-key-only-not-for-production-00000001"
PEERS = {"windows", "ubuntu"}

def valid():
    return dict(session="s1", sender="windows", target="ubuntu",
                kind="prepare", sequence=0, delay_ms=0)

@pytest.mark.parametrize("bad", [None, [], "texto", 5, {},
    {"session": "s1"},
    dict(session="s1", sender="windows", target="ubuntu", kind="prepare", sequence=0, delay_ms=0, extra=True),
])
def test_malformed_payload_fails_closed(bad):
    assert not AuthVerifier(KEY, PEERS).verify(bad, "0"*64, "s1")

@pytest.mark.parametrize("signature", [None, 42, "", "g"*64, "0"*63, [], {}])
def test_malformed_signature_fails_closed(signature):
    assert not AuthVerifier(KEY, PEERS).verify(valid(), signature, "s1")

def test_rejected_message_does_not_consume_sequence():
    verifier = AuthVerifier(KEY, PEERS)
    message = valid()
    assert not verifier.verify(message, "0"*64, "s1")
    assert verifier.verify(message, sign(message, KEY), "s1")
