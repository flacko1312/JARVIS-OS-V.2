"""Contrato de mensajes multiroom: validacion pura, sin red ni audio."""
from dataclasses import dataclass
from typing import Mapping

KINDS = frozenset({"prepare", "ready", "start", "abort", "ack"})
MAX_SKEW_MS = 120
MAX_DELAY_MS = 2000

@dataclass(frozen=True)
class Message:
    session: str
    sender: str
    target: str
    kind: str
    sequence: int
    delay_ms: int = 0

def parse_message(payload: Mapping[str, object], *, expected_session: str, peers: frozenset[str]) -> Message:
    """Rechaza datos ambiguos y emisores ajenos antes de cualquier accion."""
    if not isinstance(payload, dict):
        raise ValueError("payload invalido")
    required = {"session", "sender", "target", "kind", "sequence", "delay_ms"}
    if set(payload) != required:
        raise ValueError("campos invalidos")
    session, sender, target, kind = (payload[k] for k in ("session", "sender", "target", "kind"))
    seq, delay = payload["sequence"], payload["delay_ms"]
    if not all(isinstance(x, str) and x for x in (session, sender, target, kind)):
        raise ValueError("identificadores invalidos")
    if session != expected_session or sender not in peers or target not in peers or sender == target:
        raise ValueError("sesion o destino no autorizado")
    if kind not in KINDS or type(seq) is not int or seq < 0 or type(delay) is not int or not 0 <= delay <= MAX_DELAY_MS:
        raise ValueError("tipo, secuencia o latencia invalidos")
    return Message(session, sender, target, kind, seq, delay)

class SessionTracker:
    """Acepta mensajes en orden estricto; abort invalida la sesion."""
    def __init__(self):
        self.last = {}
        self.aborted = set()

    def accept(self, message: Message) -> bool:
        if message.session in self.aborted:
            return False
        key = (message.session, message.sender)
        if message.sequence <= self.last.get(key, -1):
            return False
        self.last[key] = message.sequence
        if message.kind == "abort":
            self.aborted.add(message.session)
        return True
