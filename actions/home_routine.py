"""Smart home meta-routines for JARVIS.

Provides pre-defined domestic routines that combine TTS announcements,
device control via LILITH, and information queries (weather, time, etc.).

Each routine follows the principle:
  1. Announce via TTS what is happening
  2. Query relevant information (weather, time)
  3. Control devices (only those confirmed available, with explicit authorization)
  4. Report results

Routines:
  buenos_dias       — Morning greeting: time, weather, agenda summary
  me_voy            — Leaving home: announce + optionally turn off lights/devices
  llegue_a_casa     — Arrived home: greeting + optionally turn on lights
  buenas_noches     — Goodnight: announce + optionally turn off lights + set alarm suggestion
  modo_taller       — Workshop mode: adjust lighting, minimize distractions

No physical device actions are taken automatically without explicit user confirmation.
Device actions are ALWAYS reported to the user before and after execution.
"""

from __future__ import annotations

import os
from typing import Any

# ---------------------------------------------------------------------------
# Routine definitions
# ---------------------------------------------------------------------------

_ROUTINES: dict[str, dict] = {
    "buenos_dias": {
        "name": "Buenos días",
        "description": "Rutina matutina: saludo, hora, tiempo meteorológico y resumen del día.",
        "steps": [
            "greet",
            "time",
            "weather",
            "summary",
        ],
        "device_action": None,
        "announcement": "¡Buenos días! Voy a darte el resumen matutino.",
    },
    "me_voy": {
        "name": "Me voy de casa",
        "description": "Rutina de salida: anuncio, apagar luces y enchufes (con confirmación).",
        "steps": [
            "announce",
            "device_off_all",
        ],
        "device_action": "turn_off",
        "announcement": "Hasta luego. Iniciando rutina de salida.",
        "device_targets": ["light.bombilla_mueble", "light.bombilla_tv", "switch.cargador_hub"],
        "device_confirm_required": True,
    },
    "llegue_a_casa": {
        "name": "He llegado a casa",
        "description": "Rutina de llegada: saludo y encender luces según hora (con confirmación).",
        "steps": [
            "greet_arrival",
            "time",
            "device_on_lights",
        ],
        "device_action": "turn_on",
        "announcement": "¡Bienvenido a casa! Ya estoy aquí.",
        "device_targets": ["light.bombilla_mueble"],
        "device_confirm_required": True,
    },
    "buenas_noches": {
        "name": "Buenas noches",
        "description": "Rutina nocturna: anuncio, apagar luces (con confirmación), sugerencia de alarma.",
        "steps": [
            "announce",
            "device_off_lights",
            "suggest_alarm",
        ],
        "device_action": "turn_off",
        "announcement": "Buenas noches. Iniciando rutina nocturna.",
        "device_targets": ["light.bombilla_mueble", "light.bombilla_tv"],
        "device_confirm_required": True,
    },
    "modo_taller": {
        "name": "Modo taller",
        "description": "Activa iluminación de trabajo y silencia notificaciones no urgentes.",
        "steps": [
            "announce",
            "device_workshop_light",
        ],
        "device_action": "turn_on",
        "announcement": "Modo taller activado. Configurando entorno de trabajo.",
        "device_targets": ["light.bombilla_mueble"],
        "device_params": {"brightness": 255, "color_temp": 4000},
        "device_confirm_required": True,
    },
}


# ---------------------------------------------------------------------------
# LILITH HTTP helpers (no dependency on main.py classes)
# ---------------------------------------------------------------------------

