"""LILITH notification helpers for the JARVIS channel.

These helpers deliberately use the active Gemini Live engine as the voice path.
They do not publish MQTT, call Home Assistant, Android TTS or the legacy LILITH
voice topic.
"""
from __future__ import annotations

from typing import Any


def notification_voice_prompt(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "Aviso de LILITH").strip()
    summary = str(item.get("summary") or "").strip()
    severity = str(item.get("severity") or "info").strip()
    text = f"Aviso de LILITH ({severity}): {title}."
    if summary:
        text = f"{text} {summary}"
    return (
        "[NOTIFICACION PROACTIVA DE LILITH] Comunica al usuario este aviso de forma breve, "
        "en español, sin ejecutar herramientas ni iniciar acciones. "
        f"{text}"
    )


async def deliver_lilith_voice_notification(engine: Any, item: dict[str, Any]) -> bool:
    if not bool(item.get("voice_eligible")):
        return False
    send_text = getattr(engine, "send_text", None)
    if not callable(send_text):
        return False
    return bool(await send_text(notification_voice_prompt(item)))
