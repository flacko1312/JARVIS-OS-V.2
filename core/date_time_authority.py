"""Authoritative, read-only host date/time and calendar services for JARVIS."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Europe/Madrid"

_WINDOWS_TO_IANA = {
    "romance standard time": "Europe/Madrid",
    "central europe standard time": "Europe/Budapest",
    "w. europe standard time": "Europe/Berlin",
    "gmt standard time": "Europe/London",
    "greenwich standard time": "Atlantic/Reykjavik",
    "utc": "UTC",
    "eastern standard time": "America/New_York",
    "central standard time": "America/Chicago",
    "mountain standard time": "America/Denver",
    "pacific standard time": "America/Los_Angeles",
}

_TIMEZONE_ALIASES = {
    "madrid": DEFAULT_TIMEZONE,
    "hora de madrid": DEFAULT_TIMEZONE,
    "zona horaria de madrid": DEFAULT_TIMEZONE,
    "hora local": DEFAULT_TIMEZONE,
    "mi zona horaria": DEFAULT_TIMEZONE,
    "local timezone": DEFAULT_TIMEZONE,
    "my timezone": DEFAULT_TIMEZONE,
    "cet": DEFAULT_TIMEZONE,
    "cest": DEFAULT_TIMEZONE,
}

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _normalized(text: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or "").casefold())
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


def windows_timezone_name() -> str | None:
    """Read the Windows timezone identifier. This never changes host settings."""
    if platform.system() != "Windows":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "TimeZoneKeyName")
        if str(value).strip():
            return str(value).strip()
    except (ImportError, OSError):
        pass
    try:
        result = subprocess.run(
            ["tzutil", "/g"], capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def normalize_timezone(
    value: str | None,
    *,
    default: str = DEFAULT_TIMEZONE,
    os_name: str | None = None,
    windows_name: str | None = None,
) -> str | None:
    """Return a canonical IANA timezone, including Windows and CET/CEST aliases."""
    raw = str(value or "").strip()
    normalized = _normalized(raw)
    if normalized in _TIMEZONE_ALIASES:
        return _TIMEZONE_ALIASES[normalized]
    if raw:
        windows_match = _WINDOWS_TO_IANA.get(normalized)
        if windows_match:
            return windows_match
        try:
            ZoneInfo(raw)
        except ZoneInfoNotFoundError:
            return None
        return raw

    configured = os.getenv("JARVIS_TIMEZONE", "").strip()
    if configured:
        resolved = normalize_timezone(configured, default=default, os_name=os_name, windows_name=windows_name)
        if resolved:
            return resolved
    if (os_name or platform.system()) == "Windows":
        host_name = windows_name if windows_name is not None else windows_timezone_name()
        if host_name:
            resolved = _WINDOWS_TO_IANA.get(_normalized(host_name))
            if resolved:
                return resolved
    try:
        ZoneInfo(default)
    except ZoneInfoNotFoundError:
        return None
    return default


def relative_date(reference: datetime, phrase: str) -> date:
    value = _normalized(phrase)
    if "pasado manana" in value or "day after tomorrow" in value:
        return (reference + timedelta(days=2)).date()
    if "manana" in value or "tomorrow" in value:
        return (reference + timedelta(days=1)).date()
    return reference.date()


def localize_wall_time(day: date, hour: int, minute: int, timezone_name: str) -> tuple[datetime | None, str | None]:
    """Localize a wall time and reject nonexistent or duplicated DST instants."""
    zone = ZoneInfo(timezone_name)
    naive = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    candidates: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive and candidate.utcoffset() == round_trip.utcoffset():
            candidates.append(candidate)
    unique = {candidate.utcoffset(): candidate for candidate in candidates}
    if not unique:
        return None, "Esa hora local no existe por el cambio de horario de verano."
    if len(unique) > 1:
        return None, "Esa hora local ocurre dos veces por el cambio de horario. Indica CET o CEST explícitamente."
    return next(iter(unique.values())), None


@dataclass(frozen=True)
class AuthoritativeDateTime:
    instant: datetime
    timezone: str

    @property
    def abbreviation(self) -> str:
        return self.instant.tzname() or self.timezone


class DateTimeAuthority:
    """Read-only clock with an injectable UTC source for deterministic tests."""

    def __init__(
        self,
        *,
        timezone_name: str | None = None,
        clock: Callable[[], datetime] | None = None,
        os_name: str | None = None,
        windows_name: str | None = None,
    ) -> None:
        resolved = normalize_timezone(
            timezone_name, os_name=os_name, windows_name=windows_name,
        )
        if not resolved:
            raise ValueError(f"Zona horaria no válida: {timezone_name}")
        self.timezone_name = resolved
        self._zone = ZoneInfo(resolved)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def now(self) -> AuthoritativeDateTime:
        instant = self._clock()
        if instant.tzinfo is None:
            raise ValueError("La fuente de tiempo debe devolver un datetime con zona horaria.")
        return AuthoritativeDateTime(instant.astimezone(self._zone), self.timezone_name)

    def format_time(self) -> str:
        current = self.now()
        return (
            f"Ahora son las {current.instant:%H:%M} "
            f"({current.abbreviation}, {current.timezone})."
        )

    def format_date(self) -> str:
        local = self.now().instant
        return (
            f"Hoy es {_WEEKDAYS[local.weekday()]}, {local.day} de "
            f"{_MONTHS[local.month - 1]} de {local.year}."
        )

    def answer_action(self, action: str, query: str = "") -> str | None:
        normalized_action = _normalized(action)
        if normalized_action in {"current_time", "time", "hora", "hora actual"}:
            return self.format_time()
        if normalized_action in {"current_date", "date", "fecha", "fecha actual"}:
            return self.format_date()
        return self.answer(query)

    def answer(self, text: str) -> str | None:
        value = _normalized(text).strip(" .?!¿¡")
        time_patterns = {
            "que hora es", "dime la hora", "que hora tenemos", "que hora es ahora",
        }
        date_patterns = {"que dia es hoy", "que fecha es", "dime la fecha", "cual es la fecha de hoy"}
        if value in time_patterns:
            return self.format_time()
        if value in date_patterns:
            return self.format_date()
        return None


def answer_current_date_time(text: str, *, authority: DateTimeAuthority | None = None) -> str | None:
    return (authority or DateTimeAuthority()).answer(text)
