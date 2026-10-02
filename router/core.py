"""Router principal de JARVIS — conecta clasificador con handlers."""
from __future__ import annotations

import logging
from typing import Any

from lilith_client.client import LilithClient
from lilith_client.monitor import LilithMonitor
from router.classifier import classify
from router.models import Domain, RouteResult

logger = logging.getLogger("jarvis.router")

_LILITH_OFFLINE_MESSAGES = {
    Domain.MEMORY: "LILITH no está disponible. No puedo acceder a la memoria ahora.",
    Domain.HOME: "LILITH no está disponible. No puedo controlar la casa ahora.",
    Domain.LOCAL_AI: "LILITH no está disponible. No puedo usar IA local ahora.",
}


class JarvisRouter:
    """Enruta peticiones del usuario al handler correcto."""

    def __init__(self, client: LilithClient, monitor: LilithMonitor):
        self._client = client
        self._monitor = monitor

    def classify(self, user_input: str) -> RouteResult:
        return classify(user_input)

    async def execute(self, result: RouteResult) -> dict[str, Any]:
        if result.requires_lilith and not self._monitor.status.is_available:
            msg = _LILITH_OFFLINE_MESSAGES.get(
                result.domain,
                "LILITH no está disponible.",
            )
            logger.warning("Router: LILITH offline, dominio=%s", result.domain.value)
            return {"ok": False, "offline": True, "message": msg}

        handler = _HANDLERS.get(result.domain)
        if handler is None:
            return {
                "ok": False,
                "message": f"Handler '{result.domain.value}' no implementado aún.",
            }

        logger.info(
            "Router: '%s' → domain=%s handler=%s confidence=%.2f",
            result.params.get("raw_input", ""),
            result.domain.value,
            result.handler,
            result.confidence,
        )
        return await handler(self, result)

    async def route(self, user_input: str) -> dict[str, Any]:
        result = self.classify(user_input)
        return await self.execute(result)

    # ── Handlers ───────────────────────────────────────────────────────

    async def _handle_memory(self, result: RouteResult) -> dict[str, Any]:
        raw = result.params.get("raw_input", "")

        if any(kw in raw.lower() for kw in ("recuerda", "acuérdate", "acuerdate", "no olvides", "guarda en memoria")):
            value = raw
            for prefix in ("recuerda que ", "acuérdate de que ", "acuerdate de que ",
                           "no olvides que ", "guarda en memoria: ", "recuerda: "):
                if raw.lower().startswith(prefix):
                    value = raw[len(prefix):]
                    break
            key = value[:60].lower().replace(" ", "_")
            data = await self._client.store_memory(key, value, category="jarvis_fact")
            return {"ok": True, "action": "store", "data": data}

        results = await self._client.search_memory(raw)
        return {"ok": True, "action": "search", "data": results}

    async def _handle_home(self, result: RouteResult) -> dict[str, Any]:
        raw = result.params.get("raw_input", "")
        lower = raw.lower()

        entity_id = result.params.get("entity")

        if any(kw in lower for kw in ("encien", "prend", "activa")):
            if entity_id:
                data = await self._client.home_action(entity_id, "turn_on")
                return {"ok": True, "action": "turn_on", "data": data}
        elif any(kw in lower for kw in ("apag", "desactiva")):
            if entity_id:
                data = await self._client.home_action(entity_id, "turn_off")
                return {"ok": True, "action": "turn_off", "data": data}

        return {
            "ok": True,
            "action": "query",
            "message": "Dominio HOME detectado pero no pude extraer la entidad. ¿Qué dispositivo?",
            "needs_clarification": True,
        }

    async def _handle_conversation(self, result: RouteResult) -> dict[str, Any]:
        return {
            "ok": True,
            "action": "chat",
            "message": "Conversación local — pendiente de implementar respuesta LLM.",
        }

    async def _handle_not_implemented(self, result: RouteResult) -> dict[str, Any]:
        return {
            "ok": False,
            "message": f"Handler '{result.domain.value}' no implementado aún.",
        }


_HANDLERS: dict[Domain, Any] = {
    Domain.MEMORY: JarvisRouter._handle_memory,
    Domain.HOME: JarvisRouter._handle_home,
    Domain.CONVERSATION: JarvisRouter._handle_conversation,
    Domain.WINDOWS: JarvisRouter._handle_not_implemented,
    Domain.FILES: JarvisRouter._handle_not_implemented,
    Domain.VISION: JarvisRouter._handle_not_implemented,
    Domain.DEVELOPMENT: JarvisRouter._handle_not_implemented,
    Domain.KNOWLEDGE: JarvisRouter._handle_not_implemented,
    Domain.LOCAL_AI: JarvisRouter._handle_not_implemented,
    Domain.WEB: JarvisRouter._handle_not_implemented,
}
