"""Errores tipados del cliente LILITH."""
from __future__ import annotations


class LilithError(Exception):
    """Error base de comunicación con LILITH."""
    def __init__(self, message: str, *, code: str = "unknown", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LilithConnectionError(LilithError):
    """LILITH no es alcanzable por red."""
    def __init__(self, message: str = "LILITH no disponible"):
        super().__init__(message, code="connection_error", retryable=True)


class LilithTimeoutError(LilithError):
    """La petición a LILITH excedió el timeout."""
    def __init__(self, message: str = "Timeout contactando LILITH"):
        super().__init__(message, code="timeout", retryable=True)


class LilithAuthError(LilithError):
    """Token inválido o ausente (401)."""
    def __init__(self, message: str = "Autenticación fallida"):
        super().__init__(message, code="auth_error", retryable=False)


class LilithForbiddenError(LilithError):
    """Nivel de autoridad insuficiente o acción prohibida (403)."""
    def __init__(self, message: str = "Acceso denegado", *, code: str = "forbidden"):
        super().__init__(message, code=code, retryable=False)


class LilithNotFoundError(LilithError):
    """Recurso no encontrado (404)."""
    def __init__(self, message: str = "Recurso no encontrado"):
        super().__init__(message, code="not_found", retryable=False)


class LilithServerError(LilithError):
    """Error del servidor LILITH (5xx)."""
    def __init__(self, message: str = "Error interno de LILITH"):
        super().__init__(message, code="server_error", retryable=True)
