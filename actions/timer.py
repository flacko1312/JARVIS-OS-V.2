"""
Timer tool — in-process countdown timers for JARVIS.

Timers count down from a duration (e.g. 5 minutos, 30 segundos).
On expiry they speak through the live session and optionally send an OS notification.
Registry is persisted to disk so the list survives tool calls; the threading.Timer
handles are re-created only while the process is running.
"""
import json
import os
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TIMERS: dict[str, threading.Timer] = {}  # id -> live Timer handle
_LOCK = threading.Lock()

_SPANISH_AMOUNTS: dict[str, int] = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "noventa": 90,
}


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _registry_path() -> Path:
    d = Path(os.environ.get("JARVIS_TIMER_DIR", "").strip() or Path.home() / ".jarvis" / "timers")
    d.mkdir(parents=True, exist_ok=True)
    return d / "registry.json"


def _load_registry() -> list[dict]:
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _save_registry(items: list[dict]) -> None:
    path = _registry_path()
    payload = json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(prefix="timers-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass


def _active_registry() -> list[dict]:
    now = datetime.now(timezone.utc)
    active = [
        item for item in _load_registry()
        if _fires_at(item) is not None and _fires_at(item) > now
    ]
    _save_registry(active)
    return active


def _fires_at(item: dict) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(item["fires_at"]))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None


def _notify_os(label: str) -> None:
    try:
        from plyer import notification
        notification.notify(title="⏱ Temporizador JARVIS", message=label, timeout=10)
        return
    except Exception:
        pass
    try:
        import winsound
        for freq in [880, 1100, 880]:
            winsound.Beep(freq, 200)
            import time; time.sleep(0.1)
    except Exception:
        pass


def _on_timer_fire(timer_id: str, label: str, player) -> None:
    with _LOCK:
        _TIMERS.pop(timer_id, None)
    items = _load_registry()
    _save_registry([item for item in items if item.get("id") != timer_id])
    text = f"Temporizador listo: {label}"
    # The Windows OS notification can block briefly; say the expiry first
    # so a slow notification backend never delays JARVIS's spoken alert.
    if player is not None:
        directive = (
            "[INTERNAL TIMER FIRED] Di al usuario en español, con un tono amistoso, "
            f"que el temporizador ha terminado. Mensaje: {json.dumps(text, ensure_ascii=False)}"
        )
        try:
            player.speak(directive)
        except Exception:
            pass
    # Retain the OS fallback; it runs after the spoken announcement.
    _notify_os(label)


def _parse_duration(text: str) -> tuple[int | None, str | None]:
    """Parse Spanish duration expression into total seconds. Returns (seconds, error)."""
    import re
    value = " ".join(text.lower().strip().split())
    value = (value
             .replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u"))

    total = 0
    found = False

    # e.g. "1 hora 30 minutos" or "2 horas y 30 segundos"
    patterns = [
        (r"(\d+|" + "|".join(_SPANISH_AMOUNTS) + r")\s*hora[s]?", 3600),
        (r"(\d+|" + "|".join(_SPANISH_AMOUNTS) + r")\s*minuto[s]?", 60),
        (r"(\d+|" + "|".join(_SPANISH_AMOUNTS) + r")\s*segundo[s]?", 1),
    ]
    for pattern, factor in patterns:
        m = re.search(pattern, value)
        if m:
            raw = m.group(1)
            amount = int(raw) if raw.isdigit() else _SPANISH_AMOUNTS.get(raw, 0)
            total += amount * factor
            found = True

    if not found:
        # Try bare number (assume minutes)
        m = re.match(r"^\s*(\d+)\s*$", value)
        if m:
            total = int(m.group(1)) * 60
            found = True

    if not found or total <= 0:
        return None, (
            "No he entendido la duración. Usa por ejemplo: "
            "\"5 minutos\", \"30 segundos\", \"1 hora 30 minutos\"."
        )
    if total > 86400:
        return None, "El temporizador no puede superar 24 horas."
    return total, None


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0 segundos"
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h:
        parts.append(f"{h} hora{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minuto{'s' if m != 1 else ''}")
    if s:
        parts.append(f"{s} segundo{'s' if s != 1 else ''}")
    return " y ".join(parts[:2]) if len(parts) > 1 else parts[0]


def _remaining_str(item: dict) -> str:
    fires = _fires_at(item)
    if fires is None:
        return "desconocido"
    remaining = int((fires - datetime.now(timezone.utc)).total_seconds())
    if remaining <= 0:
        return "expirado"
    return _format_duration(remaining)


def timer(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    action = str(parameters.get("action") or "create").strip().lower()
    items = _active_registry()

    # --- LIST ---
    if action == "list":
        active = [item for item in items if item.get("id") in _TIMERS or _fires_at(item) is not None]
        if not active:
            return "No hay temporizadores activos."
        lines = ["Temporizadores activos:"]
        for item in sorted(active, key=lambda i: str(_fires_at(i) or "")):
            tid = item.get("id", "?")
            label = item.get("label", "Temporizador")
            lines.append(f"- {tid}: {label} — quedan {_remaining_str(item)}")
        return "\n".join(lines)

    # --- CANCEL ---
    if action in {"cancel", "delete", "stop"}:
        timer_id = str(parameters.get("id") or parameters.get("timer_id") or "").strip()
        if not timer_id:
            # Cancel all if no id given
            cancelled = 0
            with _LOCK:
                for tid, handle in list(_TIMERS.items()):
                    handle.cancel()
                    _TIMERS.pop(tid, None)
                    cancelled += 1
            _save_registry([])
            if cancelled:
                return f"Cancelados {cancelled} temporizador{'es' if cancelled != 1 else ''}."
            return "No había temporizadores activos para cancelar."
        item = next((i for i in items if i.get("id") == timer_id), None)
        if item is None:
            return "No encuentro ese temporizador."
        with _LOCK:
            handle = _TIMERS.pop(timer_id, None)
            if handle:
                handle.cancel()
        _save_registry([i for i in items if i.get("id") != timer_id])
        label = item.get("label", "Temporizador")
        return f"Temporizador «{label}» cancelado."

    # --- CREATE ---
    if action not in {"create", "set", "start"}:
        return f"Acción de temporizador no compatible: {action}. Usa create, list o cancel."

    duration_text = str(
        parameters.get("duration") or parameters.get("text") or parameters.get("time") or ""
    ).strip()
    if not duration_text:
        return "Necesito una duración para el temporizador (p.ej. «5 minutos»)."

    seconds, error = _parse_duration(duration_text)
    if error:
        return error
    assert seconds is not None

    label = str(parameters.get("label") or parameters.get("message") or "").strip()
    if not label:
        label = _format_duration(seconds)

    # Dedup: same label within 10s tolerance
    duplicate = next(
        (i for i in items
         if i.get("label", "").lower() == label.lower()
         and abs(int((_fires_at(i) or datetime.now(timezone.utc)) - datetime.now(timezone.utc)).total_seconds() - seconds) < 10),
        None,
    )
    if duplicate:
        return f"Ya hay un temporizador similar activo: {duplicate.get('id')}."

    timer_id = f"tmr_{uuid.uuid4().hex[:10]}"
    fires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)

    record: dict = {
        "id": timer_id,
        "label": label,
        "duration_seconds": seconds,
        "fires_at": fires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    handle = threading.Timer(seconds, _on_timer_fire, args=(timer_id, label, player))
    handle.daemon = True
    with _LOCK:
        _TIMERS[timer_id] = handle
    handle.start()

    items.append(record)
    _save_registry(items)

    return f"Temporizador de {_format_duration(seconds)} iniciado (ID: {timer_id})."
