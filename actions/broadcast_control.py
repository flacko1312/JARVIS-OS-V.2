"""Broadcast announcements for JARVIS.

Sends a TTS announcement on the current device's speakers and optionally
triggers HA media_player TTS if a Home Assistant integration is available.

On AURORA/Windows: speaks via Gemini Live player.speak().
On Ubuntu headless: uses the local TTS engine (sounddevice playback).

For multi-room broadcast (all home speakers) LILITH + HA must be reachable,
which is a Phase 8 integration task. This module handles the local speaker
path and queues a LILITH request when it is reachable.

Supported actions:
  announce  — speak a message immediately on local speakers (default)
  broadcast — alias for announce; also attempts LILITH broadcast
  status    — connection state
"""

from __future__ import annotations

import os
import platform
import threading

_SYSTEM = platform.system()
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Local TTS
# ---------------------------------------------------------------------------

def _speak_local(message: str, player) -> str:
    """Speak via Gemini Live player (AURORA) or sounddevice TTS (headless)."""
    if player is not None:
        try:
            player.speak(message)
            return f"Anuncio reproducido: {message}"
        except Exception as exc:
            return f"Error al reproducir el anuncio: {exc}"

    # Headless: try TTS engine directly
    try:
        from actions.tts_engine import speak as _tts_speak
        _tts_speak(message)
        return f"Anuncio reproducido: {message}"
    except Exception:
        pass

    # Last fallback: pyttsx3 or espeak
    try:
        import subprocess
        subprocess.run(["espeak-ng", "-v", "es", message], timeout=10, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Anuncio reproducido (espeak): {message}"
    except Exception:
        pass

    return f"No se pudo reproducir el anuncio (sin TTS disponible): {message}"


# ---------------------------------------------------------------------------
# LILITH broadcast (best-effort)
# ---------------------------------------------------------------------------

def _try_lilith_broadcast(message: str) -> str:
    """Send broadcast request to LILITH if reachable. Returns status string."""
    try:
        api_url = os.environ.get("LILITH_API_URL", "").rstrip("/")
        api_key = os.environ.get("LILITH_API_KEY", "")
        if not api_url or not api_key:
            return ""

        import urllib.request
        import json
        payload = json.dumps({"message": message, "type": "broadcast"}).encode()
        req = urllib.request.Request(
            f"{api_url}/api/broadcast",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201, 202):
                return " Broadcast enviado a LILITH."
        return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _action_announce(message: str, player, broadcast: bool = False) -> str:
    if not message:
        return "Especifica el mensaje a anunciar."

    local = _speak_local(message, player)

    if broadcast:
        lilith_result = _try_lilith_broadcast(message)
        return local + lilith_result

    return local


def _action_status(player) -> str:
    parts = []
    if player is not None:
        parts.append("TTS local: disponible (Gemini Live player).")
    else:
        try:
            from actions.tts_engine import speak as _tts_speak  # noqa: F401
            parts.append("TTS local: disponible (headless TTS engine).")
        except Exception:
            parts.append("TTS local: NO disponible (sin player ni tts_engine).")

    api_url = os.environ.get("LILITH_API_URL", "")
    if api_url:
        parts.append(f"LILITH API: {api_url} (broadcast multi-sala en función de disponibilidad).")
    else:
        parts.append("LILITH API: no configurada (broadcast limitado al dispositivo local).")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def broadcast_control(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "announce").lower().strip()

    if action in ("announce", "say", "habla", "di"):
        message = (
            params.get("message", "")
            or params.get("text", "")
            or params.get("query", "")
        )
        return _action_announce(message, player, broadcast=False)

    if action in ("broadcast", "broadcast_all", "anuncio_hogar"):
        message = (
            params.get("message", "")
            or params.get("text", "")
            or params.get("query", "")
        )
        return _action_announce(message, player, broadcast=True)

    if action == "status":
        return _action_status(player)

    return (
        f"Acción '{action}' no reconocida. "
        "Acciones: announce, broadcast, status."
    )
