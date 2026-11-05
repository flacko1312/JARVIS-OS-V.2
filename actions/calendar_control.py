"""Google Calendar integration for JARVIS — read and create calendar events.

Uses Google Calendar API v3 with OAuth2. Credentials are stored in the OS
keychain (same secret_store used by email_control). If OAuth is not yet
configured, the tool returns a helpful setup message instead of raising.

Supported actions:
  connect        — start OAuth flow with a credentials JSON file
  status         — report connection state
  list           — list upcoming events (default window: 7 days)
  today          — list events for today only
  create         — create an event
  search         — full-text search across events
  delete         — delete a single event by ID
  disconnect     — revoke and remove stored credentials
"""

from __future__ import annotations

import json
import os
import platform
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SYSTEM = platform.system()

CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
)

_TOKEN_KEY = "gcal_oauth_credentials"
_CLIENT_PATH_KEY = "gcal_oauth_client_path"
_CREDENTIALS_CACHE = ""
_TENANT_CREDENTIALS: dict[str, str] = {}
_CACHE_LOCK = threading.Lock()


class CalendarConnectionError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Dependency and secret-store helpers
# ---------------------------------------------------------------------------

def _secret_store():
    from core.secret_store import get_secret_store
    return get_secret_store()


def _calendar_dependencies():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        return Request, Credentials, InstalledAppFlow, build
    except ImportError as exc:
        raise CalendarConnectionError(
            "Google Calendar support is not installed. "
            "Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc


# ---------------------------------------------------------------------------
# Credential persistence
# ---------------------------------------------------------------------------

def _save_credentials(credentials, client_path: str = "") -> bool:
    global _CREDENTIALS_CACHE
    payload = credentials.to_json()
    try:
        from core.tenant import get_current_user_id
        user_id = get_current_user_id()
    except Exception:
        user_id = None

    with _CACHE_LOCK:
        if user_id:
            _TENANT_CREDENTIALS[user_id] = payload
        else:
            _CREDENTIALS_CACHE = payload

    try:
        store = _secret_store()
        store.set(_TOKEN_KEY, payload)
        if client_path:
            store.set(_CLIENT_PATH_KEY, client_path)
        return store.get(_TOKEN_KEY) == payload
    except Exception:
        return False


def _load_credentials():
    global _CREDENTIALS_CACHE
    Request, Credentials, _flow, _build = _calendar_dependencies()

    try:
        from core.tenant import get_current_user_id
        user_id = get_current_user_id()
    except Exception:
        user_id = None

    with _CACHE_LOCK:
        payload = _TENANT_CREDENTIALS.get(user_id, "") if user_id else _CREDENTIALS_CACHE

    if not payload:
        try:
            payload = _secret_store().get(_TOKEN_KEY) or ""
        except Exception:
            payload = ""

    if not payload:
        raise CalendarConnectionError(
            "Google Calendar no está conectado. Para conectar, descarga un archivo de credenciales "
            "OAuth de Google Cloud Console (tipo 'App de escritorio') y dile a JARVIS: "
            "'conecta Google Calendar con este archivo'."
        )

    try:
        credentials = Credentials.from_authorized_user_info(json.loads(payload), list(CALENDAR_SCOPES))
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            _save_credentials(credentials)
        if not credentials.valid:
            raise CalendarConnectionError("La autorización de Google Calendar ha expirado. Vuelve a conectar.")
        return credentials
    except CalendarConnectionError:
        raise
    except Exception as exc:
        msg = str(exc).lower()
        if "invalid_grant" in msg or "revoked" in msg:
            _clear_credentials()
            raise CalendarConnectionError(
                "Google revocó la conexión con Calendar. Vuelve a conectar."
            ) from exc
        raise CalendarConnectionError(f"No se pudo restaurar la conexión con Calendar: {exc}") from exc


def _clear_credentials() -> None:
    global _CREDENTIALS_CACHE
    try:
        from core.tenant import get_current_user_id
        user_id = get_current_user_id()
    except Exception:
        user_id = None

    with _CACHE_LOCK:
        if user_id:
            _TENANT_CREDENTIALS.pop(user_id, None)
        else:
            _CREDENTIALS_CACHE = ""
    try:
        store = _secret_store()
        store.delete(_TOKEN_KEY)
        store.delete(_CLIENT_PATH_KEY)
    except Exception:
        pass


def _calendar_service():
    _Request, _Credentials, _flow, build = _calendar_dependencies()
    credentials = _load_credentials()
    try:
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        raise CalendarConnectionError(f"No se pudo inicializar Google Calendar: {exc}") from exc


# ---------------------------------------------------------------------------
# OAuth connect flow
# ---------------------------------------------------------------------------

def _valid_client_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        installed = data.get("installed") if isinstance(data, dict) else None
        return bool(
            isinstance(installed, dict)
            and installed.get("client_id")
            and installed.get("auth_uri")
            and installed.get("token_uri")
        )
    except (OSError, ValueError, TypeError):
        return False


def _discover_client_path(explicit_path: str = "") -> Path | None:
    def valid(p) -> Path | None:
        try:
            resolved = Path(p).expanduser().resolve()
        except OSError:
            return None
        return resolved if resolved.is_file() and _valid_client_file(resolved) else None

    if explicit_path:
        return valid(explicit_path)

    env_path = os.environ.get("GCAL_OAUTH_CLIENT_FILE", "").strip()
    if env_path:
        return valid(env_path)

    try:
        saved = _secret_store().get(_CLIENT_PATH_KEY)
        if saved:
            path = valid(saved)
            if path:
                return path
    except Exception:
        pass

    project = Path(__file__).resolve().parent.parent
    candidates = [
        project / "config" / "calendar_credentials.json",
        project / "config" / "credentials.json",
        Path.home() / "Downloads" / "calendar_credentials.json",
        Path.home() / "Downloads" / "credentials.json",
    ]
    valid_candidates = [p for p in (valid(c) for c in candidates) if p]
    if len(set(valid_candidates)) == 1:
        return valid_candidates[0]
    if len(set(valid_candidates)) > 1:
        raise CalendarConnectionError(
            "Se encontraron múltiples archivos de credenciales OAuth. "
            "Especifica el archivo con credentials_path."
        )

    downloads = Path.home() / "Downloads"
    if downloads.exists():
        try:
            discovered = [p for p in (valid(c) for c in downloads.glob("client_secret_*.json")) if p]
            discovered = list(dict.fromkeys(discovered))
            if len(discovered) == 1:
                return discovered[0]
            if len(discovered) > 1:
                raise CalendarConnectionError(
                    "Se encontraron múltiples archivos client_secret en Downloads. "
                    "Especifica credentials_path."
                )
        except CalendarConnectionError:
            raise
        except OSError:
            pass
    return None


def _do_connect(credentials_path: str = "") -> str:
    Request, Credentials, InstalledAppFlow, _build = _calendar_dependencies()
    client_path = _discover_client_path(credentials_path)
    if client_path is None:
        return (
            "No encontré el archivo de credenciales OAuth de Google Calendar. "
            "Descarga un archivo OAuth 2.0 de Google Cloud Console (tipo 'App de escritorio') "
            "y dime: 'conecta Google Calendar con este archivo'."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), list(CALENDAR_SCOPES))
    credentials = flow.run_local_server(port=0, open_browser=True)
    persisted = _save_credentials(credentials, str(client_path))
    if persisted:
        return f"Google Calendar conectado correctamente. Credenciales guardadas en keychain."
    return "Google Calendar conectado (sesión actual). No se pudo guardar en keychain — deberás reconectar al reiniciar."


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

