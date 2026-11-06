"""E41 — Time-based alarm scheduling (clock alarms, not countdown timers).

Schedules alarms at specific times (e.g. 7:30, tomorrow 8:00) using
threading.Timer, plays a beep via ffplay or falls back to OS notification.
Alarms are persisted so the list survives restarts; they re-arm on the next
start if the fire time has not yet passed.

Distinct from timer.py (countdown from now). This module schedules wall-clock
alarms.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# State

_ALARMS: dict[str, threading.Timer] = {}  # id -> live Timer handle
_LOCK = threading.Lock()
_SYSTEM = platform.system()

_DIR_ENV = "JARVIS_ALARMS_DIR"
_REGISTRY_FILE = "alarms.json"


def _base_dir() -> Path:
    env = os.environ.get(_DIR_ENV, "")
    base = Path(env) if env else Path.home() / ".jarvis" / "alarms"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _registry_path() -> Path:
    return _base_dir() / _REGISTRY_FILE


def _load_registry() -> list[dict]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_registry(items: list[dict]) -> None:
    path = _registry_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Alarm parsing

_TIME_PATTERNS = [
    # "7:30", "07:30", "7:30 AM", "7:30 PM"
    re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)?", re.IGNORECASE),
    # "7h30", "7h"
    re.compile(r"(\d{1,2})h(\d{0,2})", re.IGNORECASE),
    # "7 AM", "9PM"
    re.compile(r"(\d{1,2})\s*(am|pm)", re.IGNORECASE),
]


def _parse_time_str(text: str) -> Optional[datetime]:
    """Parse a time string into the next occurrence of that time."""
    text = text.strip().lower()
    # Determine if tomorrow is requested
    base_date = datetime.now()
    is_tomorrow = "mañana" in text or "tomorrow" in text
    if is_tomorrow:
        base_date = base_date + timedelta(days=1)

    hour = minute = None
    am_pm = None

    for idx, pat in enumerate(_TIME_PATTERNS):
        m = pat.search(text)
        if m:
            groups = m.groups()
            hour = int(groups[0])
            if idx == 2:
                # "9 AM" pattern: groups = (hour, am_pm)
                minute = 0
                am_pm = groups[1].lower() if groups[1] else None
            else:
                # HH:MM and Hh patterns: groups = (hour, minute, [am_pm])
                raw_min = groups[1]
                if raw_min and raw_min.strip() and not raw_min.strip().isalpha():
                    minute = int(raw_min.strip())
                else:
                    minute = 0
                am_pm = groups[2].lower() if len(groups) > 2 and groups[2] else None
            break

    if hour is None:
        return None

    if am_pm == "pm" and hour < 12:
        hour += 12
    elif am_pm == "am" and hour == 12:
        hour = 0

    if hour > 23 or minute > 59:
        return None

    target = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # If target is in the past today (and not explicitly tomorrow), push to tomorrow
    if target <= datetime.now() and not is_tomorrow:
        target += timedelta(days=1)
    return target


def _fmt_time(dt: datetime) -> str:
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("hoy a las %H:%M")
    if dt.date() == (now + timedelta(days=1)).date():
        return dt.strftime("mañana a las %H:%M")
    return dt.strftime("%d/%m/%Y a las %H:%M")


# ---------------------------------------------------------------------------
# Alarm firing


def _find_ffplay() -> Optional[str]:
    for candidate in ["ffplay",
                       r"C:\ffmpeg\bin\ffplay.exe",
                       r"C:\Program Files\ffmpeg\bin\ffplay.exe",
                       r"C:\Tools\ffmpeg\bin\ffplay.exe"]:
        try:
            subprocess.run([candidate, "-version"],
                           capture_output=True, check=True, timeout=3)
            return candidate
        except Exception:
            pass
    return None


def _play_beep(label: str) -> None:
    ffplay = _find_ffplay()
    if ffplay:
        try:
            # Sine wave beep: 880Hz for 1.5s, three times
            for _ in range(3):
                subprocess.run(
                    [ffplay, "-nodisp", "-loglevel", "quiet", "-autoexit",
                     "-f", "lavfi", "-i", "sine=frequency=880:duration=0.5"],
                    timeout=3,
                )
                time.sleep(0.3)
            return
        except Exception:
            pass
    # Fallback: OS notification only
    try:
        if _SYSTEM == "Windows":
            import winsound  # type: ignore
            for _ in range(3):
                winsound.Beep(880, 500)
                time.sleep(0.3)
    except Exception:
        pass


def _notify_os(label: str) -> None:
    try:
        from plyer import notification  # type: ignore
        notification.notify(title="⏰ Alarma JARVIS", message=label, timeout=15)
    except Exception:
        pass


def _on_alarm_fire(alarm_id: str, label: str, player) -> None:
    with _LOCK:
        _ALARMS.pop(alarm_id, None)
    # Remove from registry
    items = _load_registry()
    items = [i for i in items if i.get("id") != alarm_id]
    _save_registry(items)

    # Sound + notification + TTS
    threading.Thread(target=_play_beep, args=(label,), daemon=True).start()
    _notify_os(label)
    if player is not None:
        try:
            player.speak(f"Alarma: {label}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Actions


def _action_set(time_str: str, label: str = "", player=None) -> str:
    if not time_str.strip():
        return "Especifica la hora de la alarma (ej: 7:30, mañana 8:00, 9 AM)."
    target = _parse_time_str(time_str)
    if target is None:
        return f"No entendí la hora '{time_str}'. Usa formato HH:MM, ej: 7:30, 8:00 AM, mañana 9h."

    alarm_id = str(uuid.uuid4())[:8]
    display_label = label.strip() or f"Alarma {alarm_id}"
    delay = (target - datetime.now()).total_seconds()
    if delay <= 0:
        return "La hora indicada ya ha pasado."

    handle = threading.Timer(delay, _on_alarm_fire, args=(alarm_id, display_label, player))
    handle.daemon = True
    handle.start()

    with _LOCK:
        _ALARMS[alarm_id] = handle

    # Persist
    items = _load_registry()
    items.append({
        "id": alarm_id,
        "label": display_label,
        "fire_at": target.isoformat(),
    })
    _save_registry(items)

    return f"Alarma '{display_label}' programada para {_fmt_time(target)} (en {_fmt_delay(delay)})."


def _fmt_delay(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s" if s else f"{m}m"
    return f"{s}s"


def _action_list() -> str:
    items = _load_registry()
    with _LOCK:
        active_ids = set(_ALARMS.keys())
    if not items:
        return "No hay alarmas programadas."
    lines = ["Alarmas programadas:"]
    now = datetime.now()
    for item in items:
        try:
            fire_at = datetime.fromisoformat(item["fire_at"])
        except Exception:
            fire_at = None
        label = item.get("label", item.get("id", "?"))
        is_active = item.get("id") in active_ids
        status = "activa" if is_active else "pendiente"
        time_str = _fmt_time(fire_at) if fire_at else "?"
        lines.append(f"  [{item.get('id', '?')}] {label} — {time_str} ({status})")
    return "\n".join(lines)


def _action_cancel(alarm_id: str = "", label_match: str = "") -> str:
    items = _load_registry()
    cancelled = []

    with _LOCK:
        if alarm_id:
            # Cancel by ID
            handle = _ALARMS.pop(alarm_id, None)
            if handle:
                handle.cancel()
                cancelled.append(alarm_id)
        elif label_match:
            # Cancel by label substring
            for item in items:
                if label_match.lower() in item.get("label", "").lower():
                    iid = item["id"]
                    handle = _ALARMS.pop(iid, None)
                    if handle:
                        handle.cancel()
                    cancelled.append(iid)
        else:
            # Cancel all
            for iid, handle in list(_ALARMS.items()):
                handle.cancel()
                _ALARMS.clear()
                cancelled = [iid for iid in _ALARMS]
            cancelled = list(_ALARMS.keys())
            _ALARMS.clear()

    if not cancelled and not alarm_id and not label_match:
        # cancel all branch
        cancelled = [i["id"] for i in items]
        with _LOCK:
            for h in _ALARMS.values():
                h.cancel()
            _ALARMS.clear()

    new_items = [i for i in items if i.get("id") not in cancelled]
    _save_registry(new_items)

    if not cancelled:
        return f"No se encontró ninguna alarma que cancelar."
    return f"Cancelada(s): {', '.join(cancelled)}."


def _action_status() -> str:
    with _LOCK:
        count = len(_ALARMS)
    items = _load_registry()
    if count == 0 and not items:
        return "No hay alarmas programadas."
    return f"{len(items)} alarma(s) registradas, {count} activa(s) en esta sesión."


# ---------------------------------------------------------------------------
# Entry point


def alarm_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    """NEST 68 E41 — Clock alarm scheduling (wall-clock, not countdown)."""
    # Feature-gated v2 uses LILITH as registry, Ubuntu as the ONLY announcer.
    # Existing local alarms remain untouched unless explicitly migrated.
    from actions.shared_alarm_v2 import is_enabled, shared_alarm_action
    if is_enabled():
        return shared_alarm_action(parameters, source="jarvis_windows")
    if not parameters:
        return _action_list()

    action = str(parameters.get("action", "set")).strip().lower()
    time_str = str(parameters.get("time") or parameters.get("hora") or "").strip()
    label = str(parameters.get("label") or parameters.get("nombre") or "").strip()
    alarm_id = str(parameters.get("id") or parameters.get("alarm_id") or "").strip()
    label_match = str(parameters.get("label_match") or "").strip()

    if action in ("set", "crear", "poner", "add", "new"):
        return _action_set(time_str, label=label, player=player)
    elif action in ("list", "mostrar", "ver", "show"):
        return _action_list()
    elif action in ("cancel", "cancelar", "borrar", "delete", "remove"):
        return _action_cancel(alarm_id=alarm_id, label_match=label_match)
    elif action == "status":
        return _action_status()
    else:
        return f"Acción '{action}' no reconocida. Usa: set, list, cancel, status."
