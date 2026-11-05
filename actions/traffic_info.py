"""Traffic and routing information for JARVIS.

Uses OpenRouteService (ORS) for route times and distances, and Nominatim
(OpenStreetMap) for free geocoding. No API key is required for Nominatim;
ORS needs a free-tier key (env var ORS_API_KEY or keychain entry).

Supported actions:
  route     — time and distance between two addresses (requires ORS key)
  commute   — quick check using saved home/work addresses
  setup     — save home and/or work address for commute shortcuts
  addresses — show saved home/work addresses
  status    — connection state

If ORS_API_KEY is not configured, the tool returns a helpful setup message
with instructions to get a free key at openrouteservice.org.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_ORS_KEY_SECRET = "ors_api_key"
_HOME_SECRET = "traffic_home_address"
_WORK_SECRET = "traffic_work_address"

_ORS_ROUTE_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

_API_CACHE: dict[str, str] = {}
_CACHE_LOCK = threading.Lock()

# Nominatim requires a User-Agent per ToS
_UA = "JARVIS-AURORA/1.0 (contact: jarvis-local)"


class TrafficError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Secret-store helpers
# ---------------------------------------------------------------------------

def _secret_store():
    from core.secret_store import get_secret_store
    return get_secret_store()


def _get_ors_key() -> str:
    with _CACHE_LOCK:
        cached = _API_CACHE.get(_ORS_KEY_SECRET, "")
    if cached:
        return cached
    key = os.environ.get("ORS_API_KEY", "").strip()
    if not key:
        try:
            key = _secret_store().get(_ORS_KEY_SECRET) or ""
        except Exception:
            key = ""
    if key:
        with _CACHE_LOCK:
            _API_CACHE[_ORS_KEY_SECRET] = key
    return key


def _save_ors_key(key: str) -> None:
    with _CACHE_LOCK:
        _API_CACHE[_ORS_KEY_SECRET] = key
    try:
        _secret_store().set(_ORS_KEY_SECRET, key)
    except Exception:
        pass


def _get_address(key: str) -> str:
    env_map = {_HOME_SECRET: "JARVIS_HOME_ADDRESS", _WORK_SECRET: "JARVIS_WORK_ADDRESS"}
    value = os.environ.get(env_map.get(key, ""), "").strip()
    if value:
        return value
    try:
        return _secret_store().get(key) or ""
    except Exception:
        return ""


def _save_address(key: str, value: str) -> None:
    try:
        _secret_store().set(key, value)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Nominatim geocoding (free, no key)
# ---------------------------------------------------------------------------

def _geocode(address: str) -> tuple[float, float]:
    """Return (longitude, latitude) for an address string."""
    try:
        import requests
    except ImportError as exc:
        raise TrafficError("requests no está disponible. Instala: pip install requests") from exc

    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    headers = {"User-Agent": _UA, "Accept-Language": "es,en"}

    try:
        resp = requests.get(_NOMINATIM_URL, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise TrafficError(f"Error de geocodificación para '{address}': {exc}") from exc

    if not data:
        raise TrafficError(
            f"No encontré la ubicación '{address}'. "
            "Prueba con un nombre más específico (ciudad, país)."
        )

    item = data[0]
    lon = float(item["lon"])
    lat = float(item["lat"])
    return lon, lat


# ---------------------------------------------------------------------------
# ORS routing
# ---------------------------------------------------------------------------

def _ors_route(
    origin_coords: tuple[float, float],
    dest_coords: tuple[float, float],
    api_key: str,
) -> dict[str, Any]:
    """Call ORS directions API and return route summary."""
    try:
        import requests
    except ImportError as exc:
        raise TrafficError("requests no está disponible. Instala: pip install requests") from exc

    body = {
        "coordinates": [list(origin_coords), list(dest_coords)],
    }
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json, application/geo+json",
        "User-Agent": _UA,
    }

    try:
        resp = requests.post(_ORS_ROUTE_URL, json=body, headers=headers, timeout=10)
    except Exception as exc:
        raise TrafficError(f"No se pudo conectar con OpenRouteService: {exc}") from exc

    if resp.status_code == 403:
        raise TrafficError(
            "La clave de API de OpenRouteService no es válida o se superó la cuota. "
            "Verifica ORS_API_KEY."
        )
    if resp.status_code == 404:
        raise TrafficError("No se encontró ruta entre esos puntos.")

    try:
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise TrafficError(f"Respuesta inesperada de OpenRouteService: {exc}") from exc

    try:
        summary = data["routes"][0]["summary"]
        return {
            "distance_m": summary["distance"],
            "duration_s": summary["duration"],
        }
    except (KeyError, IndexError) as exc:
        raise TrafficError(f"Formato de respuesta inesperado de ORS: {exc}") from exc


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours} h"
    return f"{hours} h {mins} min"


def _fmt_distance(meters: float) -> str:
    if meters < 1000:
        return f"{int(meters)} m"
    return f"{meters / 1000:.1f} km"


def _no_key_message() -> str:
    return (
        "El módulo de tráfico necesita una clave API de OpenRouteService (gratuita). "
        "1) Regístrate en openrouteservice.org. "
        "2) Copia tu API key. "
        "3) Dile a JARVIS: 'configura tráfico con la clave XXXX'. "
        "O bien, establece la variable de entorno ORS_API_KEY."
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _action_status() -> str:
    key = _get_ors_key()
    home = _get_address(_HOME_SECRET)
    work = _get_address(_WORK_SECRET)
    parts = []
    if key:
        parts.append(f"OpenRouteService: configurado (clave termina en ...{key[-4:]}).")
    else:
        parts.append("OpenRouteService: NO configurado.")
    if home:
        parts.append(f"Casa: {home}")
    else:
        parts.append("Casa: no guardada.")
    if work:
        parts.append(f"Trabajo: {work}")
    else:
        parts.append("Trabajo: no guardado.")
    return " ".join(parts)


def _action_setup(home: str = "", work: str = "", api_key: str = "") -> str:
    messages = []
    if api_key:
        _save_ors_key(api_key.strip())
        messages.append(f"Clave API guardada (termina en ...{api_key.strip()[-4:]}).")
    if home:
        _save_address(_HOME_SECRET, home.strip())
        messages.append(f"Dirección de casa guardada: {home.strip()}.")
    if work:
        _save_address(_WORK_SECRET, work.strip())
        messages.append(f"Dirección de trabajo guardada: {work.strip()}.")
    if not messages:
        return (
            "Especifica qué configurar: "
            "api_key (clave ORS), home (dirección de casa) o work (dirección de trabajo)."
        )
    return " ".join(messages)


def _action_addresses() -> str:
    home = _get_address(_HOME_SECRET)
    work = _get_address(_WORK_SECRET)
    parts = []
    parts.append(f"Casa: {home or '(no guardada)'}")
    parts.append(f"Trabajo: {work or '(no guardado)'}")
    return ". ".join(parts) + "."


def _action_route(origin: str, destination: str) -> str:
    if not origin or not destination:
        return "Necesito origen y destino para calcular la ruta."

    api_key = _get_ors_key()
    if not api_key:
        return _no_key_message()

    origin_coords = _geocode(origin)
    dest_coords = _geocode(destination)
    summary = _ors_route(origin_coords, dest_coords, api_key)

    duration = _fmt_duration(summary["duration_s"])
    distance = _fmt_distance(summary["distance_m"])
    return (
        f"De '{origin}' a '{destination}': "
        f"{duration} en coche, {distance}."
    )


def _action_commute(direction: str = "to_work") -> str:
    home = _get_address(_HOME_SECRET)
    work = _get_address(_WORK_SECRET)

    if not home:
        return "No tengo guardada tu dirección de casa. Dile a JARVIS: 'configura tráfico casa [dirección]'."
    if not work:
        return "No tengo guardada tu dirección de trabajo. Dile a JARVIS: 'configura tráfico trabajo [dirección]'."

    if direction in ("to_work", "ida", "al trabajo"):
        return _action_route(home, work)
    elif direction in ("to_home", "vuelta", "a casa", "de vuelta"):
        return _action_route(work, home)
    else:
        # Return both
        to_work = _action_route(home, work)
        to_home = _action_route(work, home)
        return f"Ida — {to_work} Vuelta — {to_home}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def traffic_info(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "route").lower().strip()

    try:
        if action == "status":
            return _action_status()

        if action == "setup":
            return _action_setup(
                home=params.get("home", ""),
                work=params.get("work", ""),
                api_key=params.get("api_key", ""),
            )

        if action == "addresses":
            return _action_addresses()

        if action in ("commute", "trayecto"):
            return _action_commute(direction=params.get("direction", "to_work"))

        if action == "route":
            origin = params.get("origin", "") or params.get("from", "")
            destination = params.get("destination", "") or params.get("to", "")
            return _action_route(origin=origin, destination=destination)

        return (
            f"Acción '{action}' no reconocida. "
            "Acciones disponibles: route, commute, setup, addresses, status."
        )

    except TrafficError as exc:
        return str(exc)
    except Exception as exc:
        from core.error_reporting import error_report
        error_report(exc, context="traffic_info")
        return f"Error inesperado en traffic_info: {exc}"