_MONTH_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_WEEKDAY_ES = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}


def _local_tz() -> timezone:
    try:
        from zoneinfo import ZoneInfo
        tz_name = os.environ.get("TZ", "") or "Europe/Madrid"
        return ZoneInfo(tz_name)
    except Exception:
        return timezone(timedelta(hours=1))


def _now() -> datetime:
    return datetime.now(_local_tz())


def _rfc3339(dt: datetime) -> str:
    return dt.isoformat()


def _fmt_event(event: dict) -> str:
    summary = event.get("summary", "(Sin título)")
    start = event.get("start", {})
    end = event.get("end", {})
    start_str = start.get("dateTime", start.get("date", ""))
    end_str = end.get("dateTime", end.get("date", ""))
    location = event.get("location", "")
    description = (event.get("description") or "")[:80]
    event_id = event.get("id", "")

    # Format start/end for display
    try:
        if "T" in start_str:
            dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            dt_local = dt.astimezone(_local_tz())
            start_display = dt_local.strftime("%d/%m/%Y %H:%M")
        else:
            start_display = start_str
        if "T" in end_str:
            dt_end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            dt_end_local = dt_end.astimezone(_local_tz())
            end_display = dt_end_local.strftime("%H:%M")
        else:
            end_display = ""
    except Exception:
        start_display = start_str
        end_display = ""

    parts = [f"• {summary} — {start_display}"]
    if end_display:
        parts[0] += f"–{end_display}"
    if location:
        parts.append(f"  Lugar: {location}")
    if description:
        parts.append(f"  {description}")
    parts.append(f"  ID: {event_id}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _action_status() -> str:
    try:
        credentials = _load_credentials()
        return f"Google Calendar conectado. Token válido hasta: {credentials.expiry}."
    except CalendarConnectionError as exc:
        return f"Google Calendar no conectado: {exc}"


def _action_list(days: int = 7, calendar_id: str = "primary", max_results: int = 20) -> str:
    service = _calendar_service()
    now = _now()
    time_min = _rfc3339(now)
    time_max = _rfc3339(now + timedelta(days=days))
    try:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = result.get("items", [])
    except Exception as exc:
        raise CalendarConnectionError(f"Error al obtener eventos: {exc}") from exc

    if not events:
        return f"No tienes eventos en los próximos {days} día(s)."
    lines = [f"Próximos {len(events)} evento(s) ({days} días):"]
    lines += [_fmt_event(e) for e in events]
    return "\n".join(lines)


def _action_today(calendar_id: str = "primary") -> str:
    service = _calendar_service()
    now = _now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    try:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=_rfc3339(today_start),
            timeMax=_rfc3339(today_end),
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = result.get("items", [])
    except Exception as exc:
        raise CalendarConnectionError(f"Error al obtener eventos de hoy: {exc}") from exc

    if not events:
        return "No tienes eventos para hoy."
    lines = [f"Hoy tienes {len(events)} evento(s):"]
    lines += [_fmt_event(e) for e in events]
    return "\n".join(lines)


def _action_search(query: str, days: int = 30, calendar_id: str = "primary", max_results: int = 10) -> str:
    if not query:
        return "Especifica qué buscar en el calendario."
    service = _calendar_service()
    now = _now()
    try:
        result = service.events().list(
            calendarId=calendar_id,
            q=query,
            timeMin=_rfc3339(now - timedelta(days=days)),
            timeMax=_rfc3339(now + timedelta(days=days)),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = result.get("items", [])
    except Exception as exc:
        raise CalendarConnectionError(f"Error en la búsqueda: {exc}") from exc

    if not events:
        return f"No encontré eventos con '{query}'."
    lines = [f"Resultados para '{query}' ({len(events)}):"]
    lines += [_fmt_event(e) for e in events]
    return "\n".join(lines)


def _action_create(
    title: str,
    date: str = "",
    start_time: str = "",
    end_time: str = "",
    duration_minutes: int = 60,
    location: str = "",
    description: str = "",
    calendar_id: str = "primary",
) -> str:
    if not title:
        return "Necesito al menos el título del evento."

    now = _now()

    # Resolve date
    if not date:
        event_date = now.date()
    else:
        try:
            event_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return f"Formato de fecha no válido: '{date}'. Usa YYYY-MM-DD."

    # Resolve start time
    if start_time:
        try:
            start_dt = datetime.strptime(f"{event_date} {start_time}", "%Y-%m-%d %H:%M")
            start_dt = start_dt.replace(tzinfo=_local_tz())
        except ValueError:
            return f"Formato de hora no válido: '{start_time}'. Usa HH:MM."
    else:
        # Default: next full hour
        start_dt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    # Resolve end time
    if end_time:
        try:
            end_dt = datetime.strptime(f"{event_date} {end_time}", "%Y-%m-%d %H:%M")
            end_dt = end_dt.replace(tzinfo=_local_tz())
        except ValueError:
            return f"Formato de hora de fin no válido: '{end_time}'. Usa HH:MM."
    else:
        end_dt = start_dt + timedelta(minutes=duration_minutes)

    event_body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": _rfc3339(start_dt), "timeZone": str(_local_tz())},
        "end": {"dateTime": _rfc3339(end_dt), "timeZone": str(_local_tz())},
    }
    if location:
        event_body["location"] = location
    if description:
        event_body["description"] = description

    service = _calendar_service()
    try:
        created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    except Exception as exc:
        raise CalendarConnectionError(f"No se pudo crear el evento: {exc}") from exc

    event_id = created.get("id", "?")
    start_str = start_dt.strftime("%d/%m/%Y %H:%M")
    end_str = end_dt.strftime("%H:%M")
    return (
        f"Evento creado: '{title}' el {start_str}–{end_str}."
        + (f" En: {location}." if location else "")
        + f" ID: {event_id}"
    )


def _action_delete(event_id: str, calendar_id: str = "primary") -> str:
    if not event_id:
        return "Especifica el ID del evento a eliminar."
    service = _calendar_service()
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except Exception as exc:
        raise CalendarConnectionError(f"No se pudo eliminar el evento: {exc}") from exc
    return f"Evento {event_id} eliminado del calendario."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def calendar_control(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "list").lower().strip()

    try:
        if action == "connect":
            return _do_connect(params.get("credentials_path", ""))

        if action == "disconnect":
            _clear_credentials()
            return "Google Calendar desconectado. Credenciales eliminadas."

        if action == "status":
            return _action_status()

        if action == "list":
            days = int(params.get("days", 7))
            return _action_list(days=days, calendar_id=params.get("calendar_id", "primary"))

        if action == "today":
            return _action_today(calendar_id=params.get("calendar_id", "primary"))

        if action == "search":
            return _action_search(
                query=params.get("query", ""),
                days=int(params.get("days", 30)),
                calendar_id=params.get("calendar_id", "primary"),
            )

        if action == "create":
            return _action_create(
                title=params.get("title", ""),
                date=params.get("date", ""),
                start_time=params.get("start_time", ""),
                end_time=params.get("end_time", ""),
                duration_minutes=int(params.get("duration_minutes", 60)),
                location=params.get("location", ""),
                description=params.get("description", ""),
                calendar_id=params.get("calendar_id", "primary"),
            )

        if action == "delete":
            return _action_delete(
                event_id=params.get("event_id", ""),
                calendar_id=params.get("calendar_id", "primary"),
            )

        return (
            f"Acción '{action}' no reconocida. "
            "Acciones disponibles: connect, disconnect, status, list, today, search, create, delete."
        )

    except CalendarConnectionError as exc:
        return str(exc)
    except Exception as exc:
        from core.error_reporting import error_report
        error_report(exc, context="calendar_control")
        return f"Error inesperado en calendar_control: {exc}"
