"""Guardia de caducidad para C35, exclusivamente en simulacion.

El reloj se inyecta para pruebas deterministas. No crea conexiones ni audio.
"""
import math
from core.multiroom_auth_dry_run import AuthVerifier

class ExpiringAuthVerifier:
    """Sesiones registradas con plazo fijo; nunca se renuevan al recibir mensajes."""
    def __init__(self, key, peers, clock, *, ttl_seconds=30, max_sessions=32):
        if not callable(clock) or not isinstance(ttl_seconds, (int, float)) or isinstance(ttl_seconds, bool) or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("reloj o duracion invalida")
        if type(max_sessions) is not int or max_sessions < 1:
            raise ValueError("limite invalido")
        self.auth = AuthVerifier(key, peers)
        self.clock = clock
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        self.deadlines = {}
        self.expired = set()

    def register(self, session):
        if not isinstance(session, str) or not session or session in self.deadlines or session in self.expired:
            return False
        if len(self.deadlines) >= self.max_sessions:
            return False
        now = self.clock()
        if not isinstance(now, (int, float)) or not math.isfinite(now):
            return False
        self.deadlines[session] = now + self.ttl
        return True

    def verify(self, payload, signature, expected_session):
        if not isinstance(expected_session, str) or expected_session not in self.deadlines:
            return False
        now = self.clock()
        if not isinstance(now, (int, float)) or not math.isfinite(now):
            return False
        if now >= self.deadlines[expected_session]:
            self.expired.add(expected_session)
            del self.deadlines[expected_session]
            self.auth.closed.add(expected_session)
            return False
        return self.auth.verify(payload, signature, expected_session)
