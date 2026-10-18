"""Shared scheduling semantics used at every physical side-effect boundary."""
from __future__ import annotations

import re
import unicodedata
from core.date_time_authority import normalize_timezone


_SPANISH_NUMBERS = {
    "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12,
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


def _resolve_period(value: str) -> str | None:
    """Extract the day-period from normalised text (manana/tarde/noche/mediodia/am/pm)."""
    pm = re.search(r"\bpm\b", value)
    if pm:
        return "pm"
    am = re.search(r"\bam\b", value)
    if am:
        return "am"
    sp = re.search(r"\b(?:de(?:l|\s+la)\s+)?(manana|tarde|noche|mediodia)\b", value)
    if sp:
        return sp.group(1)
    return None


def _apply_period(hour: int, period: str | None) -> int | None:
    """Convert 1-12h + period to 0-23h.  Returns None when ambiguous."""
    if period is None:
        return hour if hour > 12 else None
    if period in ("am", "manana"):
        return hour % 12          # 12 AM / 12 de la mañana → 0
    if period == "mediodia":
        return 12
    if period in ("pm", "tarde", "noche"):
        if period == "noche" and 1 <= hour <= 5:
            return None            # "3 de la noche" is too ambiguous
        return hour if hour >= 13 else hour % 12 + 12  # already 24h keeps; else +12
    return hour if hour > 12 else None


def daily_time_from_text(text: str) -> tuple[int, int] | None:
    """Parse an unambiguous daily wall-clock time from Spanish or 24-hour text."""
    value = normalized_turn_text(text)
    period = _resolve_period(value)

    # "12 de la noche" / "12 del mediodía" — special-cased before numeric/spoken
    if period == "mediodia":
        return 12, 0
    midnight = re.search(r"\b12\s*(?:de la\s+)?noche\b", value)
    if midnight:
        return 0, 0

    # HH:MM or HH.MM (e.g. "9:30 de la noche", "21:30", "9:30 PM")
    numeric = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", value)
    if numeric:
        hour, minute = int(numeric.group(1)), int(numeric.group(2))
        if hour > 12:
            return hour, minute    # already unambiguous 24h
        resolved = _apply_period(hour, period)
        if resolved is None:
            return None
        return resolved, minute

    # "9 AM", "9 PM", "9h pm"
    am_pm = re.search(r"\b(1[0-2]|0?[1-9])\s*(?:h\s*)?(am|pm)\b", value)
    if am_pm:
        hour = int(am_pm.group(1))
        p = am_pm.group(2)
        return _apply_period(hour, p), 0

    # Spoken Spanish: "a las nueve de la noche", "a la una de la tarde"
    words = "|".join(_SPANISH_NUMBERS)
    spoken = re.search(
        rf"\b(?:(?:a las|a la)\s+)?(\d{{1,2}}|{words})\s*(?:h\s*)?"
        rf"(?:de la\s+)?(manana|tarde|noche)\b",
        value,
    )
    if not spoken:
        spoken = re.search(rf"\b(?:a las|a la)\s+(\d{{1,2}}|{words})\b", value)
    if not spoken:
        return None
    raw_hour = spoken.group(1)
    hour = int(raw_hour) if raw_hour.isdigit() else _SPANISH_NUMBERS[raw_hour]
    if not 1 <= hour <= 23:
        return None
    spoken_period = spoken.group(2) if spoken.lastindex and spoken.lastindex >= 2 else None
    effective_period = spoken_period or period
    resolved = _apply_period(hour, effective_period)
    if resolved is None:
        return None
    return resolved, 0


def user_confirmed(text: str) -> bool | None:
    """Detect explicit user confirmation or rejection in normalised text.

    Returns True for affirmative, False for negative, None for ambiguous.
    """
    value = normalized_turn_text(text)
    if not value:
        return None
    deny = re.search(
        r"\b(?:no|cancela|cancelar|cancelalo|anula|anular|olvidalo|dejalo|nada"
        r"|olvida|mejor no|no lo hagas|no quiero|cancel|never ?mind|don'?t|stop)\b",
        value,
    )
    if deny:
        return False
    confirm = re.search(
        r"\b(?:si|sí|ok|okey|vale|venga|dale|confirmo|confirmado|hazlo|adelante|perfecto"
        r"|correcto|exacto|claro|por supuesto|yes|yeah|confirm|go ahead|do it|proceed)\b",
        value,
    )
    if confirm:
        return True
    return None
