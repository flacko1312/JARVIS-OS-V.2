"""Internet radio streaming for JARVIS.

Plays internet radio streams using a background subprocess.
On Windows: uses ffplay (if available) or opens URL in default media app.
On Linux/Ubuntu: uses ffplay (from ffmpeg package).

Supported actions:
  play    — start streaming a station (stops any current stream first)
  stop    — stop the current stream
  status  — report what is currently playing
  list    — list available preset stations
  add     — add a custom station (saved in registry)
  remove  — remove a saved station
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

_SYSTEM = platform.system()
_LOCK = threading.Lock()
_CURRENT_PROC: Optional[subprocess.Popen] = None
_CURRENT_STATION: str = ""
_CURRENT_NAME: str = ""

# Well-known Spanish internet radio streams
_BUILTIN_STATIONS: dict[str, tuple[str, str]] = {
    "radio1":    ("RTVE Radio 1",        "https://rne.rtveradio.cds.amagi.tv/live/rtveradioe1/playlist.m3u8"),
    "radio2":    ("RTVE Radio Nacional 2","https://rne.rtveradio.cds.amagi.tv/live/rtveradioe2/playlist.m3u8"),
    "radio3":    ("RTVE Radio 3",        "https://rne.rtveradio.cds.amagi.tv/live/rtveradioe3/playlist.m3u8"),
    "ser":       ("Cadena SER",          "https://playerservices.streamtheworld.com/api/livestream-redirect/CADENA_SER_SC"),
    "cope":      ("COPE",                "https://playerservices.streamtheworld.com/api/livestream-redirect/COPE_SC"),
    "onda_cero": ("Onda Cero",           "https://playerservices.streamtheworld.com/api/livestream-redirect/ONDACERO_SC"),
    "los40":     ("Los 40",              "https://playerservices.streamtheworld.com/api/livestream-redirect/LOS40_SC"),
    "rock_fm":   ("Rock FM",             "https://playerservices.streamtheworld.com/api/livestream-redirect/ROCK_FM_SC"),
    "bbc1":      ("BBC Radio 1",         "https://stream.live.vc.bbcmedia.co.uk/bbc_radio_one"),
    "bbc6":      ("BBC Radio 6 Music",   "https://stream.live.vc.bbcmedia.co.uk/bbc_6music"),
}


def _registry_path() -> Path:
    base = Path(os.environ.get("JARVIS_RADIO_DIR", Path.home() / ".jarvis" / "radio"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "stations.json"


def _load_custom() -> dict[str, tuple[str, str]]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: (v["name"], v["url"]) for k, v in data.items()}
    except Exception:
        return {}


def _save_custom(stations: dict[str, tuple[str, str]]) -> None:
    path = _registry_path()
    data = {k: {"name": v[0], "url": v[1]} for k, v in stations.items()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _all_stations() -> dict[str, tuple[str, str]]:
    combined = dict(_BUILTIN_STATIONS)
    combined.update(_load_custom())
    return combined


def _resolve_station(query: str) -> tuple[str, str, str]:
    """Return (key, name, url) for a station key, name fragment, or direct URL."""
    query = query.strip()
    if not query:
        raise ValueError("Especifica la emisora o URL a reproducir.")

    # Direct URL
    if query.startswith("http"):
        return "custom", query, query

    stations = _all_stations()
    q = query.lower()

    # Exact key match
    if q in stations:
        name, url = stations[q]
        return q, name, url

    # Fuzzy name match
    for key, (name, url) in stations.items():
        if q in name.lower() or q in key.lower():
            return key, name, url

    raise ValueError(
        f"No encontré la emisora '{query}'. "
        "Usa 'radio list' para ver las disponibles o proporciona una URL directa."
    )


def _find_ffplay() -> Optional[str]:
    # Look for ffplay (bundled with ffmpeg)
    for candidate in ["ffplay", "ffplay.exe"]:
        path = shutil.which(candidate)
        if path:
            return path
    # Common Windows paths
    if _SYSTEM == "Windows":
        for base in [r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin", r"C:\Tools\ffmpeg\bin"]:
            p = Path(base) / "ffplay.exe"
            if p.exists():
                return str(p)
    return None


def _stop_current() -> str:
    global _CURRENT_PROC, _CURRENT_STATION, _CURRENT_NAME
    with _LOCK:
        if _CURRENT_PROC is None:
            return ""
        name = _CURRENT_NAME
        try:
            _CURRENT_PROC.terminate()
            _CURRENT_PROC.wait(timeout=3)
        except Exception:
            try:
                _CURRENT_PROC.kill()
            except Exception:
                pass
        _CURRENT_PROC = None
        _CURRENT_STATION = ""
        _CURRENT_NAME = ""
        return name


def _play_url(url: str, name: str) -> str:
    global _CURRENT_PROC, _CURRENT_STATION, _CURRENT_NAME

    _stop_current()

    ffplay = _find_ffplay()

    if ffplay:
        cmd = [ffplay, "-nodisp", "-loglevel", "quiet", "-i", url]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            with _LOCK:
                _CURRENT_PROC = proc
                _CURRENT_STATION = url
                _CURRENT_NAME = name
            return f"Reproduciendo {name}."
        except Exception as exc:
            pass  # fall through to browser

    # Fallback: open in default OS media player / browser
    try:
        if _SYSTEM == "Windows":
            os.startfile(url)  # type: ignore[attr-defined]
        elif _SYSTEM == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        with _LOCK:
            _CURRENT_PROC = None  # no process to track
            _CURRENT_STATION = url
            _CURRENT_NAME = name
        return f"Abriendo {name} en el reproductor del sistema."
    except Exception as exc:
        return f"No se pudo reproducir {name}: {exc}"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _action_play(query: str) -> str:
    if not query:
        return "Especifica la emisora. Ejemplo: 'pon Radio 1' o 'radio ser'."
    try:
        key, name, url = _resolve_station(query)
    except ValueError as exc:
        return str(exc)
    return _play_url(url, name)


def _action_stop() -> str:
    stopped = _stop_current()
    if stopped:
        return f"{stopped} detenida."
    return "No hay ninguna emisora reproduciéndose."


def _action_status() -> str:
    with _LOCK:
        if not _CURRENT_STATION:
            return "No hay radio reproduciéndose."
        alive = _CURRENT_PROC is not None and _CURRENT_PROC.poll() is None
        status = "reproduciendo" if alive else "abierta en reproductor del sistema"
        return f"Emisora {status}: {_CURRENT_NAME} ({_CURRENT_STATION})"


def _action_list() -> str:
    stations = _all_stations()
    lines = ["Emisoras disponibles:"]
    for key, (name, url) in sorted(stations.items()):
        lines.append(f"  {key}: {name}")
    return "\n".join(lines)


def _action_add(key: str, name: str, url: str) -> str:
    if not key or not url:
        return "Especifica key y url para añadir una emisora."
    if not url.startswith("http"):
        return "La URL debe comenzar con http(s)."
    if key in _BUILTIN_STATIONS:
        return f"'{key}' es una emisora integrada y no puede sobreescribirse. Elige otro nombre."
    custom = _load_custom()
    custom[key.lower()] = (name or key, url)
    _save_custom(custom)
    return f"Emisora '{name or key}' guardada con clave '{key.lower()}'."


def _action_remove(key: str) -> str:
    if not key:
        return "Especifica la clave de la emisora a eliminar."
    if key in _BUILTIN_STATIONS:
        return f"'{key}' es una emisora integrada y no puede eliminarse."
    custom = _load_custom()
    if key not in custom:
        return f"No encontré la emisora '{key}' en tus estaciones guardadas."
    del custom[key]
    _save_custom(custom)
    return f"Emisora '{key}' eliminada."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def radio_control(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if action == "play":
        query = params.get("station", "") or params.get("query", "") or params.get("text", "")
        return _action_play(query)

    if action == "stop":
        return _action_stop()

    if action == "status":
        return _action_status()

    if action == "list":
        return _action_list()

    if action == "add":
        return _action_add(
            key=params.get("key", ""),
            name=params.get("name", ""),
            url=params.get("url", ""),
        )

    if action == "remove":
        return _action_remove(key=params.get("key", ""))

    return (
        f"Acción '{action}' no reconocida. "
        "Acciones: play, stop, status, list, add, remove."
    )
