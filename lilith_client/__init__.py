"""lilith_client — Cliente HTTP para la API de integración LILITH.

Punto único de comunicación JARVIS → LILITH.
Todos los módulos de JARVIS pasan por este cliente.
"""
from lilith_client.client import LilithClient
from lilith_client.config import LilithConfig
from lilith_client.errors import (
    LilithError,
    LilithConnectionError,
    LilithAuthError,
    LilithNotFoundError,
    LilithForbiddenError,
    LilithServerError,
    LilithTimeoutError,
)
from lilith_client.monitor import ConnectionState, LilithMonitor, LilithStatus

__all__ = [
    "LilithClient",
    "LilithConfig",
    "LilithMonitor",
    "LilithStatus",
    "ConnectionState",
    "LilithError",
    "LilithConnectionError",
    "LilithAuthError",
    "LilithNotFoundError",
    "LilithForbiddenError",
    "LilithServerError",
    "LilithTimeoutError",
]
