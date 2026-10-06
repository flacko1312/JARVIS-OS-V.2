"""Router principal de JARVIS — conecta clasificador con handlers."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from lilith_client.client import LilithClient
from lilith_client.errors import LilithConnectionError, LilithError, LilithTimeoutError
from lilith_client.monitor import LilithMonitor
from router.classifier import classify
from router.models import Domain, RouteResult
from core.schedule_safety import schedule_semantics

logger = logging.getLogger("jarvis.router")

_LILITH_OFFLINE_MESSAGES = {
    Domain.MEMORY: "LILITH no está disponible. No puedo acceder a la memoria ahora.",
    Domain.HOME: "LILITH no está disponible. No puedo controlar la casa ahora.",
    Domain.LOCAL_AI: "LILITH no está disponible. No puedo usar IA local ahora.",
}

# JL-H005: JARVIS understands the intent (on/off + the reference text); LILITH owns the
# entities and the authorization. No device names live here.
_HOME_OFF_RE = re.compile(r"\b(ap[aá]g\w*|desact[ií]v\w*)\b", re.I)
_HOME_ON_RE = re.compile(r"\b(enci[eé]nd\w*|pr[eé]nd\w*|act[ií]v\w*)\b", re.I)
_HOME_FILLER_RE = re.compile(r"\b(por favor|ahora|ya|gracias)\b", re.I)
_HOME_CONFIRM_POLLS = 5
_HOME_CONFIRM_DELAY = 0.6

_HOME_ERROR_MESSAGES = {
    "entity_unavailable": "«{name}» no está disponible ahora mismo. No he hecho nada.",
    "entity_not_found": "No encuentro «{name}» en Home Assistant. No he hecho nada.",
    "home_assistant_unavailable": "Home Assistant no responde. No he hecho nada.",
    "home_assistant_error": "Home Assistant no responde. No he hecho nada.",
    "invalid_query": "No entendí qué dispositivo quieres controlar.",
    "invalid_entity_id": "No entendí qué dispositivo quieres controlar.",
}
_HOME_DENIED_CODES = frozenset({
    "domain_not_allowed", "service_not_allowed", "parameter_not_allowed",
    "prohibited_by_decision_level", "approval_required", "forbidden",
})


def _parse_home_command(text: str) -> tuple[str | None, str]:
    """Return (``turn_on``/``turn_off``/None, reference text) for a HOME utterance."""
    off, on = _HOME_OFF_RE.search(text), _HOME_ON_RE.search(text)
    hit = min((m for m in (off, on) if m), key=lambda m: m.start(), default=None)
    if hit is None:
        return None, ""
    service = "turn_off" if hit is off else "turn_on"
    reference = text[hit.end():].strip() or text[:hit.start()].strip()
    reference = _HOME_FILLER_RE.sub(" ", reference)
    reference = re.sub(r"\s+", " ", reference).strip(" \t.,;:!¡?¿")
    return service, reference


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
        semantics = schedule_semantics(raw)
        if semantics != "immediate":
            logger.warning(
                "Router HOME blocked scheduled text before effect: classification=%s",
                semantics,
            )
            return {
                "ok": False,
                "scheduled_request": True,
                "message": "Scheduled HOME request must be handled by the scheduling guard.",
            }
        service, reference = _parse_home_command(raw)
        entity_id = result.params.get("entity")

        if service is None or not (entity_id or reference):
            # No supported on/off command: nothing is done, the text goes on to Gemini.
            return {
                "ok": True,
                "action": "query",
                "message": "Dominio HOME detectado pero no pude extraer la entidad. ¿Qué dispositivo?",
                "needs_clarification": True,
            }

        name = reference or entity_id
        try:
            if not entity_id:
                # LILITH decides which entity (if any) the reference means.
                res = await self._client.home_resolve(reference)
                status = res.get("status")
                if status == "ambiguous":
                    names = ", ".join(
                        f"«{c.get('friendly_name') or c.get('entity_id')}»"
                        for c in res.get("candidates", [])
                    )
                    return self._home_reply(
                        f"¿A cuál te refieres: {names}? No he hecho nada.", "clarify", res)
                if status == "unknown":
                    return self._home_reply(
                        f"No conozco ningún dispositivo «{reference}». No he hecho nada.", "unknown", res)
                if status == "not_allowed":
                    return self._home_reply(
                        f"No tengo permiso para controlar «{reference}» desde JARVIS. No he hecho nada.",
                        "not_allowed", res)
                if status != "resolved" or not res.get("entity_id"):
                    return self._home_reply(
                        "LILITH no pudo resolver el dispositivo. No he hecho nada.", "error", res)
                entity_id = res["entity_id"]
                name = (res.get("friendly_name") or reference).strip()

            # The resolved target still goes through LILITH's normal /home/action policy.
            await self._client.home_action(entity_id, service)
        except (LilithConnectionError, LilithTimeoutError):
            return {
                "ok": False, "offline": True,
                "message": _LILITH_OFFLINE_MESSAGES[Domain.HOME],
            }
        except LilithError as exc:
            return self._home_reply(self._home_error_message(exc, name), "error", {"code": exc.code})

        expected = "on" if service == "turn_on" else "off"
        state = await self._confirm_state(entity_id, expected)
        verb = "encendida" if service == "turn_on" else "apagada"
        if state == expected:
            msg = f"Hecho: «{name}» {verb} (confirmado: {state})."
        else:
            msg = (f"Envié la orden a «{name}», pero no pude confirmar el cambio "
                   f"(estado actual: {state or 'desconocido'}).")
        reply = self._home_reply(msg, service, {"entity_id": entity_id, "action": service})
        reply["confirmed"] = state == expected
        return reply

    @staticmethod
    def _home_reply(message: str, action: str, data: dict | None = None) -> dict[str, Any]:
        # ok=True: LILITH handled it (and said honestly what happened); the text must NOT
        # also be sent to Gemini, which could claim a success that never happened.
        return {"ok": True, "action": action, "message": message, "data": data or {}}

    @staticmethod
    def _home_error_message(exc: LilithError, name: str) -> str:
        code = getattr(exc, "code", "")
        if code in _HOME_DENIED_CODES:
            return f"No tengo permiso para hacer eso con «{name}». No he hecho nada."
        template = _HOME_ERROR_MESSAGES.get(code)
        if template:
            return template.format(name=name)
        return f"LILITH rechazó la orden sobre «{name}» ({code or 'error'}). No he hecho nada."

    async def _confirm_state(self, entity_id: str, expected: str) -> str | None:
        """Read the entity back from LILITH/HA; never raises."""
        state = None
        for attempt in range(_HOME_CONFIRM_POLLS):
            try:
                data = await self._client.home_entity(entity_id)
                state = data.get("state") if isinstance(data, dict) else None
            except Exception:  # noqa: BLE001 - readback is best-effort
                state = None
            if state == expected:
                break
            if attempt < _HOME_CONFIRM_POLLS - 1:
                await asyncio.sleep(_HOME_CONFIRM_DELAY)
        return state

    async def _handle_conversation(self, result: RouteResult) -> dict[str, Any]:
        return {
            "ok": True,
            "action": "chat",
            "message": "Conversación local — pendiente de implementar respuesta LLM.",
        }

    async def _handle_gemini_passthrough(self, result: RouteResult) -> dict[str, Any]:
        """JL-R002: domains resolved by Gemini's own tools on Windows."""
        return {
            "ok": True,
            "action": "passthrough",
            "pass_to_conversation": True,
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
    Domain.WINDOWS: JarvisRouter._handle_gemini_passthrough,
    Domain.FILES: JarvisRouter._handle_gemini_passthrough,
    Domain.VISION: JarvisRouter._handle_gemini_passthrough,
    Domain.DEVELOPMENT: JarvisRouter._handle_gemini_passthrough,
    Domain.KNOWLEDGE: JarvisRouter._handle_gemini_passthrough,
    Domain.LOCAL_AI: JarvisRouter._handle_not_implemented,
    Domain.WEB: JarvisRouter._handle_gemini_passthrough,
}
