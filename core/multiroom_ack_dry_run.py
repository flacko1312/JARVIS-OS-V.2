"""Correlacion de ACK multiroom, sin red ni audio.

Un ACK solo confirma un mensaje previamente registrado para la misma sesion.
El identificador de sesion nunca se reutiliza tras el cierre.
"""
from dataclasses import dataclass
from core.multiroom_protocol_dry_run import Message

@dataclass(frozen=True)
class Pending:
    session: str
    sender: str
    target: str
    sequence: int

class AckLedger:
    def __init__(self):
        self.pending = set()
        self.completed = set()
        self.closed = set()

    def register(self, message: Message) -> bool:
        if message.kind == "ack" or message.session in self.closed:
            return False
        key = Pending(message.session, message.sender, message.target, message.sequence)
        if key in self.pending or key in self.completed:
            return False
        self.pending.add(key)
        return True

    def acknowledge(self, ack: Message, *, original_sequence: int) -> bool:
        if ack.kind != "ack" or type(original_sequence) is not int or original_sequence < 0:
            return False
        if ack.session in self.closed:
            return False
        # Invertir origen y destino es obligatorio; nunca aceptar auto-ACK.
        key = Pending(ack.session, ack.target, ack.sender, original_sequence)
        if key not in self.pending:
            return False
        self.pending.remove(key)
        self.completed.add(key)
        return True

    def close(self, session: str) -> None:
        self.closed.add(session)
        self.pending = {p for p in self.pending if p.session != session}
