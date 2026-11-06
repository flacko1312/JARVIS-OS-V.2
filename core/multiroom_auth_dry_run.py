"""Autenticacion de mensajes multiroom simulada. No abre sockets ni emite audio.

La clave de prueba se entrega por el llamador. En produccion se necesita
provision segura, rotacion y canal autenticado, que NO se implementan aqui.
"""
import hashlib
import hmac
import json
from core.multiroom_protocol_dry_run import parse_message

FIELDS = frozenset({"session", "sender", "target", "kind", "sequence", "delay_ms"})

def _canonical(payload):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError("mensaje invalido")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

def sign(payload, key):
    """Firma un mensaje ya validado con HMAC-SHA256 (clave solo en memoria)."""
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("clave demasiado corta")
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()

class AuthVerifier:
    """Verificador fail-closed con antirrepeticion por sesion/emisor."""
    def __init__(self, key, peers):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("clave demasiado corta")
        self.key = key
        self.peers = frozenset(peers)
        self.last = {}
        self.closed = set()

    def verify(self, payload, signature, expected_session):
        try:
            if not isinstance(signature, str) or len(signature) != 64:
                return False
            message = parse_message(payload, expected_session=expected_session, peers=self.peers)
            if message.session in self.closed:
                return False
            expected = sign(payload, self.key)
            if not hmac.compare_digest(expected, signature):
                return False
            index = (message.session, message.sender)
            if message.sequence <= self.last.get(index, -1):
                return False
            self.last[index] = message.sequence
            if message.kind == "abort":
                self.closed.add(message.session)
            return True
        except (TypeError, ValueError, UnicodeError):
            return False
