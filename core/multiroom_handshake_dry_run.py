"""Simulador determinista de handshake multiroom. Sin red, reloj real ni audio."""
from dataclasses import dataclass

@dataclass
class Handshake:
    """El reloj y las respuestas son entradas simuladas; nunca ejecuta acciones."""
    deadline_ms: int = 1000
    max_retries: int = 2

    def __post_init__(self):
        if type(self.deadline_ms) is not int or self.deadline_ms <= 0:
            raise ValueError("deadline invalido")
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 10:
            raise ValueError("reintentos invalidos")
        self.state = "new"
        self.attempts = 0
        self.sent_at = None

    def prepare(self, now_ms: int) -> bool:
        if type(now_ms) is not int or now_ms < 0 or self.state != "new":
            return False
        self.state = "waiting"
        self.attempts = 1
        self.sent_at = now_ms
        return True

    def ready(self, now_ms: int) -> bool:
        if self.state != "waiting" or type(now_ms) is not int:
            return False
        if now_ms < self.sent_at or now_ms - self.sent_at > self.deadline_ms:
            self.state = "aborted"
            return False
        self.state = "ready"
        return True

    def tick(self, now_ms: int) -> str:
        if self.state != "waiting":
            return self.state
        if type(now_ms) is not int or now_ms < self.sent_at:
            self.state = "aborted"
        elif now_ms - self.sent_at >= self.deadline_ms:
            if self.attempts > self.max_retries:
                self.state = "aborted"
            else:
                self.attempts += 1
                self.sent_at = now_ms
        return self.state

    def start(self) -> bool:
        if self.state != "ready":
            return False
        self.state = "started"
        return True

    def abort(self):
        self.state = "aborted"
