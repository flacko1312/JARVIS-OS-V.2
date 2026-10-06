"""Shared scheduling semantics used at every physical side-effect boundary."""
from __future__ import annotations

import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_SPANISH_NUMBERS = {
    "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12,
}
_LOCAL_TIMEZONE_ALIASES = {
    "madrid", "hora de madrid", "zona horaria de madrid", "mi zona horaria",
    "hora local", "local timezone", "my timezone",
}


def normalized_turn_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or "").lower())
    return " ".join(
        "".join(ch for ch in decomposed if not unicodedata.combining(ch)).split()
    )


def schedule_semantics(text: str) -> str:
    """Return the mutually exclusive immediate/one-shot/recurring route."""
    value = normalized_turn_text(text)
    patterns = (
        r"\btodos? los dias\b", r"\bcada dia\b", r"\bdiariamente\b",
        r"\bcada (?:manana|noche|semana)\b",
        r"\btodos? los (?:lunes|martes|miercoles|jueves|viernes|sabados|domingos)\b",
        r"\bcada \d+ (?:horas?|dias?)\b", r"\b(?:rutina|automatiza(?:r|cion)?)\b",
        r"\ba partir de ahora\b", r"\bevery day\b", r"\bdaily\b",
        r"\bevery (?:morning|night|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\bevery \d+ (?:hours?|days?)\b", r"\b(?:routine|automate)\b",
        r"\bfrom now on\b",
    )
    if any(re.search(pattern, value) for pattern in patterns):
        return "recurring"
    one_shot_patterns = (
        r"\b(?:recuerdame|remind me)\b",
        r"\b(?:hoy|manana|tonight|tomorrow)\b.*\b(?:a las?|at)\b",
        r"\b(?:el )?(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b.*\ba las?\b",
        r"\bdentro de \d+ (?:minutos?|horas?|dias?)\b",
        r"\bin \d+ (?:minutes?|hours?|days?)\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    )
    if any(re.search(pattern, value) for pattern in one_shot_patterns):
        return "one_shot"
    return "immediate"


def daily_time_from_text(text: str) -> tuple[int, int] | None:
    """Parse an unambiguous daily wall-clock time from Spanish or 24-hour text."""
    value = normalized_turn_text(text)
    numeric = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", value)
    if numeric:
        return int(numeric.group(1)), int(numeric.group(2))
    am_pm = re.search(r"\b(1[0-2]|0?[1-9])\s*(?:h\s*)?(am|pm)\b", value)
    if am_pm:
        return int(am_pm.group(1)) % 12 + (12 if am_pm.group(2) == "pm" else 0), 0
    words = "|".join(_SPANISH_NUMBERS)
    spoken = re.search(rf"\b(?:a las|a la)\s+(\d{{1,2}}|{words})\b", value)
    if not spoken:
        return None
    raw_hour = spoken.group(1)
    hour = int(raw_hour) if raw_hour.isdigit() else _SPANISH_NUMBERS[raw_hour]
    if not 1 <= hour <= 23:
        return None
    period = re.search(r"\b(?:de la )?(manana|tarde|noche)\b", value)
    if hour <= 12 and period is None:
        return None
    if period and period.group(1) in {"tarde", "noche"} and hour < 12:
        hour += 12
    if period and period.group(1) == "manana" and hour == 12:
        hour = 0
    return hour, 0


def normalize_timezone(value: str | None, *, default: str = "Europe/Madrid") -> str | None:
    """Resolve friendly local timezone references while preserving valid IANA names."""
    raw = str(value or "").strip()
    normalized = normalized_turn_text(raw)
    if not raw or normalized in _LOCAL_TIMEZONE_ALIASES:
        return default
    try:
        ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        return None
    return raw
