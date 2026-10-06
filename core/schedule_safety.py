"""Shared scheduling semantics used at every physical side-effect boundary."""
from __future__ import annotations

import re
import unicodedata


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
