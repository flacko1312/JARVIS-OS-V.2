"""Punto de entrada para integrar el Router con el runtime de JARVIS.

El runtime de JARVIS en Windows importa este módulo y llama a
``process_input()`` para cada mensaje del usuario.  El resultado
indica si la petición fue resuelta por un handler (LILITH, local,
no implementado) o si debe pasar al flujo conversacional existente
(Gemini Live u otro).

Uso mínimo desde el runtime de Windows::

    from runtime import JarvisRuntime

    rt = JarvisRuntime()
    await rt.start()                # arranca monitor + client

    result = await rt.process_input("Enciende la luz del salón")
    if result["handled"]:
        show_to_user(result["message"])
    else:
        # flujo conversacional normal (Gemini, etc.)
        ...

    await rt.stop()                 # cierre limpio
"""
from __future__ import annotations

import logging
from typing import Any

from lilith_client.client import LilithClient
from lilith_client.config import LilithConfig
from lilith_client.monitor import ConnectionState, LilithMonitor
from router.core import JarvisRouter
from router.models import Domain

logger = logging.getLogger("jarvis.runtime")

_CONVERSATION_DOMAINS = frozenset({Domain.CONVERSATION})

_NOT_IMPLEMENTED_DOMAINS = frozenset({
    Domain.WINDOWS, Domain.FILES, Domain.VISION,
    Domain.DEVELOPMENT, Domain.KNOWLEDGE, Domain.WEB,
})


class JarvisRuntime:
    """Orquesta LilithClient + Monitor + Router como un único punto de entrada."""

    def __init__(self, config: LilithConfig | None = None):
        self._config = config or LilithConfig.from_env()
        self._client = LilithClient(self._config)
        self._monitor = LilithMonitor(self._client)
        self._router = JarvisRouter(client=self._client, monitor=self._monitor)
        self._running = False

    @property
    def client(self) -> LilithClient:
        return self._client

    @property
    def monitor(self) -> LilithMonitor:
        return self._monitor

    @property
    def router(self) -> JarvisRouter:
        return self._router

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def lilith_available(self) -> bool:
        return self._monitor.status.is_available

    async def start(self) -> None:
        if self._running:
            return
        await self._monitor.start()
        self._running = True
        logger.info("JarvisRuntime iniciado (LILITH: %s)", self._monitor.status.state.value)

    async def stop(self) -> None:
        if not self._running:
            return
        await self._monitor.stop()
        await self._client.close()
        self._running = False
        logger.info("JarvisRuntime detenido")

    async def __aenter__(self) -> JarvisRuntime:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()

    async def process_input(self, text: str) -> dict[str, Any]:
        """Procesa texto del usuario y devuelve resultado estructurado.

        Retorna un dict con:
        - ``handled`` (bool): True si el Router resolvió la petición.
          False si debe pasar al flujo conversacional existente.
        - ``domain`` (str): dominio clasificado.
        - ``confidence`` (float): confianza de la clasificación.
        - ``message`` (str | None): respuesta textual para el usuario (si handled).
        - ``data`` (dict | None): datos estructurados del handler.
        - ``pass_to_conversation`` (bool): True si el runtime de Windows debe
          enviar el texto al LLM conversacional (Gemini, etc.).
        """
        classification = self._router.classify(text)

        if classification.domain in _CONVERSATION_DOMAINS:
            return {
                "handled": False,
                "domain": classification.domain.value,
                "confidence": classification.confidence,
                "message": None,
                "data": None,
                "pass_to_conversation": True,
            }

        if classification.domain in _NOT_IMPLEMENTED_DOMAINS:
            return {
                "handled": False,
                "domain": classification.domain.value,
                "confidence": classification.confidence,
                "message": None,
                "data": None,
                "pass_to_conversation": True,
            }

        try:
            result = await self._router.execute(classification)
        except Exception as exc:
            logger.exception("Error ejecutando handler %s", classification.domain.value)
            return {
                "handled": False,
                "domain": classification.domain.value,
                "confidence": classification.confidence,
                "message": f"Error interno: {exc}",
                "data": None,
                "pass_to_conversation": True,
            }

        if result.get("offline"):
            return {
                "handled": True,
                "domain": classification.domain.value,
                "confidence": classification.confidence,
                "message": result.get("message", "LILITH no disponible"),
                "data": result,
                "pass_to_conversation": False,
            }

        if result.get("needs_clarification"):
            return {
                "handled": True,
                "domain": classification.domain.value,
                "confidence": classification.confidence,
                "message": result.get("message"),
                "data": result,
                "pass_to_conversation": False,
            }

        handled = result.get("ok", False)
        return {
            "handled": handled,
            "domain": classification.domain.value,
            "confidence": classification.confidence,
            "message": result.get("message"),
            "data": result.get("data"),
            "pass_to_conversation": not handled,
        }