def _entity_is_available(entity_id: str) -> bool:
    """Return True if the entity is reachable in Home Assistant, False if unavailable/unknown."""
    import json
    import urllib.request

    api_url = os.environ.get("LILITH_API_URL", "").rstrip("/")
    api_key = os.environ.get("LILITH_API_KEY", "")
    if not api_url or not api_key:
        return True  # assume available if LILITH not configured (let action fail naturally)
    try:
        req = urllib.request.Request(
            f"{api_url}/api/v1/integration/home/entity/{entity_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            state = data.get("data", {}).get("state", "unknown")
            return state not in ("unavailable", "unknown")
    except Exception:
        return True  # on error, let the action attempt and fail naturally


def _lilith_home_action(entity_id: str, action: str,
                        extra_params: dict | None = None) -> dict:
    """Call LILITH home/action endpoint directly."""
    import json
    import urllib.request

    api_url = os.environ.get("LILITH_API_URL", "").rstrip("/")
    api_key = os.environ.get("LILITH_API_KEY", "")
    if not api_url or not api_key:
        return {"ok": False, "error": "LILITH not configured"}

    payload: dict[str, Any] = {"entity_id": entity_id, "action": action}
    if extra_params:
        payload["parameters"] = extra_params

    try:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{api_url}/api/v1/integration/home/action",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _lilith_home_resolve(query: str) -> dict:
    """Resolve a natural-language device name to an entity_id via LILITH."""
    import json
    import urllib.request

    api_url = os.environ.get("LILITH_API_URL", "").rstrip("/")
    api_key = os.environ.get("LILITH_API_KEY", "")
    if not api_url or not api_key:
        return {"status": "error", "error": "LILITH not configured"}

    try:
        body = json.dumps({"query": query}).encode()
        req = urllib.request.Request(
            f"{api_url}/api/v1/integration/home/resolve",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _get_weather_summary() -> str:
    """Return a brief weather summary using weather_report action if available."""
    try:
        from actions.weather_report import weather_report
        result = weather_report({"action": "current", "location": "Madrid"}, None, None)
        if result and len(str(result)) > 10:
            lines = str(result).split("\n")
            return lines[0] if lines else str(result)[:200]
    except Exception:
        pass
    return "El tiempo no está disponible ahora mismo."


def _get_current_time() -> str:
    """Return current time string from system clock."""
    import datetime
    now = datetime.datetime.now()
    hour = now.hour
    minute = now.minute
    day_name = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][now.weekday()]
    month_name = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"][now.month - 1]
    return (
        f"Son las {hour}:{minute:02d} del {day_name} "
        f"{now.day} de {month_name} de {now.year}."
    )


# ---------------------------------------------------------------------------
# Routine execution
# ---------------------------------------------------------------------------

def _execute_buenos_dias(confirm_devices: bool = False) -> str:
    time_str = _get_current_time()
    weather_str = _get_weather_summary()
    return (
        f"¡Buenos días! 🌅\n"
        f"  {time_str}\n"
        f"  Tiempo: {weather_str}\n"
        f"  Dispositivos: sin cambios (modo solo información).\n"
        f"  Para controlar dispositivos di: 'enciende las luces'."
    )


def _execute_me_voy(confirm_devices: bool = False) -> str:
    routine = _ROUTINES["me_voy"]
    targets = routine.get("device_targets", [])
    lines = [routine["announcement"]]

    if not confirm_devices:
        lines.append(
            f"  ⚠️ Acción de dispositivos PENDIENTE de confirmación.\n"
            f"  Dispositivos que se apagarían: {', '.join(targets)}\n"
            f"  Di 'confirma me voy' o 'apaga todos los dispositivos' para ejecutar."
        )
    else:
        results = []
        for entity_id in targets:
            if not _entity_is_available(entity_id):
                results.append(f"  {entity_id}: ⚠️ dispositivo offline (omitido)")
            else:
                r = _lilith_home_action(entity_id, "turn_off")
                ok = r.get("ok", False) or (isinstance(r.get("data"), dict) and r["data"].get("status") != "error")
                results.append(f"  {entity_id}: {'✓ apagado' if ok else '✗ error al apagar'}")
        lines.append("  Dispositivos:\n" + "\n".join(results))

    lines.append("  ¡Hasta pronto!")
    return "\n".join(lines)


def _execute_llegue_a_casa(confirm_devices: bool = False) -> str:
    routine = _ROUTINES["llegue_a_casa"]
    targets = routine.get("device_targets", [])
    time_str = _get_current_time()
    lines = [routine["announcement"], f"  {time_str}"]

    if not confirm_devices:
        lines.append(
            f"  ⚠️ Acción de dispositivos PENDIENTE de confirmación.\n"
            f"  Dispositivos que se encenderían: {', '.join(targets)}\n"
            f"  Di 'confirma llegué a casa' o 'enciende las luces' para ejecutar."
        )
    else:
        results = []
        for entity_id in targets:
            if not _entity_is_available(entity_id):
                results.append(f"  {entity_id}: ⚠️ dispositivo offline (omitido)")
            else:
                r = _lilith_home_action(entity_id, "turn_on")
                ok = r.get("ok", False) or (isinstance(r.get("data"), dict) and r["data"].get("status") != "error")
                results.append(f"  {entity_id}: {'✓ encendido' if ok else '✗ error al encender'}")
        lines.append("  Dispositivos:\n" + "\n".join(results))

    return "\n".join(lines)


def _execute_buenas_noches(confirm_devices: bool = False) -> str:
    routine = _ROUTINES["buenas_noches"]
    targets = routine.get("device_targets", [])
    lines = [routine["announcement"]]

    if not confirm_devices:
        lines.append(
            f"  ⚠️ Acción de dispositivos PENDIENTE de confirmación.\n"
            f"  Dispositivos que se apagarían: {', '.join(targets)}\n"
            f"  Di 'confirma buenas noches' o 'apaga las luces' para ejecutar.\n"
            f"  Puedo también configurar una alarma para mañana. Di: 'ponme alarma a las 7'."
        )
    else:
        results = []
        for entity_id in targets:
            if not _entity_is_available(entity_id):
                results.append(f"  {entity_id}: ⚠️ dispositivo offline (omitido)")
            else:
                r = _lilith_home_action(entity_id, "turn_off")
                ok = r.get("ok", False) or (isinstance(r.get("data"), dict) and r["data"].get("status") != "error")
                results.append(f"  {entity_id}: {'✓ apagado' if ok else '✗ error al apagar'}")
        lines.append("  Dispositivos:\n" + "\n".join(results))
        lines.append("  ¡Buenas noches! Que descanses.")

    return "\n".join(lines)


def _execute_modo_taller(confirm_devices: bool = False) -> str:
    routine = _ROUTINES["modo_taller"]
    targets = routine.get("device_targets", [])
    extra = routine.get("device_params", {})
    lines = [routine["announcement"]]

    if not confirm_devices:
        lines.append(
            f"  ⚠️ Acción de dispositivos PENDIENTE de confirmación.\n"
            f"  Se ajustarían: {', '.join(targets)} (brillo máximo, luz blanca fría)\n"
            f"  Di 'confirma modo taller' para ejecutar."
        )
    else:
        results = []
        for entity_id in targets:
            if not _entity_is_available(entity_id):
                results.append(f"  {entity_id}: ⚠️ dispositivo offline (omitido)")
            else:
                r = _lilith_home_action(entity_id, "turn_on", extra)
                ok = r.get("ok", False) or (isinstance(r.get("data"), dict) and r["data"].get("status") != "error")
                results.append(f"  {entity_id}: {'✓ configurado' if ok else '✗ error al configurar'}")
        lines.append("  Dispositivos:\n" + "\n".join(results))
        lines.append("  Modo taller activo. Brillo al máximo, luz blanca fría.")

    return "\n".join(lines)


_ROUTINE_EXECUTORS = {
    "buenos_dias": _execute_buenos_dias,
    "me_voy": _execute_me_voy,
    "llegue_a_casa": _execute_llegue_a_casa,
    "buenas_noches": _execute_buenas_noches,
    "modo_taller": _execute_modo_taller,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def home_routine(
    parameters: dict[str, Any] | None = None,
    response: Any = None,
    player: Any = None,
) -> str:
    params = parameters or {}
    action = str(params.get("action", "list")).lower().strip()
    routine_name = str(params.get("routine", params.get("name", ""))).lower().replace(" ", "_").replace("-", "_")
    confirm = bool(params.get("confirm", False))

    if action == "list" or (not routine_name and action not in _ROUTINE_EXECUTORS):
        lines = ["**Rutinas domésticas disponibles:**"]
        for key, r in _ROUTINES.items():
            lines.append(f"  • **{r['name']}** (`{key}`): {r['description']}")
        lines.append("\nUso: action=run, routine=<nombre> [, confirm=true para ejecutar acciones de dispositivos]")
        return "\n".join(lines)

    # Allow action to be the routine name directly (e.g. action="buenos_dias")
    if action in _ROUTINE_EXECUTORS and not routine_name:
        routine_name = action

    if routine_name not in _ROUTINE_EXECUTORS:
        available = ", ".join(_ROUTINES.keys())
        return (
            f"Rutina '{routine_name}' no reconocida. "
            f"Rutinas disponibles: {available}. "
            f"Uso: action=buenos_dias, action=me_voy, etc."
        )

    executor = _ROUTINE_EXECUTORS[routine_name]
    routine_def = _ROUTINES[routine_name]

    # Routines with device actions always require explicit confirmation
    if routine_def.get("device_confirm_required") and not confirm:
        return executor(confirm_devices=False)

    return executor(confirm_devices=confirm)
