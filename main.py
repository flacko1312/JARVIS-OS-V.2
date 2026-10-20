import asyncio
import os
import re
import threading
import json
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from core.schedule_safety import daily_time_from_text as _daily_time_from_text
from core.schedule_safety import normalize_timezone
from core.schedule_safety import normalized_turn_text as _normalized_turn_text
from core.schedule_safety import schedule_semantics as _schedule_semantics
from core.schedule_safety import user_confirmed as _user_confirmed
from core.date_time_authority import DateTimeAuthority
from core.audio_barge_in import BargeInDecision, SpeechAwareBargeInGate

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None  # headless / no-audio: resolved lazily when audio is actually needed
from google import genai
from google.genai import types
from api import status as jarvis_status
from core.jarvis_client import JarvisClient
from core.lilith_gateway import LilithBridge
from memory.memory_manager import (
    load_memory, format_memory_for_prompt,
)
from memory.conversation_store import (
    ConversationStore,
    append_tool_result as append_conversation_tool_result,
    append_turn as append_conversation_turn,
    default_store_path as default_conversation_store_path,
    empty_state as empty_conversation_state,
    redact_sensitive_text,
    upsert_turn as upsert_conversation_turn,
)
import hashlib
import importlib
import time
import logging
import logging.handlers
from enum import Enum

from core.live_model import pick_live_model
from core.voice_config import (
    DEFAULT_GEMINI_VOICE,
    SUPPORTED_GEMINI_VOICE_NAMES,
    normalize_gemini_voice,
)


def _lazy_action(module_name: str, attribute: str):
    """Keep desktop-only dependencies out of headless API process startup."""

    def invoke(*args, **kwargs):
        action = getattr(importlib.import_module(module_name), attribute)
        return action(*args, **kwargs)

    invoke.__name__ = attribute
    return invoke


# Preserve the historical module-level action surface for patches/plugins while
# deferring platform-specific imports until a declared action actually runs.
file_processor = _lazy_action("actions.file_processor", "file_processor")
flight_finder = _lazy_action("actions.flight_finder", "flight_finder")
open_app = _lazy_action("actions.open_app", "open_app")
weather_action = _lazy_action("actions.weather_report", "weather_action")
send_message = _lazy_action("actions.send_message", "send_message")
prepare_message_reply = _lazy_action("actions.send_message", "prepare_message_reply")
email_control = _lazy_action("actions.email_control", "email_control")
check_messages = _lazy_action("actions.message_monitor", "check_messages")
reminder = _lazy_action("actions.reminder", "reminder")
computer_settings = _lazy_action("actions.computer_settings", "computer_settings")
screen_process = _lazy_action("actions.screen_processor", "screen_process")
youtube_video = _lazy_action("actions.youtube_video", "youtube_video")
media_control = _lazy_action("actions.media_control", "media_control")
desktop_control = _lazy_action("actions.desktop", "desktop_control")
browser_control = _lazy_action("actions.browser_control", "browser_control")
file_controller = _lazy_action("actions.file_controller", "file_controller")
code_helper = _lazy_action("actions.code_helper", "code_helper")
dev_agent = _lazy_action("actions.dev_agent", "dev_agent")
web_search_action = _lazy_action("actions.web_search", "web_search")
computer_control = _lazy_action("actions.computer_control", "computer_control")
game_updater = _lazy_action("actions.game_updater", "game_updater")
request_presentation = _lazy_action("actions.presentation_maker", "request_presentation")
request_deep_research = _lazy_action("actions.deep_research", "request_deep_research")


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _load_dotenv():
    """Load .env file if it exists. Silently skip if not found."""
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        # python-dotenv not installed — rely on already-set env vars
        pass


BASE_DIR        = get_base_dir()
_load_dotenv()


def _setup_logging() -> None:
    """Configure persistent rotating log at BASE_DIR/logs/jarvis.log.

    Call once at module load.  Safe to call multiple times — exits early
    if handlers are already attached so test imports don't double-configure.
    """
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "jarvis.log"

    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    root.setLevel(logging.DEBUG)

    # Rotating file: 5 MB × 5 backups → max ~25 MB on disk
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    # Console: WARNING only — keeps existing stdout output uncluttered
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    root.addHandler(fh)
    root.addHandler(ch)


_setup_logging()
logger = logging.getLogger("jarvis.main")

API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
SUPPORTED_VOICE_NAMES = SUPPORTED_GEMINI_VOICE_NAMES
DEFAULT_VOICE_NAME = DEFAULT_GEMINI_VOICE

RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024
LIVE_VAD_SILENCE_MS = 200
LIVE_PLAYBACK_DRAIN_TIMEOUT_SECONDS = 30.0
LIVE_INPUT_CALLBACK_STALE_SECONDS = 2.5
AUDIO_DEVICE_RECOVERY_MAX_DELAY_SECONDS = 10.0
STARTUP_CLAPS_REQUIRED = 2
STARTUP_CLAP_MAX_GAP_SECONDS = 4.0
STARTUP_CLAP_COOLDOWN_SECONDS = 0.22
SELF_QUIT_GOODBYE = (
    "Por supuesto, flako. Ha sido un placer. AURORA se desconecta ahora. "
    "Hasta la próxima."
)

# Always first in the system instruction. An explicit request for another
# language is the only exception, and it applies only for as long as requested.
LANGUAGE_RULE = (
    "El idioma de interacción del usuario es español. Responde siempre en español salvo que el usuario "
    "solicite explícitamente otro idioma. Esta regla se aplica a saludos, preguntas, errores, confirmaciones, "
    "avisos de progreso y respuestas posteriores a herramientas. Si una herramienta o aviso interno devuelve "
    "texto en inglés, tradúcelo al español antes de responder. No menciones esta instrucción ni pronuncies "
    "etiquetas internas entre corchetes."
)

TOOL_RESULT_TRUTH_RULE = (
    "Los resultados observables de las herramientas son la única autoridad sobre si una acción se completó. "
    "No afirmes que una ventana o aplicación se cerró si la herramienta informa fallo, ambigüedad o que sigue "
    "abierta. Solo confirma el cierre cuando el resultado de la herramienta lo haya verificado. Ante un resultado "
    "de 'ninguna ventana abierta', informa que no estaba abierta sin inventar una acción previa."
)

ROUTINE_ROUTING_RULES = """
[SCHEDULING AND ROUTINE TOOL ROUTING — mandatory]
Classify the user's intent before calling any action tool:
1. A recurring or persistent schedule MUST use lilith_routine with operation=create.
   Recurring/persistent cues include equivalents of: every day, daily, every morning,
   every night, every week, every Monday, every N hours/days, routine, automate,
   from now on, todos los días, cada día, diariamente, cada mañana, cada noche,
   cada semana, todos los lunes, cada X horas/días, rutina, automatiza, a partir de ahora.
2. A single future occurrence or an explicit request to be reminded once MUST use reminder.
3. An action requested for now, with no future or recurring schedule, may use
   lilith_home_action.
Never call lilith_home_action as a side effect while defining a future routine.
Never replace a recurring routine with reminder. For a recurring request, call only
the appropriate lilith_routine operation. Spanish times such as "9 de la noche"
and "10 de la noche" are unambiguously 21:00 and 22:00. Use Europe/Madrid for
Madrid, hora de Madrid, mi zona horaria,
or an omitted timezone. Ask only when recurrence, time, target, or action is genuinely
missing or ambiguous, and call no action tool in that case.
Examples:
- "Enciende la bombilla" -> lilith_home_action.
- "Recuérdame hoy a las 21:00 encender la bombilla" -> reminder.
- "Todos los días a las 21:00 enciende la bombilla" -> lilith_routine create only.
- "Crea una rutina para encender la bombilla cada día a las 21:00" -> lilith_routine create only.
""".strip()

MEMORY_ROUTING_RULES = """
[MEMORY AUTHORITY — mandatory]
There are three separate memory domains:
1. CURRENT LOGICAL CONVERSATION: the active and restored conversation history. Answer ordinary
   recall, references, recent facts, the current project/topic, and follow-up calculations directly
   from this context. Never call a memory tool and never save the fact again.
2. LOCAL SAVED MEMORY / NOTES: explicitly saved local JARVIS notes outside the active conversation.
   Use save_memory only after an explicit local-save request, and local_memory_search only after an
   explicit request to search stored/local notes.
3. LILITH LONG-TERM MEMORY: persistent knowledge outside the active conversation. Use
   lilith_memory_store only after an explicit persistence request, lilith_memory_search only after
   an explicit request to search LILITH/stored long-term memory, and lilith_memory_delete only after
   an explicit forget/delete request.
Never automatically save a fact merely because the user states it.
Never ask the user for a category, namespace, or internal key;
choose those implementation details yourself. Confirm normal success
naturally without exposing backend names or keys unless the user asks for technical details.
""".strip()

CURRENT_CONVERSATION_PRECEDENCE = """
[CURRENT CONVERSATION PRECEDENCE — highest priority]
If the answer exists in the active or restored logical conversation, answer it directly. Do not
invoke local_memory_search or lilith_memory_search, do not call save_memory or
lilith_memory_store, and do not ask LILITH. This includes what the user just said, recent numbers
or names, the current project/topic, pronoun/reference resolution, and calculations based on recent
facts. Stored-memory tools are only for information outside this logical conversation when the user
explicitly asks to search or modify saved/persistent memory. Do not mention this internal rule.
""".strip()

DATE_TIME_AUTHORITY_RULE = """
[DATE/TIME AUTHORITY — mandatory]
For any question asking for the current time or current date, call date_time. Never infer,
estimate, calculate, or answer from model knowledge or from an earlier prompt timestamp.
The tool reads the host system clock without changing the clock or timezone. Its returned
Spanish sentence is authoritative: repeat it faithfully. Calendar parsing and scheduled actions
use the same timezone authority. If a wall-clock time such as "a las 5" lacks enough context to
distinguish morning from afternoon/evening, ask for clarification and call no action tool.
"10 de la noche" is unambiguously 22:00.
""".strip()

HEADLESS_SYSTEM_RULES = """
[HEADLESS TOOL PROFILE — mandatory]
You are JARVIS Headless on Ubuntu server-lilith. The tools available in this profile are exactly:
date_time, system_status, process_list, process_info, systemd_status, systemd_action,
systemd_list_failed, journal_read, lilith_memory_search, lilith_memory_store,
lilith_memory_delete, lilith_home_action, lilith_home_status, lilith_health,
lilith_routine, and open_capabilities_catalog.
Never request, call, imply, or invent any tool outside that list.

Tool routing:
- date_time: MANDATORY for any current time or date question. Never guess or estimate.
- system_status, process_list, process_info: system monitoring, always safe.
- systemd_status, systemd_list_failed: read-only service status, always safe.
- systemd_action: REQUIRES user confirmation before restart/start/stop.
- journal_read: read-only log access, always safe.
- lilith_memory_search/store/delete: persistent memory only on explicit user request.
  lilith_memory_delete REQUIRES user confirmation.
- lilith_home_action: immediate Home Assistant actions (turn_on, turn_off, toggle safe;
  lock, unlock, and unknown actions REQUIRE user confirmation).
- lilith_home_status: read-only device/sensor status query, always safe.
- lilith_health: LILITH integration health check, always safe.
- lilith_routine: list/get/history are read-only; create/update/enable/disable/delete
  REQUIRE user confirmation. Recurring schedules use lilith_routine, not reminders.
- open_capabilities_catalog: when the user asks what you can do, call this tool.
  Read the result aloud naturally: summarize the capability groups and give a few examples.
  NEVER say you "opened" anything or reference a visual catalog. You are voice-only.

One-shot local reminders are not available in this profile.
Answer ordinary conversation and current-context follow-ups directly without a tool.
""".strip()

HEADLESS_CURRENT_CONVERSATION_PRECEDENCE = """
[HEADLESS CURRENT CONVERSATION PRECEDENCE — highest priority]
If the answer exists in the active or restored logical conversation, answer it directly.
Do not call any memory tool for immediate context. Use lilith_memory_search/store/delete only
for explicit persistent-memory requests concerning information outside the current conversation.
Do not mention tools or capabilities that are not in the headless profile.
""".strip()

_SCHEDULED_TOOL_NAMES = frozenset({"lilith_home_action", "reminder", "lilith_routine"})
_ROUTINE_READ_OPERATIONS = frozenset({"list", "get", "history"})
_ROUTINE_WRITE_OPERATIONS = frozenset({"create", "update", "enable", "disable", "delete"})
_MEMORY_MUTATING_TOOL_NAMES = frozenset({"save_memory", "lilith_memory_store", "lilith_memory_delete"})
_MEMORY_LOOKUP_TOOL_NAMES = frozenset({"local_memory_search", "lilith_memory_search"})


def _canonical_memory_key(key: str, category: str | None = None) -> str:
    """Return LILITH's public semantic key (without its internal ``jarvis:`` prefix)."""
    value = str(key or "").strip()
    if value.startswith("jarvis:"):
        value = value[len("jarvis:"):]
    value = value.strip(" /")
    category_value = str(category or "").strip().strip(" /")
    if not value:
        return ""
    if "/" in value or not category_value:
        return value
    return f"{category_value}/{value}"


def _memory_category_from_key(key: str, fallback: str = "jarvis_fact") -> str:
    canonical = _canonical_memory_key(key)
    return canonical.split("/", 1)[0] if "/" in canonical else fallback


def _is_explicit_persistent_memory_request(text: str) -> bool:
    """Recognize an explicit request to persist user knowledge, not an operational note."""
    return bool(_memory_authority_indicators(text)["persistent"])


def _is_explicit_local_memory_request(text: str) -> bool:
    """Recognize the narrow operational/session scope owned by local JARVIS memory."""
    evidence = _memory_authority_indicators(text)
    return bool(evidence["local"] or evidence["negated_lilith"])


def _memory_authority_control_text(text: str) -> str:
    """Repair only known memory-control tokens fragmented by Live STT.

    This view is used solely for authority classification. It never replaces the
    transcript and is never used to derive or mutate a stored key/value.
    """
    tokens = re.findall(r"[a-z0-9]+", _normalized_turn_text(text))
    vocabulary = {
        "guarda", "guardalo", "guardes", "guardar", "local", "localmente",
        "lilith", "sesion", "jarvis", "recuerda", "memoria",
    }
    # Dynamic programming avoids a greedy false split such as
    # ``guar da lo cal mente`` -> ``guardalo cal mente``. The best path is the
    # one that recognizes the most vocabulary items: ``guarda localmente``.
    best: list[tuple[int, list[str]]] = [(0, []) for _ in range(len(tokens) + 1)]
    for index in range(len(tokens) - 1, -1, -1):
        best[index] = (best[index + 1][0], [tokens[index], *best[index + 1][1]])
        for width in (3, 2):
            candidate = "".join(tokens[index:index + width])
            if len(tokens[index:index + width]) == width and candidate in vocabulary:
                score = 1 + best[index + width][0]
                if score > best[index][0]:
                    best[index] = (score, [candidate, *best[index + width][1]])
    return " ".join(best[0][1])


def _memory_authority_indicators(text: str) -> dict[str, object]:
    """Return explainable authority signals from the control-only transcript view."""
    value = _memory_authority_control_text(text)
    local_patterns = {
        "localmente": r"\blocalmente\b",
        "solo_local": r"\bsolo (?:en (?:tu )?memoria )?local\b|\bsolo localmente\b",
        "jarvis": r"\b(?:solo )?(?:en )?jarvis\b",
        "session_only": r"\bsolo (?:durante )?(?:esta|la) sesion\b",
        "session_context": r"\b(?:esta|la|mi) sesion\b|\bcontexto (?:de sesion|operativo|del runtime)\b",
        "local_state": r"\b(?:nota|memoria|estado|bandera|flag) local\b|\b(?:runtime|ui) (?:hint|state|flag)\b",
    }
    persistent_patterns = {
        "memory_command": (
            r"\b(?:guarda|guardalo|guardar|almacena|memoriza|recuerda)\b.{0,32}\bmemoria\b"
        ),
        "remember_fact": r"\b(?:guarda|recuerda) que\b|\bquiero que recuerdes\b",
        "remember_later": r"\bguarda\b.{0,48}\b(?:mas adelante|para despues|en el futuro)\b",
        "english_memory": r"\b(?:save|store|remember)\b.{0,32}\b(?:memory|about me)\b",
    }
    negated_patterns = {
        "no_lilith": r"\bno (?:lo )?(?:guardes|guarda|guardar|guarde)(?:\s+\w+){0,3}\s+(?:en )?lilith\b",
        "not_in_lilith": r"\bno (?:lo )?en lilith\b",
    }
    return {
        "control_text": value,
        "local": tuple(name for name, pattern in local_patterns.items() if re.search(pattern, value)),
        "persistent": tuple(name for name, pattern in persistent_patterns.items() if re.search(pattern, value)),
        "negated_lilith": tuple(name for name, pattern in negated_patterns.items() if re.search(pattern, value)),
    }


def _memory_control_log_excerpt(text: str) -> str:
    """Keep only the authority clause for diagnostics; omit the fact/value after 'que'."""
    value = str(text or "").strip()
    value = re.split(r"\bque\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.sub(r"\d+", "<value>", value)
    return value[:180]


def _classify_memory_request(text: str, *, source: str, requested_tool: str) -> str:
    """Classify memory authority without trusting a possibly partial Live transcript."""
    if requested_tool == "lilith_memory_delete":
        return "persistent"
    if requested_tool not in {"save_memory", "lilith_memory_store"}:
        return "unknown"
    # Authority comes from the user, never from Gemini's selected storage tool.
    # A reliable negative/local instruction has precedence over persistence.
    if _is_explicit_local_memory_request(text):
        return "local"
    if _is_explicit_persistent_memory_request(text):
        return "persistent"
    if source in {"voice", "text"}:
        return "ambiguous"
    return "unknown"


def _explicit_memory_lookup_scope(text: str) -> str:
    """Return the explicitly requested saved-memory domain, never inferred recall intent."""
    value = _normalized_turn_text(text)
    if not value:
        return "none"
    explicit_search = bool(re.search(
        r"\b(?:busca|buscar|consulta|consultar|revisa|revisar)\b.{0,48}\b(?:memoria|notas?|guardad[oa]s?|recuerdos?)\b"
        r"|\b(?:que|qué) (?:tienes|hay) guardad[oa]\b"
        r"|\b(?:lo que|algo que) (?:te )?(?:pedi |pedí )?guardar\b"
        r"|\brecuerdos? almacenados?\b"
        r"|\b(?:en|de) (?:tu |la |tus )?(?:memoria|notas?)\b",
        value,
    ))
    if not explicit_search:
        return "none"
    if re.search(r"\blilith\b|\b(?:memoria|historial) (?:persistente|de largo plazo)\b", value):
        return "persistent"
    if re.search(r"\b(?:local|jarvis|notas?)\b", value):
        return "local"
    return "stored"


def _has_explicit_memory_write_intent(text: str) -> bool:
    """Recognize an explicit save command without treating an ordinary fact as one."""
    value = _normalized_turn_text(text)
    return bool(re.search(
        r"\b(?:guarda|guardalo|guardar|almacena|memoriza|anota|apunta|save|store)\b"
        r"|\brecuerda (?:esto|que)\b|\bquiero que recuerdes\b",
        value,
    ))


def _memory_key_alias(value: str) -> str:
    normalized = _normalized_turn_text(str(value or "")).replace("/", " ").replace("_", " ")
    return " ".join(normalized.split())


def _automatic_memory_category(text: str, supplied: str | None = None) -> str:
    value = _normalized_turn_text(text)
    if re.search(r"\b(?:prefiero|preferencia|favorit[oa]|me gusta)\b", value):
        return "preferences"
    if re.search(r"\b(?:proyecto|project)\b", value):
        return "projects"
    candidate = str(supplied or "").strip()
    return candidate or "notes"


def _automatic_memory_key(text: str, supplied: str | None = None) -> str:
    candidate = _canonical_memory_key(str(supplied or ""))
    if candidate:
        return candidate.rsplit("/", 1)[-1]
    basis = _normalized_turn_text(text) or "memory_fact"
    if re.search(r"\b(?:luz|light)\b", basis) and re.search(
        r"\b(?:prefiero|preferencia|preferida|preferred|preference)\b", basis,
    ):
        return "preferred_light_level"
    return f"fact_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:12]}"


@dataclass
class PendingRoutineState:
    """Session-bound routine intent assembled across Gemini Live turns."""

    session_id: str
    origin_turn: int
    last_turn: int
    operation: str = "create"
    target: str = ""
    recurrence: str = ""
    hour: int | None = None
    minute: int | None = None
    timezone: str = "Europe/Madrid"
    action: str = ""
    pending_clarification: set[str] = field(default_factory=set)
    consumed_call_ids: set[str] = field(default_factory=set)

    def observe_text(self, text: str, turn: int) -> None:
        self.last_turn = turn
        if _schedule_semantics(text) == "recurring":
            self.recurrence = "daily" if _is_daily_routine_text(text) else self.recurrence
        when = _daily_time_from_text(text)
        if when is not None:
            self.hour, self.minute = when
        value = _normalized_turn_text(text)
        if any(alias in value for alias in ("madrid", "mi zona horaria", "hora local")):
            self.timezone = "Europe/Madrid"
        action, target = _routine_action_target(text, {})
        if action:
            self.action = action
        if target:
            self.target = target
        self.refresh_missing()

    def absorb_call(self, args: dict) -> None:
        operation = str(args.get("operation") or "").strip().lower()
        if operation:
            self.operation = operation
        description_time = _daily_time_from_text(str(args.get("description") or ""))
        if description_time is not None:
            self.hour, self.minute = description_time
        name_time = _daily_time_from_text(str(args.get("name") or ""))
        if name_time is not None and self.hour is None:
            self.hour, self.minute = name_time
        schedule_type = str(args.get("schedule_type") or "").strip().lower()
        if schedule_type:
            self.recurrence = schedule_type
        schedule = args.get("schedule")
        if isinstance(schedule, dict):
            if self.hour is None and isinstance(schedule.get("hour"), int):
                raw_h = schedule["hour"]
                from core.schedule_safety import _resolve_period, _apply_period, normalized_turn_text
                period_ctx = _resolve_period(
                    normalized_turn_text(str(args.get("description") or args.get("name") or ""))
                )
                resolved = _apply_period(raw_h, period_ctx) if period_ctx else raw_h
                self.hour = resolved if resolved is not None else raw_h
            if self.minute is None and isinstance(schedule.get("minute"), int):
                self.minute = schedule["minute"]
        timezone = normalize_timezone(args.get("timezone"), default=self.timezone)
        if timezone:
            self.timezone = timezone
        nested = args.get("action_parameters")
        nested = dict(nested) if isinstance(nested, dict) else {}
        self.target = str(
            nested.get("entity_id") or nested.get("target") or args.get("target") or self.target
        ).strip()
        self.action = str(nested.get("action") or args.get("action") or self.action).strip()
        self.refresh_missing()

    def refresh_missing(self) -> None:
        missing = set()
        if not self.recurrence:
            missing.add("recurrence")
        if self.hour is None or self.minute is None:
            missing.add("time")
        if not self.target:
            missing.add("target")
        if not self.action:
            missing.add("action")
        self.pending_clarification = missing


@dataclass
class PendingRoutineConfirmation:
    """Holds a routine mutation awaiting explicit user confirmation."""

    session_id: str
    turn_sequence: int
    fc_id: str
    fc_name: str
    operation: str
    args: dict
    summary: str
    confirmed: bool | None = None


def _is_daily_routine_text(text: str) -> bool:
    value = _normalized_turn_text(text)
    return bool(re.search(
        r"\b(?:todos? los dias|cada dia|diariamente|cada manana|cada noche|every day|daily|every morning|every night)\b",
        value,
    ))


def _routine_action_target(text: str, source_args: dict) -> tuple[str, str]:
    """Recover only safety-critical home fields when Gemini selects the wrong tool."""
    value = _normalized_turn_text(text)
    nested = source_args.get("action_parameters")
    nested = dict(nested) if isinstance(nested, dict) else {}
    action = str(source_args.get("action") or nested.get("action") or "").strip()
    target = str(source_args.get("target") or nested.get("target") or nested.get("entity_id") or "").strip()
    if not action:
        if re.search(r"\b(?:enciende|encender|turn on|switch on)\b", value):
            action = "turn_on"
        elif re.search(r"\b(?:apaga|apagar|turn off|switch off)\b", value):
            action = "turn_off"
    if not target and action:
        target = re.sub(
            r"(?i)\b(?:todos? los dias|cada dia|diariamente|a las?\s+\w+(?:\s+de la (?:manana|tarde|noche))?|"
            r"enciende|encender|apaga|apagar|turn on|turn off|crea una rutina para|routine|every day)\b",
            " ", text,
        )
        target = " ".join(target.strip(" .,:;-").split())
    return action, target


def _routine_args_from_wrong_call(turn_text: str, fc) -> dict | None:
    """Build the existing JL-A9 routine contract without performing an effect."""
    when = _daily_time_from_text(turn_text)
    is_daily = _is_daily_routine_text(turn_text)
    if not is_daily or when is None:
        return None
    source_args = dict(getattr(fc, "args", None) or {})
    nested_params = source_args.get("action_parameters")
    nested_params = dict(nested_params) if isinstance(nested_params, dict) else {}
    action, target = _routine_action_target(
        str(source_args.get("message", "")).strip() or turn_text, source_args
    )
    if action not in {"turn_on", "turn_off"} or not target:
        return None
    hour, minute = when
    return {
        "operation": "create", "name": str(source_args.get("name") or f"{action} {target} daily"),
        "schedule_type": "daily", "schedule": {"hour": hour, "minute": minute},
        "timezone": normalize_timezone(
            source_args.get("timezone"),
            default=os.getenv("JARVIS_TIMEZONE", "Europe/Madrid"),
        ) or os.getenv("JARVIS_TIMEZONE", "Europe/Madrid"),
        "action_intent": "home.action",
        "action_parameters": {
            **nested_params,
            "target": target,
            "action": action,
            "parameters": source_args.get("parameters") or nested_params.get("parameters") or {},
        },
    }

_SELF_QUIT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:quit|close|exit)\s+(?:jarvis|yourself)\b",
    r"\b(?:shut|turn)\s+(?:jarvis|yourself)\s+(?:down|off)\b",
    r"\b(?:shut\s+down|turn\s+off|power\s+down)\s+(?:jarvis|yourself)\b",
    r"\bjarvis\b.{0,36}\b(?:quit|close|exit|shut\s+down|turn\s+off|go\s+offline)\b",
    r"\b(?:go|take\s+yourself)\s+offline(?:\s+jarvis)?\b",
))


def _exception_leaves(exc: BaseException):
    nested = getattr(exc, "exceptions", None)
    if nested:
        for child in nested:
            yield from _exception_leaves(child)
    else:
        yield exc


def _is_normal_live_close_error(exc: BaseException) -> bool:
    for leaf in _exception_leaves(exc):
        name = leaf.__class__.__name__.lower()
        message = str(leaf).lower()
        if name == "connectionclosedok" or "1000 (ok)" in message:
            return True
        if isinstance(leaf, genai.errors.APIError) and "1000" in message:
            return True
    return False


def _is_transient_live_connection_error(exc: BaseException) -> bool:
    transient_markers = (
        "connection reset", "connection aborted", "temporarily unavailable",
        "timed out", "timeout", "network is unreachable", "broken pipe",
    )
    return any(
        isinstance(leaf, (ConnectionResetError, ConnectionAbortedError, TimeoutError))
        or any(marker in str(leaf).lower() for marker in transient_markers)
        for leaf in _exception_leaves(exc)
    )


def _is_resumption_handle_rejected(exc: BaseException) -> bool:
    markers = (
        "session resumption", "resumption handle", "resume handle",
        "invalid handle", "expired handle", "handle expired",
    )
    return any(
        any(marker in str(leaf).lower() for marker in markers)
        for leaf in _exception_leaves(exc)
    )


class RecoverableLiveDisconnect(ConnectionError):
    """Real Live transport/session failure that should trigger a silent reconnect."""

    def __init__(
        self,
        detail: str,
        *,
        category: str = "transport",
        close_code: int | str | None = None,
    ) -> None:
        super().__init__(detail)
        self.category = category
        self.close_code = close_code


def _safe_live_diagnostic(value: object, limit: int = 160) -> str:
    """Single-line, bounded transport diagnostic; never includes payload/audio."""
    text = redact_sensitive_text(str(value or "").replace("\x00", ""))
    text = " ".join(text.split())
    return text[:limit] or "none"


def _live_disconnect_diagnostics(exc: BaseException) -> dict[str, object]:
    leaves = list(_exception_leaves(exc)) or [exc]
    primary = next(
        (leaf for leaf in leaves if isinstance(leaf, RecoverableLiveDisconnect)),
        leaves[0],
    )
    category = getattr(primary, "category", None)
    if not category:
        if isinstance(primary, (asyncio.TimeoutError, TimeoutError)):
            category = "timeout"
        elif _is_normal_live_close_error(primary):
            category = "provider_close"
        elif _is_transient_live_connection_error(primary):
            category = "network"
        else:
            category = "transport"
    code = getattr(primary, "close_code", None) or getattr(primary, "code", None)
    return {
        "category": category,
        "exception": type(primary).__name__,
        "close_code": code if code is not None else "none",
        "detail": _safe_live_diagnostic(primary),
    }


class InitialHistoryRejected(ConnectionError):
    """Gemini rejected the optional initial-history protocol."""


_RECOVERABLE_WS_CLOSE_CODES = frozenset({1006, 1001, 1011, 1012, 1013, 1014})


def _is_websocket_abnormal_close(exc: BaseException) -> bool:
    """Recognize WebSocket abnormal closures that should trigger reconnect."""
    name = type(exc).__name__
    msg = str(exc).lower()
    if name == "ConnectionClosedError" or (
        "connectionclosederror" in name.lower()
    ):
        return True
    if "no close frame" in msg or "abnormal closure" in msg:
        return True
    if isinstance(exc, genai.errors.APIError):
        code = getattr(exc, "status", None) or getattr(exc, "code", None)
        if code is None:
            try:
                code = int(str(exc).split()[0])
            except (ValueError, IndexError):
                code = None
        if code in _RECOVERABLE_WS_CLOSE_CODES:
            return True
    return False


def _is_recoverable_live_disconnect(exc: BaseException) -> bool:
    leaves = list(_exception_leaves(exc))
    return bool(leaves) and all(
        isinstance(leaf, RecoverableLiveDisconnect)
        or _is_normal_live_close_error(leaf)
        or _is_transient_live_connection_error(leaf)
        or _is_session_not_found_1008(leaf)
        or _is_invalid_argument_1007(leaf)
        or _is_websocket_abnormal_close(leaf)
        for leaf in leaves
    )


def _live_reconnect_delay(attempt: int) -> float:
    return min(30.0, float(2 ** max(0, int(attempt) - 1)))


def _audio_device_recovery_delay(attempt: int) -> float:
    return min(
        AUDIO_DEVICE_RECOVERY_MAX_DELAY_SECONDS,
        0.5 * float(2 ** max(0, int(attempt) - 1)),
    )


class AudioInputDeviceLost(ConnectionError):
    """The local capture stream stopped producing usable callbacks."""


def _current_default_input_device() -> tuple[int | None, str]:
    """Resolve the current OS default input on every open/recovery attempt."""
    default = getattr(sd.default, "device", None)
    try:
        index = int(default[0])
    except (TypeError, IndexError, ValueError):
        index = None
    if index is not None and index < 0:
        index = None
    info = sd.query_devices(index, "input")
    if int(info.get("max_input_channels", 0)) < CHANNELS:
        raise AudioInputDeviceLost("default input exposes no capture channel")
    return index, _safe_live_diagnostic(info.get("name", "default input"), 80)


def _device_supports_rate(idx: int, kind: str, rate: int) -> bool:
    """Return True if device *idx* accepts *rate* Hz for *kind*."""
    if sd is None:
        return False
    try:
        check = sd.check_input_settings if kind == "input" else sd.check_output_settings
        check(device=idx, samplerate=rate, channels=CHANNELS, dtype="int16")
        return True
    except Exception:
        return False


def _resolve_device_by_name(
    kind: str, name_hints: tuple[str, ...] = (), *, required_rate: int = 0
) -> int | None:
    """Find an audio device whose name contains any of *name_hints*.

    *kind* is ``"input"`` or ``"output"``.  When *required_rate* is nonzero
    the candidate must also accept that sample rate.  Returns the device
    index, or ``None`` to let sounddevice use the system default.
    """
    if sd is None:
        return None
    devices = sd.query_devices()
    chan_key = "max_input_channels" if kind == "input" else "max_output_channels"
    for hint in name_hints:
        hint_lower = hint.lower()
        for idx, dev in enumerate(devices):
            if hint_lower in dev["name"].lower() and int(dev.get(chan_key, 0)) >= CHANNELS:
                if required_rate and not _device_supports_rate(idx, kind, required_rate):
                    continue
                return idx
    return None


_HEADLESS_INPUT_HINTS = (
    "ALC3234 Analog", "HDA Intel PCH", "pulse", "default",
)
_HEADLESS_OUTPUT_HINTS = (
    "ALC3234 Analog", "HDA Intel PCH", "pulse", "default",
)


def _headless_input_device() -> tuple[int | None, str]:
    """Resolve input device by name for headless deployments."""
    resolved = _resolve_device_by_name(
        "input", _HEADLESS_INPUT_HINTS, required_rate=SEND_SAMPLE_RATE,
    )
    if resolved is not None:
        info = sd.query_devices(resolved, "input")
        return resolved, _safe_live_diagnostic(info.get("name", "headless input"), 80)
    return _current_default_input_device()


def _is_invalid_argument_1007(exc: BaseException) -> bool:
    return any(
        "1007" in str(leaf)
        and "invalid argument" in str(leaf).lower()
        for leaf in _exception_leaves(exc)
    )


def _is_session_not_found_1008(exc: BaseException) -> bool:
    for leaf in _exception_leaves(exc):
        s = str(leaf).lower()
        if "1008" in s and (
            "session not found" in s
            or "requested entity was not found" in s
        ):
            return True
    return False


_SESSION_RESUMPTION_HANDLE_MAX_AGE = 600.0  # 10 minutes


def _live_response_audio_bytes(response) -> bytes | None:
    server_content = getattr(response, "server_content", None)
    model_turn = getattr(server_content, "model_turn", None)
    for part in getattr(model_turn, "parts", None) or []:
        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None)
        mime_type = str(getattr(inline_data, "mime_type", "") or "").lower()
        if data and mime_type.startswith("audio/"):
            return bytes(data)
    return None


def wait_for_startup_claps(
    required: int = STARTUP_CLAPS_REQUIRED,
    *,
    timeout: float | None = None,
    stream_factory=None,
) -> bool:
    """Hold startup until two distinct claps are heard by the default microphone."""
    if os.environ.get("JARVIS_SKIP_CLAP_GATE", "").strip().lower() in {"1", "true", "yes", "on"}:
        print("[JARVIS] 👏 Startup clap gate bypassed (JARVIS_SKIP_CLAP_GATE).")
        return True
    # Some macOS/AUHAL configurations expose a nominal input device but reject
    # every PortAudio operation (PaErrorCode -9986). Avoid repeatedly starting
    # a failing Core Audio stream; users with a working mic can opt in.
    if sys.platform == "darwin" and stream_factory is None and os.environ.get("JARVIS_ENABLE_CLAP_GATE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        print("[JARVIS] ⚠️ macOS microphone gate disabled for this audio configuration.")
        print("[JARVIS] Continuing without clap startup. Set JARVIS_ENABLE_CLAP_GATE=1 to force it.")
        return True

    required = max(1, int(required))
    stream_factory = stream_factory or sd.InputStream
    try:
        import numpy as np
    except ImportError:
        print("[JARVIS] ❌ Startup clap gate needs numpy. Set JARVIS_SKIP_CLAP_GATE=1 to bypass.")
        return False

    clap_times: list[float] = []
    last_clap_at = 0.0
    # Microphone input levels vary considerably between Mac models.  The old
    # fixed 0.12 RMS / 0.32 peak gates rejected quiet real claps, while laptop
    # fan noise could sometimes trip them.  Track the room floor and use both
    # transient shape (crest factor) and energy to identify a clap.
    noise_floor = 0.008
    finished = threading.Event()
    started_at = time.monotonic()

    def callback(indata, frames, time_info, status):
        nonlocal last_clap_at, noise_floor, clap_times
        if status:
            print(f"[JARVIS] ⚠️ Clap mic: {status}")
        samples = np.asarray(indata, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return
        magnitude = np.abs(samples)
        rms = float(np.sqrt(np.mean(samples * samples)))
        peak = float(np.max(magnitude))
        # Only let low-energy frames teach the noise floor; otherwise a clap
        # would raise the threshold immediately and make the second clap hard
        # to detect.
        if rms < max(0.08, noise_floor * 6.0):
            noise_floor = (noise_floor * 0.96) + (rms * 0.04)
        threshold = max(0.100, noise_floor * 6.5)
        peak_threshold = max(0.35, noise_floor * 15.0)
        crest_factor = peak / max(rms, 1e-6)
        now = time.monotonic()
        # A valid clap must be either a sharp transient with meaningful energy
        # or a genuinely loud impact. This rejects speech, fan noise, and most
        # desk/keyboard taps that only have a brief peak.
        is_transient = crest_factor >= 2.20 and rms >= threshold
        is_loud = rms >= max(0.28, noise_floor * 15.0)
        if (
            peak < peak_threshold
            or not (is_transient or is_loud)
            or now - last_clap_at < STARTUP_CLAP_COOLDOWN_SECONDS
        ):
            return
        if clap_times and now - clap_times[-1] > STARTUP_CLAP_MAX_GAP_SECONDS:
            clap_times = []
        clap_times.append(now)
        last_clap_at = now
        print(f"[JARVIS] 👏 Clap {len(clap_times)}/{required} detected")
        if len(clap_times) >= required:
            finished.set()

    print(f"[JARVIS] 👏 Waiting for {required} claps to power up...")
    # PortAudio on macOS commonly rejects 16 kHz even when the microphone is
    # available (PaErrorCode -9986). Prefer the device's native rate, then
    # retry standard rates before reporting that the microphone is unavailable.
    sample_rates = [SEND_SAMPLE_RATE, 44100, 48000]
    input_device = None
    try:
        if stream_factory is sd.InputStream:
            try:
                default_device = sd.default.device
                try:
                    input_index = int(default_device[0])
                except (TypeError, IndexError, ValueError):
                    input_index = -1
                if input_index < 0:
                    print("[JARVIS] ⚠️ macOS reports no default microphone device.")
                    if os.environ.get("JARVIS_REQUIRE_CLAP_GATE", "").strip().lower() not in {"1", "true", "yes", "on"}:
                        print("[JARVIS] ⚠️ Continuing without the clap gate; microphone input is unavailable.")
                        return True
                    raise RuntimeError("no default microphone device")
                input_device = input_index
                device = sd.query_devices(input_device if input_device is not None else None, "input")
                if int(device.get("max_input_channels", 0)) < 1:
                    raise RuntimeError("no input channels are available")
                native_rate = int(float(device.get("default_samplerate", 0)))
                if native_rate > 0:
                    sample_rates.insert(0, native_rate)
            except Exception:
                pass
        sample_rates = list(dict.fromkeys(sample_rates))
        last_error = None
        for sample_rate in sample_rates:
            try:
                if stream_factory is sd.InputStream:
                    # Validate the format before constructing a live AUHAL
                    # stream; macOS can report a device but reject it with
                    # PaErrorCode -9986 during stream startup.
                    sd.check_input_settings(
                        device=input_device,
                        samplerate=sample_rate,
                        channels=CHANNELS,
                        dtype="float32",
                    )
                with stream_factory(
                    samplerate=sample_rate,
                    device=input_device,
                    channels=CHANNELS,
                    dtype="float32",
                    blocksize=0,
                    latency="high",
                    callback=callback,
                ):
                    while not finished.wait(0.05):
                        if timeout is not None and time.monotonic() - started_at >= timeout:
                            print("[JARVIS] ⏱️ Startup clap gate timed out.")
                            return False
                break
            except Exception as exc:
                last_error = exc
                if finished.is_set():
                    break
        else:
            raise last_error or RuntimeError("no compatible microphone sample rate")
    except KeyboardInterrupt:
        print("\n[JARVIS] Startup cancelled.")
        return False
    except Exception as exc:
        print(f"[JARVIS] ❌ Startup clap microphone unavailable: {exc}")
        if os.environ.get("JARVIS_REQUIRE_CLAP_GATE", "").strip().lower() not in {"1", "true", "yes", "on"}:
            print("[JARVIS] ⚠️ Continuing without the clap gate; microphone input is unavailable.")
            print("[JARVIS] Restore microphone access to use voice input.")
            return True
        print("[JARVIS] Clap gate required. Set JARVIS_SKIP_CLAP_GATE=1 to bypass it.")
        return False

    print("[JARVIS] ⚡ Two claps detected. Powering up...")
    return True

def _get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set. Please set it to your Gemini API key.")
    return api_key


def _normalize_voice_name(voice_name: str | None) -> str:
    return normalize_gemini_voice(voice_name)


def _is_unsupported_voice_error(exc: Exception) -> bool:
    if not isinstance(exc, genai.errors.APIError):
        return False
    code = getattr(exc, "code", None)
    msg = str(exc).lower()
    if code == 1007:
        return "requested voice api_name" in msg and "not available for model" in msg
    return "requested voice api_name" in msg and "not available for model" in msg


def _load_voice_name() -> str:
    voice = os.environ.get("GEMINI_VOICE_NAME")
    if voice:
        return _normalize_voice_name(voice)
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return _normalize_voice_name(json.load(f).get("voice_name"))
    except Exception:
        return DEFAULT_VOICE_NAME


def _load_system_prompt() -> str:
    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
        return (
            LANGUAGE_RULE
            + "\n\n"
            + prompt
            + "\n\nDirígete al usuario por su nombre (flako) con respeto, de forma eficiente y directa, en español por defecto."
        )
    except Exception:
        return (
            LANGUAGE_RULE + "\n\n"
            "Eres AURORA, un asistente personal de IA. "
            "Sé conciso y directo, y usa siempre las herramientas disponibles para completar tareas. "
            "Nunca simules ni adivines resultados: llama a la herramienta adecuada. "
            "Dirígete al usuario por su nombre (flako) con respeto, de forma eficiente y directa, en español por defecto."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _pcm16_level(pcm) -> float:
    """Normalized 0..1 loudness (RMS) of a 16-bit PCM buffer, for UI display only."""
    try:
        import numpy as np
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 32768.0
        return min(1.0, (rms ** 0.5) * 2.0)
    except Exception:
        return 0.0


def _report_audio_level(ui, kind: str, pcm) -> None:
    """Forward a real audio level to the UI; never touches or stores the audio."""
    setter = getattr(ui, f"set_{kind}_audio_level", None)
    if callable(setter):
        try:
            setter(_pcm16_level(pcm))
        except Exception:
            pass


def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


def _merge_transcript_text(current: str, chunk: str) -> str:
    """Merge incremental or cumulative Live transcription updates safely."""
    current = " ".join(str(current or "").split()).strip()
    chunk = " ".join(str(chunk or "").split()).strip()
    if not current:
        return chunk
    if not chunk or chunk == current or current.endswith(chunk):
        return current
    if chunk.startswith(current):
        return chunk
    return f"{current} {chunk}".strip()

TOOL_DECLARATIONS = [
    {
        "name": "date_time",
        "description": (
            "Reads the real current date or time from the host system. Mandatory for every "
            "current-time/current-date question; never guess from model knowledge."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["current_time", "current_date"],
                    "description": "Whether the user asks for the current local time or date.",
                },
                "query": {"type": "STRING", "description": "Original user wording, if available."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "check_messages",
        "description": (
            "Reads the current Instagram or Apple Messages conversation and optionally searches Contacts. "
            "Use this before drafting a reply or when the user asks about recent messages."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {"type": "STRING", "description": "all | Instagram | iMessage | Contacts. Default: all."},
                "include_contacts": {"type": "BOOLEAN", "description": "Also search the user's Contacts."},
                "contact_query": {"type": "STRING", "description": "Optional spoken contact name to match."},
                "max_messages": {"type": "INTEGER", "description": "Maximum current-chat lines to inspect. Default: 30."}
            },
            "required": []
        }
    },
    {
        "name": "prepare_message_reply",
        "description": (
            "Creates an approval-gated message draft, approves the current pending draft, or cancels it. "
            "Never approve unless the user explicitly confirms the exact pending draft."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["prepare", "approve", "cancel"], "description": "Draft lifecycle action."},
                "platform": {"type": "STRING", "description": "Instagram, iMessage, WhatsApp, Telegram, or another supported platform."},
                "receiver": {"type": "STRING", "description": "Recipient name. Optional for the currently open chat."},
                "message_text": {"type": "STRING", "description": "Exact draft text, required for prepare."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_message",
        "description": (
            "Sends a user-authored message through iMessage, WhatsApp, Telegram, Instagram, Discord, or the current chat. "
            "For Instagram, the first call prepares a visible draft; use action=approve only after explicit user confirmation."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING", "enum": ["send", "approve", "cancel"], "description": "Default: send. Approve/cancel operates on the pending draft."},
                "receiver":     {"type": "STRING", "description": "Recipient contact name. Optional for current/focused chats and approval actions."},
                "message_text": {"type": "STRING", "description": "Exact message content. Required for send."},
                "platform":     {"type": "STRING", "description": "iMessage, WhatsApp, Telegram, Instagram, Discord, or current/focused."}
            },
            "required": ["platform"]
        }
    },
    {
        "name": "email_control",
        "description": (
            "Connects Gmail through Google OAuth, checks connection status, reads/searches Gmail, and prepares email. "
            "Gmail is the default provider; Apple Mail remains an optional macOS fallback. "
            "For Gmail, prepare opens a visible compose window and types To, Cc/Bcc, Subject, and Body in sequence. "
            "Every outgoing email is approval-gated: first call action=prepare, then call action=approve "
            "only after the user explicitly confirms the exact pending recipient, subject, and body."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["connect", "status", "disconnect", "inbox", "unread", "search", "read", "thread", "download_attachment", "create_draft", "list_drafts", "read_draft", "delete_draft", "prepare", "approve", "cancel"],
                    "description": "Email operation."
                },
                "provider": {
                    "type": "STRING",
                    "enum": ["gmail", "apple_mail", "default"],
                    "description": "Email provider. Default: gmail."
                },
                "browser": {
                    "type": "STRING",
                    "description": "Browser for the visible Gmail compose window. Default: chrome."
                },
                "credentials_path": {
                    "type": "STRING",
                    "description": "Path to a Google Desktop OAuth client JSON file, used only for connect."
                },
                "limit": {"type": "INTEGER", "description": "Maximum inbox/search results, 1-30."},
                "query": {"type": "STRING", "description": "Sender or subject text for search."},
                "message_id": {"type": "STRING", "description": "Message ID returned by inbox/search, required for read."},
                "thread_id": {"type": "STRING", "description": "Gmail thread ID required for thread retrieval."},
                "draft_id": {"type": "STRING", "description": "Gmail draft ID for read/delete draft."},
                "attachment_id": {"type": "STRING", "description": "Opaque Gmail attachment ID returned by read/thread."},
                "filename": {"type": "STRING", "description": "Attachment filename returned by Gmail."},
                "destination": {"type": "STRING", "description": "Existing user-selected directory for attachment download."},
                "attachments": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Local file paths to attach to a Gmail draft or approval-gated email."},
                "to": {"type": "STRING", "description": "Recipient email address or comma-separated addresses."},
                "cc": {"type": "STRING", "description": "Optional Cc addresses."},
                "bcc": {"type": "STRING", "description": "Optional Bcc addresses."},
                "subject": {"type": "STRING", "description": "Exact email subject for prepare."},
                "body": {"type": "STRING", "description": "Exact email body for prepare."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "reminder",
        "description": (
            "Create, list, cancel or modify ONE-TIME future reminders using the local OS scheduler. Use only for one "
            "future occurrence or when the user explicitly asks to be reminded once. Never use "
            "for recurring, daily, weekly, routine, automation, or 'from now on' requests; those "
            "must use lilith_routine. A reminder notifies the user and does not execute a Home "
            "Assistant device action."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "create | list | cancel | modify (default: create)"},
                "id":      {"type": "STRING", "description": "Safe reminder ID returned by create/list; required for cancel/modify"},
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "text":    {"type": "STRING", "description": "Natural Spanish one-shot time, e.g. 'mañana a las 9 de la noche' or 'en 30 minutos'"},
                "timezone":{"type": "STRING", "description": "IANA timezone; defaults to Europe/Madrid"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": []
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "media_control",
        "description": (
            "Controls music playback, primarily Spotify. Use when the user asks to play, resume, pause, "
            "stop, toggle, skip, or go back in Spotify, Apple Music, YouTube Music, or the active media player. "
            "Spotify is the default platform. Pass a song, artist, album, playlist, or Spotify link in query."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["play", "pause", "stop", "toggle", "next", "previous", "play_query", "volume_up", "volume_down", "set_volume", "mute", "unmute", "toggle_mute", "queue", "inspect_queue"],
                    "description": "Playback command. Use play_query to find a specific song or other item."
                },
                "platform": {
                    "type": "STRING",
                    "enum": ["spotify", "apple_music", "youtube_music", "system"],
                    "description": "Music platform. Default: spotify."
                },
                "query": {
                    "type": "STRING",
                    "description": "Song, artist, album, playlist, or Spotify link for play/play_query."
                },
                "volume": {"type": "INTEGER", "description": "Exact system volume percentage from 0 to 100 for set_volume."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer at the OS level: volume, brightness, window management, "
            "keyboard shortcuts, typing text on screen, closing app windows, fullscreen, "
            "dark mode, WiFi, restart, shutdown, scrolling, zoom, screenshots, lock screen, "
            "refresh/reload page. Use action='close_window' to close any OS window or named "
            "application. Use for ANY single OS-level command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform. Use close_tab only for a browser tab; use close_window for a named application window."},
                "app_name":    {"type": "STRING", "description": "Exact requested application name for close_window/close_app, for example 'Bloc de notas', 'Spotify', or 'Chrome'. Never infer it from the foreground window."},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls JARVIS's own Playwright-managed browser session. Use for: opening websites, "
            "searching the web, clicking elements, filling forms, scrolling, screenshots, navigation, "
            "any web-based automation task inside JARVIS's controlled browser. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously. "
            "IMPORTANT: close_tab here closes a tab in the JARVIS-controlled Playwright session ONLY — "
            "it does NOT close tabs in the user's native browser. To close the user's active OS/browser "
            "tab, use computer_settings with action='close_tab' instead."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages and opens local files and folders: open, list, create, delete, move, copy, rename, read, write, find, disk usage. Use action=open for a file path; do not use open_app for files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "open | list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files. Screen-debug only proposes a patch; applying it requires the returned approval token in a later call.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | optimize | screen_debug | apply_screen_fix | auto"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
                "approval_token": {"type": "STRING", "description": "Token returned by screen_debug; use only after explicit user approval"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds and tests contained multi-file projects, or performs explicit local Git status/diff/branch/create-branch/commit operations. Never pushes or discards changes.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING", "description": "build | git_status | git_diff | git_branch | git_create_branch | git_commit"},
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "project_root": {"type": "STRING", "description": "Existing absolute owner-approved root for Git operations"},
                "branch":       {"type": "STRING", "description": "New local branch name for git_create_branch"},
                "message":      {"type": "STRING", "description": "Commit message for git_commit; only already staged files are committed"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "graphics_quality",
        "description": "Changes JARVIS rendering quality between low, medium, and high.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "quality": {
                    "type": "STRING",
                    "enum": ["low", "medium", "high"],
                    "description": "Rendering quality preset."
                }
            },
            "required": ["quality"]
        }
    },
    {
        "name": "jarvis_ui_control",
        "description": (
            "Changes JARVIS's own interface. Use when the user asks to open or close the Command Center, "
            "change the theme or graphics quality, open settings, enter compact mode, toggle fullscreen, or show shortcuts."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["open_command_center", "close_command_center", "change_theme", "change_graphics_quality", "open_settings", "compact_mode", "fullscreen", "show_shortcuts"],
                    "description": "The interface action to perform."
                },
                "theme": {
                    "type": "STRING",
                    "enum": ["arc_reactor", "stealth_red", "vibranium_purple", "nanotech_gold", "platinum"],
                    "description": "Required for change_theme."
                },
                "graphics_quality": {
                    "type": "STRING",
                    "enum": ["low", "medium", "high"],
                    "description": "Required for change_graphics_quality. Low favors performance, medium is balanced, and high enables full visual detail."
                },
            },
            "required": ["action"]
        }
    },
    {
        "name": "deep_research",
        "description": (
            "Runs rigorous, multi-query web research and keeps the report in volatile memory unless the user asks to save it. "
            "Use when the user explicitly asks for deep, thorough, comprehensive, or source-backed research. "
            "On the first call, ask whether the user wants a background status bar or visible browser research. "
            "After completion, use this tool again to save the latest report or read it aloud."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "question": {
                    "type": "STRING",
                    "description": "The research question. Required on the initial ask call; optional when confirming a pending request."
                },
                "execution_mode": {
                    "type": "STRING",
                    "enum": ["ask", "background", "visible"],
                    "description": "Always use ask initially. Background shows a labeled status bar; visible opens a controlled browser and visits sources."
                },
                "result_action": {
                    "type": "STRING",
                    "enum": ["none", "save_files", "save_desktop", "read_report"],
                    "description": "Action for the latest completed in-memory report. Use only after the user chooses one of these options."
                },
                "depth": {
                    "type": "STRING",
                    "enum": ["quick", "standard", "deep"],
                    "description": "Research breadth. Default: standard."
                },
                "focus_areas": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional angles, constraints, or subtopics to prioritize."
                },
                "max_sources": {
                    "type": "INTEGER",
                    "description": "Maximum verified source links to retain, from 5 to 50."
                },
                "output_path": {
                    "type": "STRING",
                    "description": "Optional explicit path used only with save_files or save_desktop. Research never saves automatically."
                },
            },
            "required": []
        }
    },
    {
        "name": "create_presentation",
        "description": (
            "Creates, edits, redesigns, or extends an editable Microsoft PowerPoint (.pptx) presentation. "
            "Use this directly whenever the user asks to make a PowerPoint, presentation, "
            "slide deck, pitch deck, briefing deck, or slideshow. Do not use code_helper, "
            "file_processor, computer_control, or agent_task. First ask whether the user wants "
            "a native 3D model, then ask whether they want to see the task or keep it in the background."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {
                    "type": "STRING",
                    "description": "Subject, goal, and important content instructions. Required on the initial ask; optional when confirming the pending run mode."
                },
                "execution_mode": {
                    "type": "STRING",
                    "enum": ["ask", "background", "visible"],
                    "description": "Always use ask initially. Visible shows real build phases; background keeps a compact status indicator."
                },
                "mode": {
                    "type": "STRING",
                    "description": "auto | create | edit | redesign | extend. Default: auto."
                },
                "title": {
                    "type": "STRING",
                    "description": "Optional presentation title."
                },
                "audience": {
                    "type": "STRING",
                    "description": "Who will view the presentation, such as executives, investors, clients, or students."
                },
                "slide_count": {
                    "type": "INTEGER",
                    "description": "Final slide count from 3 to 50. Default: inferred or 8."
                },
                "tone": {
                    "type": "STRING",
                    "description": "Desired writing and visual tone, such as executive, persuasive, technical, or educational."
                },
                "theme": {
                    "type": "STRING",
                    "description": "Visual theme: jarvis_minimal | editorial | arc_reactor | executive | platinum. Default: jarvis_minimal."
                },
                "appearance": {
                    "type": "STRING",
                    "enum": ["auto", "light", "dark"],
                    "description": "Overall slide appearance. Honor light or dark when requested; auto uses the restrained dark JARVIS style."
                },
                "transition": {
                    "type": "STRING",
                    "enum": ["morph", "fade", "none"],
                    "description": "Native PowerPoint slide transition. Default: morph, with a fade fallback for older PowerPoint versions."
                },
                "source_file": {
                    "type": "STRING",
                    "description": "Backward-compatible single source path. Leave empty to use the uploaded file."
                },
                "source_files": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Source paths: PDF, Office files, data, text, images, audio, video, or PowerPoint."
                },
                "source_urls": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Specific source URLs supplied by the user."
                },
                "template_file": {
                    "type": "STRING",
                    "description": "Existing PPTX template or deck to preserve for edit/extend operations."
                },
                "model_source_file": {
                    "type": "STRING",
                    "description": "A PPTX used only as a native 3D model library. Its slides and text are not copied into the new presentation."
                },
                "use_native_3d": {
                    "type": "BOOLEAN",
                    "description": "The user's answer to the 3D-model question. Omit on the initial call unless the user already explicitly answered."
                },
                "three_d_mode": {
                    "type": "STRING",
                    "enum": ["ask", "yes", "no"],
                    "description": "Use ask on the initial call unless the user already explicitly requested or rejected 3D."
                },
                "quality": {
                    "type": "STRING",
                    "description": "fast | quality | premium. Default: quality."
                },
                "language": {
                    "type": "STRING",
                    "description": "Optional output language; otherwise infer from the request."
                },
                "allow_web_research": {
                    "type": "BOOLEAN",
                    "description": "Use broader web research. Set true only after the user explicitly permits web search."
                },
                "export_pdf": {
                    "type": "BOOLEAN",
                    "description": "Also export a PDF when Microsoft PowerPoint is available. Default: true."
                },
                "include_speaker_notes": {
                    "type": "BOOLEAN",
                    "description": "Generate editable speaker notes. Default: false."
                },
                "output_path": {
                    "type": "STRING",
                    "description": "Optional .pptx output path or destination folder."
                },
                "open_after_create": {
                    "type": "BOOLEAN",
                    "description": "Open the finished PowerPoint after creation. Default: false."
                },
            },
            "required": []
        }
    },
    {
        "name": "task_status",
        "description": "Checks or cancels background jobs, including presentation and deep-research jobs.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "get | all | cancel. Default: get."
                },
                "task_id": {
                    "type": "STRING",
                    "description": "Background task ID for get or cancel."
                },
            },
            "required": []
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save a LOCAL-ONLY operational note outside the active conversation. Call only when the "
            "user explicitly asks to save something locally; never auto-save an ordinary conversational fact. "
            "For persistent personal facts about the user (name, age, preferences, relationships, "
            "projects, wishes), use lilith_memory_store instead — LILITH is the canonical memory. "
            "Do NOT use this tool to store identity, preferences, relationships, or any personal "
            "knowledge. Those categories are restricted to LILITH. Never use this tool when the user "
            "explicitly asks to save, store, remember, or delete something in persistent memory. "
            "Do not call for recent numbers, names, the current project/topic, follow-up references, "
            "or anything already present in the active/restored conversation. "
            "Choose category and key internally; never ask the user for either. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "notes — runtime hints, session flags, operational context | "
                        "projects — ONLY active coding/task context, not user profile data"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. current_task, session_mode)"},
                "value": {"type": "STRING", "description": "Concise value in English"},
            },
            "required": ["value"]
        }
    },
    {
        "name": "local_memory_search",
        "description": (
            "Read/search SAVED JARVIS LOCAL-ONLY notes outside the active conversation. Use only when "
            "the user explicitly asks to search local memory, saved notes, or something previously stored. "
            "DO NOT CALL for facts in the active/restored conversation, what the user just said, recent "
            "numbers or names, the current project/topic, follow-up arithmetic, or pronoun/reference resolution. "
            "Do not use it for normal persistent personal memory; use lilith_memory_search for that. "
            "If you know the internal key from the prior local save, pass it; otherwise omit it and "
            "the tool returns the small local notes/projects set for semantic selection."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "Optional local category: notes or projects"
                },
                "key": {
                    "type": "STRING",
                    "description": "Optional exact local snake_case key, when known"
                },
                "query": {
                    "type": "STRING",
                    "description": "Optional natural-language description of the local fact"
                },
            },
            "required": []
        }
    },
    # ── LILITH integration tools (JL-W005) ─────────────────────────────
    {
        "name": "lilith_memory_search",
        "description": (
            "Search persistent long-term memory stored in LILITH, outside the active conversation. "
            "Use only when the user explicitly asks to search LILITH, persistent memory, or stored history. "
            "DO NOT CALL for facts in the active/restored conversation, what the user just said, recent "
            "numbers or names, the current project/topic, follow-up arithmetic, or pronoun/reference resolution. "
            "Returns real facts from LILITH's semantic memory database."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search text in natural language"},
                "limit": {"type": "INTEGER", "description": "Max results, 1-20. Default: 5"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "lilith_memory_store",
        "description": (
            "Store or update a personal fact in LILITH's persistent memory. "
            "Call only when the user explicitly asks for persistent storage; never auto-save a fact stated "
            "during ordinary conversation or anything already available in active/restored history. "
            "LILITH is the canonical source for personal knowledge about the user. "
            "Use a stable semantic key for each fact (e.g. favorite_color, birthday, pet_name). "
            "To CORRECT a fact, call this again with the SAME key and the new value — "
            "this upserts, replacing the old value. Do NOT delete-then-recreate. "
            "Do NOT use lilith_memory_delete to correct a fact — only to forget one. "
            "LILITH enforces restricted categories (identity, housing, beliefs, economy, psychology). "
            "Choose category and key internally and never ask the user for them. "
            "Value should be in the user's language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {
                    "type": "STRING",
                    "description": (
                        "Stable snake_case semantic identifier for this fact. "
                        "Use the SAME key when updating (e.g. favorite_color, birthday, city, pet_name, "
                        "sister_name). The key identifies WHAT attribute this is — the value is the current answer."
                    )
                },
                "value": {"type": "STRING", "description": "The fact value in the user's language (e.g. 'lila', 'Madrid', 'Luna')"},
                "category": {
                    "type": "STRING",
                    "description": (
                        "Memory category: preferences | family | pets | work | skills | projects | "
                        "places | relationships | devices | goals | events | health | habits"
                    )
                },
                "confidence": {"type": "NUMBER", "description": "0.0-1.0. Default: 1.0 for explicit user statements"},
                "description": {
                    "type": "STRING",
                    "description": (
                        "Natural-language phrase describing this fact in the user's language. "
                        "LILITH uses this to make the fact searchable. "
                        "Examples: 'color favorito', 'nombre del perro', 'ciudad donde vive'. "
                        "Always provide this when storing a fact."
                    )
                },
            },
            "required": ["value"]
        }
    },
    {
        "name": "lilith_memory_delete",
        "description": (
            "Delete a fact from LILITH's persistent memory. Use ONLY when the user "
            "explicitly asks to FORGET something entirely (e.g. 'forget my favorite color'). "
            "Do NOT use this to correct a fact — use lilith_memory_store with the same key instead. "
            "Resolve the stored fact naturally from the user's wording; never ask the user for its key. "
            "When already known internally, key format is category/attribute (e.g. preferences/favorite_color). "
            "LILITH only allows deleting facts JARVIS created."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING", "description": "The semantic key to delete (category/attribute, e.g. preferences/favorite_color)"},
                "reason": {"type": "STRING", "description": "Why: 'user_request' (explicit forget) or 'obsolete'"},
            },
            "required": []
        }
    },
    {
        "name": "lilith_home_action",
        "description": (
            "Control a smart home device NOW through LILITH and Home Assistant. Use only for an "
            "immediate action with no future or recurring schedule. If the request includes a "
            "recurring/persistent schedule, use lilith_routine instead and do NOT call this tool. "
            "Describe the device in natural language — LILITH resolves the real entity. "
            "Never invent entity IDs. Only turn_on and turn_off are supported. "
            "LILITH enforces safety rules and will reject prohibited actions. "
            "IMPORTANT: 'target' must contain ONLY the device name (e.g. 'bombilla habitación'), "
            "never brightness levels, percentages, or action words. "
            "To set brightness, pass brightness_pct in 'parameters'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {
                    "type": "STRING",
                    "description": (
                        "Device name only — no brightness, percentages, or action words. "
                        "Examples: 'bombilla habitación', 'luz del mueble', 'bombilla del salón'"
                    ),
                },
                "action": {
                    "type": "STRING",
                    "enum": ["turn_on", "turn_off", "toggle"],
                    "description": "The action to perform"
                },
                "parameters": {
                    "type": "OBJECT",
                    "description": (
                        "Optional action parameters. "
                        "For turn_on: brightness (0-255), brightness_pct (0-100), "
                        "color_temp, color_temp_kelvin, rgb_color, transition. "
                        "For turn_off: transition. "
                        "LILITH validates allowed parameters."
                    ),
                },
            },
            "required": ["target", "action"]
        }
    },
    {
        "name": "lilith_health",
        "description": (
            "Check LILITH system health and service status. "
            "Use when the user asks about LILITH, the smart home server, or system status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "lilith_runtime_status",
        "description": (
            "Read LILITH's real runtime status: health, autonomy, queue, AUT-6 "
            "motivation/satisfaction, goals, recent decisions/events, monitor, memory, "
            "Home Assistant and routine availability. Read-only; never executes actions."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "lilith_docs_list",
        "description": (
            "List real canonical LILITH documentation available through the safe "
            "read-only integration API. Use before reading if the exact path is unclear."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prefix": {"type": "STRING", "description": "Optional path prefix such as AI_MEMORY or docs/work_blocks"},
            },
            "required": []
        }
    },
    {
        "name": "lilith_docs_read",
        "description": (
            "Read one real canonical LILITH documentation file by path. Read-only. "
            "Allowed examples: ARCHITECTURE.md, PROJECT_STATE.md, TASKS.md, ROADMAP.md, "
            "CHANGELOG.md, AI_MEMORY/CURRENT.md, docs/work_blocks/WB-08_motor_de_decision.md."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Allowlisted documentation path to read"},
                "max_bytes": {"type": "INTEGER", "description": "Maximum bytes to return, default 80000"},
            },
            "required": ["path"]
        }
    },
    {
        "name": "lilith_docs_search",
        "description": (
            "Search real canonical LILITH documentation through the safe read-only "
            "integration API. Use for questions about roadmap, state, architecture, tasks, "
            "AI_MEMORY, or work-block docs."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Text to search for"},
                "limit": {"type": "INTEGER", "description": "Maximum files to return, 1-50"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "lilith_source_list",
        "description": (
            "List allowlisted real LILITH source, tests, scripts, migrations, docker-control "
            "and non-secret config files through the safe read-only integration API. "
            "Use before reading if the exact path is unclear."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prefix": {"type": "STRING", "description": "Optional path prefix such as core/routers, core/tests, scripts, migrations or docker-control"},
            },
            "required": []
        }
    },
    {
        "name": "lilith_source_read",
        "description": (
            "Read one allowlisted real LILITH source/tests/config file by path. Read-only. "
            "Allowed examples: core/routers/integration.py, core/tests/test_jarvis_integration.py, "
            "scripts/soak_aut5.py, core/database/migrations/0018_aut5_approval_id.sql, docker-compose.yml."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Allowlisted source/config path to read"},
                "max_bytes": {"type": "INTEGER", "description": "Maximum bytes to return, default 100000"},
            },
            "required": ["path"]
        }
    },
    {
        "name": "lilith_source_search",
        "description": (
            "Search allowlisted real LILITH source/tests/scripts/migrations/config through "
            "the safe read-only integration API. Does not run shell or inspect Git."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Text to search for"},
                "limit": {"type": "INTEGER", "description": "Maximum files to return, 1-50"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "lilith_git_status",
        "description": (
            "Read LILITH's local Git snapshot: branch, HEAD, origin/main, ahead/behind, "
            "dirty/untracked file names, diff stat and recent commits. Read-only; no fetch, "
            "push, checkout, patch contents or shell."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "lilith_command_submit",
        "description": (
            "Submit one canonical command envelope to LILITH with request/correlation id, "
            "source, intent, parameters, status and idempotency. Use only for the allowlisted "
            "LILITH intents; LILITH enforces authority, decision, resistance and audit rules."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "intent": {
                    "type": "STRING",
                    "enum": [
                        "runtime.status", "docs.list", "docs.read", "docs.search",
                        "source.list", "source.read", "source.search", "git.status",
                        "memory.search", "memory.store", "memory.delete",
                        "home.resolve", "home.entity", "home.action",
                        "home.request_approval", "home.resolve_approval",
                        "routines.create", "routines.list", "routines.get", "routines.update",
                        "routines.enable", "routines.disable", "routines.delete", "routines.history",
                    ],
                    "description": "Canonical LILITH intent to submit",
                },
                "parameters": {"type": "OBJECT", "description": "Intent-specific parameters"},
                "request_id": {"type": "STRING", "description": "Optional caller request id"},
                "correlation_id": {"type": "STRING", "description": "Optional end-to-end correlation id"},
                "idempotency_key": {"type": "STRING", "description": "Optional stable replay key"},
            },
            "required": ["intent"]
        }
    },
    {
        "name": "lilith_routine",
        "description": (
            "CREATE AND MANAGE PERSISTENT OR RECURRING ROUTINES in LILITH. This is the mandatory "
            "tool for requests equivalent to every day/daily/every morning/every night/every "
            "week/every Monday/every N hours or days/routine/automate/from now on, including "
            "todos los días/cada día/diariamente/cada mañana/cada noche/cada semana/todos los "
            "lunes/cada X horas o días/rutina/automatiza/a partir de ahora. For create, translate "
            "the requested action into the existing JL-A6 action_intent and action_parameters; "
            "for a light use home.action with entity/action parameters. Never also call reminder "
            "or lilith_home_action while defining the routine. Interpret 9 de la noche as 21:00 "
            "and 10 de la noche as 22:00. "
            "Normalize Madrid, hora de Madrid, mi zona horaria, or an omitted timezone to "
            "Europe/Madrid. Ask only when time, recurrence, target, or action is genuinely ambiguous. "
            "LILITH is authoritative: never claim created/updated/enabled/disabled/deleted unless "
            "status is completed."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "operation": {"type": "STRING", "enum": [
                    "create", "list", "get", "update", "enable", "disable", "delete", "history"
                ]},
                "routine_id": {"type": "INTEGER", "description": "Required except create/list"},
                "name": {"type": "STRING"},
                "description": {"type": "STRING"},
                "schedule_type": {"type": "STRING", "enum": ["manual", "once", "daily", "weekly", "interval"]},
                "schedule": {"type": "OBJECT", "description": "hour/minute, weekday, every_minutes or ISO run_at"},
                "timezone": {"type": "STRING", "description": "IANA timezone such as Europe/Madrid"},
                "action_intent": {"type": "STRING", "description": "Existing JL-A6 intent, e.g. home.action or runtime.status"},
                "action_parameters": {"type": "OBJECT"},
                "limit": {"type": "INTEGER", "description": "History limit, 1-100"},
            },
            "required": ["operation"]
        }
    },

    {
        "name": "system_status",
        "description": (
            "Read the server's current system status: CPU, RAM, swap, load, disk space, "
            "uptime, temperature, and network interfaces. Use when the user asks about "
            "the server, system health, resources, or performance. Read-only, no side effects."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "process_list",
        "description": (
            "List running processes sorted by memory usage. Optional filter by name. "
            "Use when the user asks what's running, or about a specific process. Read-only."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "filter": {
                    "type": "STRING",
                    "description": "Optional process name filter (case-insensitive substring match)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "process_info",
        "description": (
            "Get detailed info for a specific process by PID: CPU, memory, uptime, command. "
            "Read-only."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pid": {"type": "INTEGER", "description": "Process ID to inspect"},
            },
            "required": ["pid"],
        },
    },
    {
        "name": "systemd_status",
        "description": (
            "Check the status of a systemd user service. Only works for allowlisted services: "
            "jarvis-headless, jarvis-soak, lilith, lilith-worker, nginx, tailscaled. "
            "Returns active state, PID, restart count, start time. Read-only."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "service": {"type": "STRING", "description": "Service name (e.g. 'jarvis-headless')"},
            },
            "required": ["service"],
        },
    },
    {
        "name": "systemd_action",
        "description": (
            "Perform a mutating action on a systemd user service: restart, start, or stop. "
            "Only works for allowlisted services. REQUIRES USER CONFIRMATION before executing. "
            "First call returns a confirmation request; user must approve before execution."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "service": {"type": "STRING", "description": "Service name"},
                "action": {
                    "type": "STRING",
                    "enum": ["restart", "start", "stop"],
                    "description": "Action to perform",
                },
            },
            "required": ["service", "action"],
        },
    },
    {
        "name": "systemd_list_failed",
        "description": (
            "List all failed systemd user units. Use when the user asks about failed services "
            "or system problems. Read-only."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "journal_read",
        "description": (
            "Read recent log entries from an allowlisted systemd service journal. "
            "Supports filtering by priority and time. Max 100 lines. "
            "Allowlisted: jarvis-headless, jarvis-soak, lilith, lilith-worker, nginx, "
            "tailscaled, pulseaudio. Read-only. Secrets are automatically redacted."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "service": {"type": "STRING", "description": "Service name"},
                "lines": {"type": "INTEGER", "description": "Max lines to return (default 50, max 100)"},
                "priority": {
                    "type": "STRING",
                    "enum": ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"],
                    "description": "Filter by minimum priority level",
                },
                "since": {"type": "STRING", "description": "Show entries since (e.g. '1 hour ago', '2026-10-19')"},
            },
            "required": ["service"],
        },
    },
    {
        "name": "lilith_home_status",
        "description": (
            "Query the current state of a Home Assistant device or sensor through LILITH. "
            "Use for checking temperature, humidity, light state, switch state, presence, "
            "energy, battery, or any sensor value. Describe the device in natural language. "
            "Read-only — does not change any device state."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {
                    "type": "STRING",
                    "description": "Device or sensor name in natural language (e.g. 'temperatura salón', 'luz cocina', 'sensor humedad')",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "open_capabilities_catalog",
        "description": (
            "Opens the JARVIS capability catalog — a searchable generated list of "
            "everything JARVIS can do. Call this tool whenever the user asks to see "
            "JARVIS capabilities, abilities, skills, functions, or what JARVIS can do. "
            "Triggers: abre tus habilidades, muéstrame tus habilidades, abre tus "
            "capacidades, enséñame qué puedes hacer, abre la lista de funciones, "
            "show me your capabilities, what can you do, list your abilities. "
            "The catalog is refreshed automatically and opened in a text editor. "
            "Do NOT read the catalog aloud — just confirm it was opened."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["open", "refresh"],
                    "description": (
                        "open: refresh and open the catalog (default). "
                        "refresh: regenerate without opening."
                    ),
                },
            },
            "required": [],
        },
    },
]

# Tool names exposed by hosted clients. The names here are Gemini function
# declaration names (which differ from a few implementation module names).
CLOUD_SAFE_ACTIONS = frozenset({
    "web_search",
    "deep_research",
    "create_presentation",
    "flight_finder",
    "email_control",
    "youtube_video",
})

LOCAL_MACHINE_ONLY_ACTIONS = frozenset({
    "computer_control",
    "open_app",
    "file_controller",
    "media_control",
    "desktop_control",
    "computer_settings",
})

HEADLESS_ACTIONS = frozenset({
    "date_time",
    "system_status",
    "process_list",
    "process_info",
    "systemd_status",
    "systemd_action",
    "systemd_list_failed",
    "journal_read",
    "lilith_memory_search",
    "lilith_memory_store",
    "lilith_memory_delete",
    "lilith_home_action",
    "lilith_home_status",
    "lilith_health",

    "lilith_routine",
    "open_capabilities_catalog",
})


def get_tool_declarations(*, cloud_safe: bool = False, headless: bool = False) -> list[dict]:
    """Return the Gemini tools available for the requested runtime."""
    if headless:
        return [
            declaration
            for declaration in TOOL_DECLARATIONS
            if declaration.get("name") in HEADLESS_ACTIONS
        ]
    if not cloud_safe:
        return list(TOOL_DECLARATIONS)
    return [
        declaration
        for declaration in TOOL_DECLARATIONS
        if declaration.get("name") in CLOUD_SAFE_ACTIONS
    ]


class ConversationState(str, Enum):
    STANDBY = "STANDBY"
    CONNECTING = "CONNECTING"
    LISTENING = "LISTENING"
    RECONNECTING = "RECONNECTING"
    STOPPING = "STOPPING"


MAX_LIVE_RECONNECT_ATTEMPTS = 5
_INITIAL_HISTORY_UNSUPPORTED_MODELS = frozenset({
    # Verified against Gemini Developer API v1beta: these native-audio models
    # reject restored initial history and close the Live session (1007/1008).
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.5-flash-native-audio-latest",
})



_NON_SEMANTIC_PATTERN = re.compile(
    r"^[\s\.\,\;\:\!\?\-\—\…\<\>]*$"
    r"|^<noise>$"
    r"|^<silence>$"
    r"|^\[.*\]$",
    re.IGNORECASE,
)


def _strip_noise_tags(text: str) -> str:
    """Remove <noise>, <silence> tags from transcript, collapse whitespace."""
    if not text:
        return ""
    cleaned = _re_sub_noise(text)
    return " ".join(cleaned.split()).strip()

_re_sub_noise = lambda t: _RE_NOISE_TAG.sub("", t)
_RE_NOISE_TAG = re.compile(r"<noise>|<silence>", re.IGNORECASE)


def _is_semantic_transcript(text: str | None) -> bool:
    """Return True if the transcript contains real human speech content."""
    if not text:
        return False
    cleaned = text.strip()
    if not cleaned:
        return False
    if _NON_SEMANTIC_PATTERN.match(cleaned):
        return False
    if len(cleaned) <= 1 and not cleaned.isalnum():
        return False
    return True


class JarvisLive:

    def __init__(
        self,
        client: JarvisClient,
        voice_name: str = "Puck",
        *,
        cloud_safe: bool = False,
        headless: bool = False,
        no_audio: bool = False,
        api_key: str | None = None,
        external_audio: bool = False,
        conversation_store_path: Path | str | None = None,
    ):
        # Keep ``ui`` as a compatibility alias for desktop integrations that
        # already inspect JarvisLive.ui. The engine contract is JarvisClient.
        self.client         = client
        self.ui             = client
        self.cloud_safe     = bool(cloud_safe)
        self.headless       = bool(headless)
        self.no_audio       = bool(no_audio)
        self.external_audio = bool(external_audio)
        if self.headless and not self.no_audio:
            self._audio_input_device_resolver = _headless_input_device
            self._audio_output_device_id = _resolve_device_by_name(
                "output", _HEADLESS_OUTPUT_HINTS,
                required_rate=RECEIVE_SAMPLE_RATE,
            )
        self._api_key       = api_key.strip() if isinstance(api_key, str) else None
        self.tool_declarations = get_tool_declarations(
            cloud_safe=self.cloud_safe, headless=self.headless,
        )
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._playback_stream_lock = threading.Lock()
        self._barge_in_gate = SpeechAwareBargeInGate(input_sample_rate=SEND_SAMPLE_RATE)
        self._barge_in_candidate_logged = False
        self._local_barge_in_active = False
        self._suppress_interrupted_output = False
        self._active_turn_id: str | None = None
        self._turn_interrupted = False
        self._turn_tool_signatures: set[str] = set()
        self._last_interrupted_turn: dict | None = None
        self._barge_in_last_reject_log = 0.0
        self._audio_input_worker_lock = threading.Lock()
        self._audio_input_device_id: int | None = None
        self.voice_name     = voice_name
        self._date_time_authority = DateTimeAuthority()
        # optional runtime limit in seconds (set by main)
        self.runtime_limit_seconds: int | None = None
        # optional path that must exist (e.g. a mounted encrypted volume)
        self.required_unlock_path: str | None = None
        self.required_unlock_secret: str | None = None
        self.ui.on_text_command = self._on_text_command
        self._voice_changed  = threading.Event()
        self._turn_done_event: asyncio.Event | None = None
        self._tts_engine = None
        self._ext_tts_provider = ""
        self._ext_tts_voice_id = ""
        self._ext_tts_api_key = ""
        self._current_input_transcript = ""
        self._last_input_transcript = ""
        self._last_input_transcript_at = 0.0
        self._schedule_guard_routed = False
        self._schedule_session_id = uuid.uuid4().hex[:12]
        self._schedule_turn_sequence = 0
        self._schedule_turn_id = ""
        self._schedule_turn_source = ""
        self._schedule_call_turns: dict[str, str] = {}
        self._pending_routine: PendingRoutineState | None = None
        self._routine_confirmation: PendingRoutineConfirmation | None = None
        self._memory_call_turns: dict[str, str] = {}
        self._memory_consumed_call_ids: set[str] = set()
        self._memory_turn_effects: set[tuple[str, str, str]] = set()
        self._memory_key_aliases: dict[str, str] = {}
        # Explicitly local/session memory is process-local RAM only. It must not
        # survive a JarvisLive restart and must never use the persistent memory manager.
        self._local_session_memory: dict[str, dict[str, dict[str, str]]] = {
            "notes": {},
            "projects": {},
        }
        self._pending_self_quit = False
        self._pending_self_quit_farewell_received = False
        self._self_quit_timer = None
        self._shutdown_requested = threading.Event()
        self._conversation_requested = threading.Event()
        self._conversation_state = ConversationState.STANDBY
        self._conversation_lock = threading.RLock()
        self._live_runner_lock = threading.Lock()
        self._conversation_store = (
            ConversationStore(conversation_store_path)
            if conversation_store_path is not None and not self.cloud_safe
            else None
        )
        persisted_conversation = (
            self._conversation_store.load()
            if self._conversation_store is not None
            else empty_conversation_state()
        )
        self._conversation_id = persisted_conversation["conversation_id"]
        self._conversation_continuity = list(persisted_conversation["recent_turns"])
        self._rolling_conversation_summary = persisted_conversation["summary"]
        self._recent_conversation_tool_results = list(
            persisted_conversation["recent_tool_results"]
        )
        self._conversation_metadata = dict(persisted_conversation["metadata"])
        # Gemini handles are deliberately process-local transport state. Durable
        # continuity comes from the local store, never from an opaque token.
        self._session_resumption_handle: str | None = None
        self._session_resumption_handle_at: float | None = None
        self._logical_conversation_started = bool(
            self._conversation_continuity
            or self._rolling_conversation_summary
            or self._recent_conversation_tool_results
        )
        self._resume_from_local_continuity = self._logical_conversation_started
        if self._logical_conversation_started:
            print(
                "[JARVIS] Durable conversation loaded: "
                f"{len(self._conversation_continuity)} turns, logical conversation preserved."
            )
        self._tour_active = False
        # JL-W003: optional LILITH bridge for typed input (None when not configured).
        self._lilith: LilithBridge | None = None
        self.ui.on_conversation_toggle = self.toggle_conversation
        self.ui.set_state(ConversationState.STANDBY.value)

    @property
    def conversation_state(self) -> ConversationState:
        with self._conversation_lock:
            return self._conversation_state

    def _set_conversation_state(self, state: ConversationState) -> bool:
        with self._conversation_lock:
            if (
                self._conversation_state == ConversationState.STOPPING
                and state != ConversationState.STANDBY
            ):
                return False
            self._conversation_state = state
        self.ui.set_state(state.value)
        return True

    def toggle_conversation(self) -> bool:
        if self._conversation_requested.is_set():
            return self.stop_conversation()
        return self.start_conversation()

    def start_conversation(self) -> bool:
        """Resume the current logical conversation without blocking the UI."""
        with self._conversation_lock:
            if (
                self._shutdown_requested.is_set()
                or self._conversation_requested.is_set()
                or self._conversation_state != ConversationState.STANDBY
            ):
                return False
            self._conversation_requested.set()
            self._conversation_state = ConversationState.CONNECTING
        self.ui.set_state(ConversationState.CONNECTING.value)
        return True

    def stop_conversation(self) -> bool:
        """Cooperatively stop only the active Gemini session and its tasks."""
        with self._conversation_lock:
            if (
                not self._conversation_requested.is_set()
                and self._conversation_state == ConversationState.STANDBY
                and self.session is None
            ):
                return False
            # Stop wins: publish the inactive request before touching the session.
            self._conversation_requested.clear()
            self._conversation_state = ConversationState.STOPPING
        self.ui.set_state(ConversationState.STOPPING.value)
        loop = self._loop
        if loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._close_live_session(), loop)
            except RuntimeError:
                pass
        return True

    def new_conversation(self) -> bool:
        """Explicitly replace the logical conversation and its local continuity."""
        with self._conversation_lock:
            if self._conversation_requested.is_set() or self.session is not None:
                return False
            try:
                new_state = (
                    self._conversation_store.new_conversation()
                    if self._conversation_store is not None
                    else empty_conversation_state()
                )
            except (OSError, ValueError, TypeError) as exc:
                print(
                    "[JARVIS] ⚠️ New conversation was not created because the "
                    f"continuity store could not be replaced: {type(exc).__name__}"
                )
                return False
            self._conversation_id = new_state["conversation_id"]
            self._conversation_continuity = list(new_state["recent_turns"])
            self._rolling_conversation_summary = new_state["summary"]
            self._recent_conversation_tool_results = list(new_state["recent_tool_results"])
            self._conversation_metadata = dict(new_state["metadata"])
            self._session_resumption_handle = None
            self._session_resumption_handle_at = None
            self._logical_conversation_started = False
            self._resume_from_local_continuity = False
        return True

    def _conversation_store_state(self) -> dict:
        return {
            "schema_version": 1,
            "conversation_id": self._conversation_id,
            "summary": self._rolling_conversation_summary,
            "recent_turns": list(self._conversation_continuity),
            "recent_tool_results": list(self._recent_conversation_tool_results),
            "metadata": dict(self._conversation_metadata),
        }

    def _persist_conversation_state(self) -> None:
        if self._conversation_store is None:
            return
        with self._conversation_lock:
            try:
                saved = self._conversation_store.save(self._conversation_store_state())
            except (OSError, ValueError, TypeError) as exc:
                print(
                    "[JARVIS] ⚠️ Conversation continuity save failed: "
                    f"{type(exc).__name__}"
                )
                return
            self._conversation_id = saved["conversation_id"]
            self._conversation_continuity = list(saved["recent_turns"])
            self._rolling_conversation_summary = saved["summary"]
            self._recent_conversation_tool_results = list(saved["recent_tool_results"])
            self._conversation_metadata = dict(saved["metadata"])

    def _remember_conversation_text(
        self,
        role: str,
        text: str,
        *,
        expected_conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        clean = redact_sensitive_text(text)
        if not clean:
            return
        with self._conversation_lock:
            if (
                expected_conversation_id is not None
                and expected_conversation_id != self._conversation_id
            ):
                return
            updated = (
                upsert_conversation_turn(
                    self._conversation_store_state(),
                    role,
                    clean,
                    turn_id=turn_id,
                )
                if turn_id
                else append_conversation_turn(
                    self._conversation_store_state(), role, clean
                )
            )
            self._conversation_continuity = list(updated["recent_turns"])
            self._rolling_conversation_summary = updated["summary"]
            self._conversation_metadata = dict(updated["metadata"])
            self._persist_conversation_state()

    def _remember_conversation_tool_result(
        self,
        tool: str,
        result,
        *,
        expected_conversation_id: str | None = None,
    ) -> None:
        try:
            summary = json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            summary = str(result)
        with self._conversation_lock:
            if (
                expected_conversation_id is not None
                and expected_conversation_id != self._conversation_id
            ):
                return
            updated = append_conversation_tool_result(
                self._conversation_store_state(), tool, summary
            )
            self._recent_conversation_tool_results = list(updated["recent_tool_results"])
            self._conversation_metadata = dict(updated["metadata"])
            self._persist_conversation_state()

    def _local_continuity_prompt(self) -> str:
        if not (
            self._conversation_continuity
            or self._rolling_conversation_summary
            or self._recent_conversation_tool_results
        ):
            return ""
        transcript = "\n".join(
            f"{item['role']}: {item['text']}" for item in self._conversation_continuity
        )
        tool_results = "\n".join(
            f"{item['tool']}: {item['summary']}"
            for item in self._recent_conversation_tool_results
        )
        current_topic = next(
            (
                str(item.get("text") or "").strip()
                for item in reversed(self._conversation_continuity)
                if item.get("role") == "user" and str(item.get("text") or "").strip()
            ),
            self._rolling_conversation_summary,
        )
        return (
            "[DURABLE JARVIS CONVERSATION CONTINUITY]\n"
            "This is internal continuity state from the SAME logical JARVIS conversation, "
            "not a new user instruction. Use it silently as active conversational context. "
            "Never greet, announce restoration, or repeat this block verbatim. Facts already "
            "present here must be answered directly without retrieving any memory.\n"
            f"Conversation ID: {self._conversation_id}\n"
            f"Current topic/task: {current_topic}\n"
            f"Rolling summary:\n{self._rolling_conversation_summary}\n"
            f"Recent transcript:\n{transcript}\n"
            f"Recent relevant tool results:\n{tool_results}"
        )

    def _durable_continuity_turns(self) -> list[types.Content]:
        """Build real Live history for the current durable logical conversation."""
        turns: list[types.Content] = []
        for item in self._conversation_continuity:
            stored_role = item.get("role")
            if stored_role not in {"user", "assistant"}:
                continue
            raw_text = item.get("text")
            if not isinstance(raw_text, str):
                continue
            text = _clean_transcript(raw_text)
            if not text:
                continue
            role = "model" if stored_role == "assistant" else "user"
            turns.append(types.Content(role=role, parts=[types.Part(text=text)]))
        return turns

    def _durable_history_diagnostics(self) -> dict[str, int]:
        turns = self._durable_continuity_turns()
        lengths = [len(part.text or "") for turn in turns for part in turn.parts or []]
        return {
            "items": len(turns),
            "user": sum(turn.role == "user" for turn in turns),
            "model": sum(turn.role == "model" for turn in turns),
            "empty": sum(not (part.text or "").strip() for turn in turns for part in turn.parts or []),
            "max_chars": max(lengths, default=0),
            "total_chars": sum(lengths),
        }

    async def _restore_durable_continuity(self, session) -> None:
        """Prefill Live history before any normal realtime input can begin."""
        logger.info(
            "LIVE_SESSION context_restore turns=%d summary_len=%d",
            len(self._conversation_continuity),
            len(self._rolling_conversation_summary or ""),
        )
        print("[JARVIS] Restoring durable conversation context into Live session.")
        turns = self._durable_continuity_turns()
        if turns:
            # HistoryConfig makes this a history handshake: completing it does
            # not trigger a model response and unlocks subsequent realtime input.
            await session.send_client_content(turns=turns, turn_complete=True)
            websocket = getattr(session, "_ws", None)
            wait_closed = getattr(websocket, "wait_closed", None)
            if callable(wait_closed):
                try:
                    await asyncio.wait_for(wait_closed(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
                else:
                    code = getattr(websocket, "close_code", None)
                    reason = str(getattr(websocket, "close_reason", "") or "")
                    if code == 1007 or "invalid argument" in reason.lower():
                        raise InitialHistoryRejected(
                            "Gemini API 1007 rejected initial history"
                        )
                    raise RecoverableLiveDisconnect(
                        f"Live transport closed during initial history ({code})"
                    )
        print("[JARVIS] Durable conversation context restored.")

    async def _close_live_session(self) -> None:
        out_queue = self.out_queue
        if out_queue is not None:
            try:
                out_queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        session = self.session
        if session is not None:
            try:
                await session.close()
            except Exception as exc:
                print(f"[JARVIS] ⚠️ Conversation close failed: {exc}")

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(self.send_text(text), self._loop)

    async def send_text(self, text: str) -> bool:
        """Send a text turn from either the desktop callback or a web client."""
        if not self.session:
            return False
        self._current_input_transcript = str(text or "").strip()
        if not self._current_input_transcript:
            return False
        self._begin_schedule_turn(self._current_input_transcript, "text")
        self._last_input_transcript = self._current_input_transcript
        self._last_input_transcript_at = time.monotonic()
        self._remember_conversation_text("user", self._current_input_transcript)
        outgoing_text = self._current_input_transcript
        authority = getattr(self, "_date_time_authority", None)
        if authority is None:
            authority = self._date_time_authority = DateTimeAuthority()
        authoritative_date_time = authority.answer(self._current_input_transcript)
        if authoritative_date_time:
            outgoing_text = (
                "[AUTHORITATIVE HOST DATE/TIME] "
                f'Di exactamente en español: "{authoritative_date_time}" '
                "No calcules ni adivines la fecha o la hora y no llames a ninguna herramienta."
            )
        if (
            not getattr(self, "_pending_self_quit", False)
            and self._is_explicit_self_quit_transcript(self._current_input_transcript)
        ):
            self._queue_self_quit_after_farewell()
            outgoing_text = (
                "[VERIFIED LOCAL SELF-SHUTDOWN] El usuario pidió explícitamente que te cierres. "
                f'Di exactamente (en español): "{SELF_QUIT_GOODBYE}" No llames a ninguna herramienta y no digas nada más.'
            )
        # JL-W003: offer ordinary typed text to LILITH first. Only when LILITH actually
        # executed it is Gemini skipped; every other case continues unchanged below.
        if outgoing_text == self._current_input_transcript and await self._offer_typed_to_lilith(outgoing_text):
            return True
        await self.session.send_client_content(
            turns={"parts": [{"text": outgoing_text}]},
            turn_complete=True,
        )
        return True

    async def _offer_typed_to_lilith(self, text: str) -> bool:
        """True if LILITH executed the typed text (do not also send it to Gemini)."""
        bridge = getattr(self, "_lilith", None)
        if bridge is None:
            return False
        outcome = await bridge.route_typed(text)
        if outcome.notice:
            self.ui.write_log(f"SYS: {outcome.notice}")
        if not outcome.handled:
            return False
        self.ui.write_log(f"LILITH: {outcome.message}")
        return True

    async def send_audio_chunk(
        self,
        data: bytes,
        mime_type: str = "audio/pcm;rate=16000",
    ) -> bool:
        """Queue browser-captured PCM for the active Gemini Live session."""
        if not data or self.out_queue is None or self._shutdown_requested.is_set():
            return False
        await self.out_queue.put({"data": data, "mime_type": mime_type})
        return True

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            previous = getattr(self, "_is_speaking", False)
            self._is_speaking = value
        gate = getattr(self, "_barge_in_gate", None)
        if gate is not None and value != previous:
            if value:
                gate.start_playback()
                self._barge_in_candidate_logged = False
            else:
                gate.stop_playback()
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str) -> bool:
        if not self._loop or not self.session:
            return False
        try:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )
            return True
        except Exception:
            return False

    def _speak_vision_result(self, text: str) -> bool:
        """Send finished vision text through JARVIS's active voice session."""
        result = " ".join(str(text or "").split())
        if not result:
            return False
        directive = (
            "[INTERNAL VISION OUTPUT] Lee al usuario, en español, el siguiente resultado de visión "
            "(tradúcelo si está en inglés). No añadas introducción, comentarios ni llames a herramientas. "
            f"Vision result: {json.dumps(result, ensure_ascii=False)}"
        )
        return self.speak(directive)

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Perdona, {tool_name} ha dado un error. {short}")

    @staticmethod
    def _is_explicit_self_quit_transcript(text: str) -> bool:
        """Only match commands that clearly target JARVIS, never the computer."""
        normalized = " ".join(str(text or "").lower().split())
        if not normalized:
            return False
        if re.search(r"\b(?:computer|mac|pc|system|machine)\b", normalized):
            return False
        if re.search(r"\b(?:stop talking|be quiet|cancel|never mind)\b", normalized):
            return False
        if normalized in {
            "quit", "exit", "shutdown", "shut down", "turn off", "power down",
            "go offline", "goodbye jarvis", "goodbye jarvis please",
        }:
            return True
        return any(pattern.search(normalized) for pattern in _SELF_QUIT_PATTERNS)

    def _queue_self_quit_after_farewell(self) -> None:
        """Arm shutdown without closing until the response audio is fully drained."""
        self._pending_self_quit = True
        self._pending_self_quit_farewell_received = False
        try:
            self.ui.write_log("SYS: Apagado en espera; esperando la despedida de AURORA.")
        except Exception:
            pass
        # A voice model can occasionally omit audio/turn_complete. Do not
        # leave the user with a permanently armed shutdown in that case.
        try:
            if self._self_quit_timer is not None:
                self._self_quit_timer.cancel()
            self._self_quit_timer = threading.Timer(8.0, self._force_complete_self_quit)
            self._self_quit_timer.daemon = True
            self._self_quit_timer.start()
        except Exception:
            pass

    def _force_complete_self_quit(self) -> None:
        if not getattr(self, "_pending_self_quit", False):
            return
        self._pending_self_quit_farewell_received = True
        self._complete_self_quit_after_audio()

    def _mark_self_quit_farewell_received(self) -> None:
        if getattr(self, "_pending_self_quit", False):
            self._pending_self_quit_farewell_received = True

    def _complete_self_quit_after_audio(self) -> bool:
        """Close through the UI only after a farewell turn has actually completed."""
        if not (
            getattr(self, "_pending_self_quit", False)
            and getattr(self, "_pending_self_quit_farewell_received", False)
        ):
            return False
        self._pending_self_quit = False
        self._pending_self_quit_farewell_received = False
        if getattr(self, "_self_quit_timer", None) is not None:
            self._self_quit_timer.cancel()
            self._self_quit_timer = None
        self.request_shutdown()
        self.ui.handle_ui_command("Quit JARVIS")
        return True

    def request_shutdown(self) -> None:
        """Stop live tasks and make the process exit after the UI closes."""
        shutdown_requested = getattr(self, "_shutdown_requested", None)
        if shutdown_requested is None:
            self._shutdown_requested = threading.Event()
            shutdown_requested = self._shutdown_requested
        if shutdown_requested.is_set():
            return
        try:
            self._persist_conversation_state()
        except Exception as exc:
            print(f"[JARVIS] ⚠️ Conversation continuity save failed: {type(exc).__name__}")
        shutdown_requested.set()
        conversation_requested = getattr(self, "_conversation_requested", None)
        if conversation_requested is not None:
            conversation_requested.clear()
        try:
            session = getattr(self, "session", None)
            loop = getattr(self, "_loop", None)
            if session is not None and loop is not None:
                asyncio.run_coroutine_threadsafe(session.close(), loop)
            out_queue = getattr(self, "out_queue", None)
            if out_queue is not None:
                out_queue.put_nowait(None)
        except Exception as exc:
            print(f"[JARVIS] ⚠️ Shutdown session close failed: {exc}")

    def set_tour_active(self, active: bool) -> None:
        """Track whether the desktop introduction temporarily owns the UI."""
        self._tour_active = bool(active)

    async def _wait_before_reconnect(self, delay: float) -> None:
        deadline = time.monotonic() + max(0.0, float(delay))
        while (
            not self._shutdown_requested.is_set()
            and self._conversation_requested.is_set()
        ):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))

    def _intercept_ui_tool_call(self, name: str, args: dict) -> str | None:
        """Safety net for stale models that attempt the removed quit tool action."""
        action = str(args.get("action") or "").strip().lower()
        if name != "shutdown_jarvis" and not (
            name == "jarvis_ui_control" and action == "quit_jarvis"
        ):
            return None

        transcript = str(getattr(self, "_current_input_transcript", "") or "")
        if not transcript:
            age = time.monotonic() - float(getattr(self, "_last_input_transcript_at", 0.0) or 0.0)
            if age <= 5.0:
                transcript = str(getattr(self, "_last_input_transcript", "") or "")

        if not self._is_explicit_self_quit_transcript(transcript):
            return "Ignored an unverified shutdown request. JARVIS remains online."

        self._queue_self_quit_after_farewell()
        return f'Shutdown queued. Say exactly: "{SELF_QUIT_GOODBYE}"'

    def update_voice(self, voice_name: str):
        self.voice_name = _normalize_voice_name(voice_name)
        self.ui.write_log(f"SYS: Cambio de voz solicitado: {self.voice_name}")
        try:
            self.ui.sync_voice_display(self.voice_name)
        except Exception:
            pass
        if self.session and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self.session.close(), self._loop)
            except Exception as e:
                print(f"[JARVIS] ⚠️ Could not close session after voice change: {e}")

    def _get_current_voice(self) -> str:
        if getattr(self, "voice_name", None):
            return _normalize_voice_name(self.voice_name)
        voice_combo = getattr(self.ui, "_voice_combo", None)
        if voice_combo is not None:
            idx = voice_combo.currentIndex()
            if idx >= 0:
                voice = voice_combo.itemData(idx)
                if isinstance(voice, str) and voice:
                    return _normalize_voice_name(voice)
            voice = voice_combo.currentText().strip().lower()
            if voice in SUPPORTED_VOICE_NAMES:
                return voice
        return _load_voice_name()

    async def _announce_startup(self):
        try:
            memory = load_memory()
            name_entry = memory.get("identity", {}).get("name")
            name = None
            if isinstance(name_entry, dict):
                name = name_entry.get("value")
            elif isinstance(name_entry, str):
                name = name_entry
            if name:
                greeting = f"Hola, soy {name}. Salúdame brevemente."
            else:
                greeting = "Hola. Salúdame brevemente."
            await self.session.send_client_content(
                turns={"parts": [{"text": greeting}]},
                turn_complete=True,
            )
        except Exception as e:
            print(f"[JARVIS] ⚠️ Greeting failed: {e}")

    _CONTEXT_SKIP_CATEGORIES = frozenset({
        "jarvis_fact", "project_status", "conversation_summary", "signal",
    })
    _CONTEXT_PRIORITY = (
        "identity", "preferences", "work", "family", "pets", "goals",
        "projects", "places", "housing", "skills", "hobbies",
    )
    _CONTEXT_MAX_CHARS = 3000

    @staticmethod
    def _format_lilith_context(ctx: dict) -> str:
        """Format LILITH personal knowledge into a system-prompt block.

        Filters out operational/test categories and prioritises identity-first.
        Truncates at line boundaries to avoid cutting mid-fact.
        """
        categories = ctx.get("categories", {})
        if not categories:
            return ""

        skip = JarvisLive._CONTEXT_SKIP_CATEGORIES
        cats = {c: fs for c, fs in categories.items() if c not in skip and fs}
        if not cats:
            return ""

        ordered = []
        for c in JarvisLive._CONTEXT_PRIORITY:
            if c in cats:
                ordered.append((c, cats.pop(c)))
        for c in sorted(cats):
            ordered.append((c, cats[c]))

        header = "[LILITH PERSISTENT MEMORY — authoritative facts about this person]\n"
        lines = [header]
        budget = JarvisLive._CONTEXT_MAX_CHARS - len(header)
        for cat, facts in ordered:
            section = [f"{cat.replace('_', ' ').title()}:"]
            for f in facts[:12]:
                val = f.get("value", "")
                if val:
                    section.append(f"  - {val}")
            section.append("")
            block = "\n".join(section)
            if len(block) > budget:
                break
            lines.append(block)
            budget -= len(block) + 1
        return "\n".join(lines)

    def _build_config(
        self,
        *,
        lilith_context: dict | None = None,
        resumption_handle: str | None = None,
        local_continuity: str = "",
        initial_history: bool = False,
        live_model_id: str = "",
    ) -> types.LiveConnectConfig:
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)

        if getattr(self, "headless", False):
            parts = [
                LANGUAGE_RULE,
                DATE_TIME_AUTHORITY_RULE,
                HEADLESS_SYSTEM_RULES,
                ROUTINE_ROUTING_RULES,
                MEMORY_ROUTING_RULES,
                TOOL_RESULT_TRUTH_RULE,
            ]
            sys_prompt = ""
        else:
            sys_prompt = _load_system_prompt()
            parts = [
                LANGUAGE_RULE,
                DATE_TIME_AUTHORITY_RULE,
                ROUTINE_ROUTING_RULES,
                MEMORY_ROUTING_RULES,
                TOOL_RESULT_TRUTH_RULE,
            ]
        lilith_is_authoritative = False
        if lilith_context:
            lilith_str = self._format_lilith_context(lilith_context)
            if lilith_str:
                parts.append(lilith_str)
                lilith_is_authoritative = True
        if lilith_is_authoritative:
            _LOCAL_PERSONAL_CATEGORIES = {"identity", "preferences", "relationships", "wishes"}
            stripped = {k: v for k, v in memory.items() if k not in _LOCAL_PERSONAL_CATEGORIES}
            mem_str = format_memory_for_prompt(stripped)
        if mem_str:
            parts.append(mem_str)
        if sys_prompt:
            parts.append(sys_prompt)
        if local_continuity:
            # Keep active-conversation continuity after generic routing rules so
            # immediate history wins without forcing a persistent-memory lookup.
            parts.append(local_continuity)
        parts.append(LANGUAGE_RULE)  # repeated near the end: recency keeps the rule in force
        parts.append(TOOL_RESULT_TRUTH_RULE)
        parts.append(
            HEADLESS_CURRENT_CONVERSATION_PRECEDENCE
            if getattr(self, "headless", False)
            else CURRENT_CONVERSATION_PRECEDENCE
        )

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{
                "function_declarations": getattr(
                    self,
                    "tool_declarations",
                    TOOL_DECLARATIONS,
                )
            }],
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=LIVE_VAD_SILENCE_MS,
                ),
                activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            ),
            thinking_config=(
                None if "3.8-live" in live_model_id
                else types.ThinkingConfig(thinking_budget=0)
            ),
            session_resumption=types.SessionResumptionConfig(handle=resumption_handle),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
            history_config=(
                types.HistoryConfig(initial_history_in_client_content=True)
                if initial_history
                else None
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self._get_current_voice()
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        if getattr(self, "cloud_safe", False) and name not in CLOUD_SAFE_ACTIONS:
            try:
                from core.green.runtime import emit_tool_rejected
                emit_tool_rejected(tool_name=name, function_call_id=fc.id, reason="cloud_safe")
            except Exception:
                pass
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={
                    "result": (
                        f"Tool '{name}' is unavailable in cloud-safe mode."
                    )
                },
            )

        if getattr(self.ui, "operational_ready", True) is False:
            try:
                from core.green.runtime import emit_tool_rejected
                emit_tool_rejected(tool_name=name, function_call_id=fc.id, reason="not_ready")
            except Exception:
                pass
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": "Startup sequence active. Try this action again when JARVIS is ready."},
            )

        from core.qa_mode import guard_tool_call, qa_block_message

        qa_decision = guard_tool_call(name, args)
        if not qa_decision.allowed:
            try:
                from core.green.runtime import emit_tool_rejected
                emit_tool_rejected(tool_name=name, function_call_id=fc.id, reason="qa_blocked")
            except Exception:
                pass
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": qa_block_message(qa_decision)},
            )

        # GREEN: trace + event for authorized tool execution
        _green_trace = None
        try:
            from core.green.runtime import trace_tool_start, emit_tool_authorized
            emit_tool_authorized(tool_name=name, function_call_id=fc.id)
            _green_trace = trace_tool_start(
                tool_name=name,
                tool_arguments=args,
                function_call_id=fc.id,
                session_id=getattr(self, "_schedule_session_id", None),
                turn_id=getattr(self, "_schedule_turn_id", None),
            )
        except Exception:
            pass

        print(f"[JARVIS] 🔧 {name}  {args}")
        logger.info("TOOL_CALL  %s  args=%s", name, args)
        self.ui.set_state("THINKING")

        intercepted = self._intercept_ui_tool_call(name, args)
        if intercepted is not None:
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": intercepted}
            )

        if name == "save_memory":
            _SAVE_MEMORY_BLOCKED_CATEGORIES = frozenset({
                "identity", "preferences", "relationships", "wishes",
            })
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if category in _SAVE_MEMORY_BLOCKED_CATEGORIES:
                print(f"[Memory] 🚫 save_memory BLOCKED: {category}/{key} — use lilith_memory_store")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={
                        "result": (
                            f"Category '{category}' is restricted to LILITH persistent memory. "
                            f"Use lilith_memory_store instead to save personal facts."
                        )
                    }
                )
            if key and value:
                category = str(category or "notes")
                if category not in {"notes", "projects"}:
                    category = "notes"
                key = str(key)
                value = str(value)
                local_key = f"{category}/{key}"
                logger.info("LOCAL_MEMORY write_start key=%s", local_key)
                try:
                    bucket = self._local_session_memory.setdefault(category, {})
                    bucket[key] = {"value": value}
                    stored = bucket.get(key, {}).get("value")
                    if stored != value:
                        raise RuntimeError("local write verification failed")
                except Exception as exc:
                    result = f"Local memory write failed: {type(exc).__name__}"
                    logger.error(
                        "LOCAL_MEMORY write_failure key=%s error=%s",
                        local_key, type(exc).__name__, exc_info=True,
                    )
                    logger.info("TOOL_RESULT  %s  result=%s", name, result)
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    return types.FunctionResponse(
                        id=fc.id, name=name, response={"result": result}
                    )
                logger.info("LOCAL_MEMORY write_success key=%s", local_key)
                print(f"[Memory] 💾 save_memory: {local_key}")
            else:
                result = "Local memory write failed: key and value are required."
                logger.warning("LOCAL_MEMORY write_failure key=none error=missing_key_or_value")
                logger.info("TOOL_RESULT  %s  result=%s", name, result)
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name, response={"result": result}
                )
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            logger.info("TOOL_RESULT  %s  result=ok", name)
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        if name == "local_memory_search":
            allowed_categories = ("notes", "projects")
            requested_category = str(args.get("category") or "").strip()
            requested_key = str(args.get("key") or "").strip().rsplit("/", 1)[-1]
            query = _memory_key_alias(str(args.get("query") or ""))
            categories = (
                (requested_category,)
                if requested_category in allowed_categories
                else allowed_categories
            )
            memory = self._local_session_memory
            entries: list[tuple[str, str, str]] = []
            for local_category in categories:
                items = memory.get(local_category, {})
                if not isinstance(items, dict):
                    continue
                for local_key, entry in items.items():
                    if requested_key and local_key != requested_key:
                        continue
                    stored_value = entry.get("value") if isinstance(entry, dict) else entry
                    if stored_value is None:
                        continue
                    entries.append((local_category, str(local_key), str(stored_value)))

            if query and not requested_key:
                query_terms = set(query.split())
                scored = []
                for entry in entries:
                    searchable = set(_memory_key_alias(f"{entry[1]} {entry[2]}").split())
                    scored.append((len(query_terms & searchable), entry))
                matching = [entry for score, entry in scored if score > 0]
                if matching:
                    entries = matching

            entries = entries[:10]
            logger.info(
                "LOCAL_MEMORY read key=%s hit=%s matches=%d",
                requested_key or "any", bool(entries), len(entries),
            )
            if entries:
                result = "\n".join(
                    f"- {category}/{key} = {value}" for category, key, value in entries
                )
            else:
                result = "No matching local JARVIS memory."
            logger.info(
                "TOOL_RESULT  %s  result=%s",
                name, f"{len(entries)} local match(es)" if entries else "no local matches",
            )
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        result = "Done."

        try:
            if name == "open_app":
                r = await asyncio.to_thread(lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await asyncio.to_thread(lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await asyncio.to_thread(lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                if (
                    args.get("action", "").lower() == "open"
                    and not args.get("path")
                    and not args.get("name")
                ):
                    current_file = getattr(self.ui, "current_file", None)
                    if current_file:
                        args["path"] = current_file
                r = await asyncio.to_thread(lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "check_messages":
                r = await asyncio.to_thread(
                    lambda: check_messages(parameters=args, response=None, player=self.ui, session_memory=None),
                )
                result = r or "No readable messages were found."

            elif name == "prepare_message_reply":
                r = await asyncio.to_thread(
                    lambda: prepare_message_reply(parameters=args, response=None, player=self.ui, session_memory=None),
                )
                result = r or "The message draft could not be prepared."

            elif name == "send_message":
                r = await asyncio.to_thread(lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "email_control":
                if args.get("action", "").lower() == "connect" and not args.get("credentials_path"):
                    current_file = getattr(self.ui, "current_file", None)
                    if current_file and Path(str(current_file)).suffix.lower() == ".json":
                        args["credentials_path"] = current_file
                r = await asyncio.to_thread(lambda: email_control(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Email action completed."

            elif name == "reminder":
                r = await asyncio.to_thread(lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "date_time":
                result = self._date_time_authority.answer_action(
                    str(args.get("action", "")), str(args.get("query", "")),
                ) or "No he podido determinar si necesitas la fecha o la hora actual."

            elif name == "youtube_video":
                r = await asyncio.to_thread(lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "media_control":
                r = await asyncio.to_thread(lambda: media_control(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None,
                            "speak": self._speak_vision_result},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await asyncio.to_thread(lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await asyncio.to_thread(lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await asyncio.to_thread(lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await asyncio.to_thread(lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(
                    goal=args.get("goal", ""),
                    priority=priority,
                    speak=self.speak,
                    immediate=True,
                )
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await asyncio.to_thread(lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await asyncio.to_thread(
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await asyncio.to_thread(lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await asyncio.to_thread(lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await asyncio.to_thread(lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "graphics_quality":
                quality = str(args.get("quality") or "").strip().lower()
                if quality not in {"low", "medium", "high"}:
                    raise ValueError("Graphics quality must be low, medium, or high.")
                self.ui.set_graphics_quality(quality)
                result = f"JARVIS graphics quality changed to {quality}."

            elif name == "jarvis_ui_control":
                action = str(args.get("action") or "").strip().lower()
                if action == "change_theme":
                    theme = str(args.get("theme") or "").strip().lower()
                    allowed = {"arc_reactor", "stealth_red", "vibranium_purple", "nanotech_gold", "platinum"}
                    if theme not in allowed:
                        raise ValueError(f"Unknown JARVIS theme: {theme or 'missing'}")
                    self.ui.set_theme(theme)
                    result = f"JARVIS theme changed to {theme.replace('_', ' ')}."
                elif action == "change_graphics_quality":
                    quality = str(args.get("graphics_quality") or "").strip().lower()
                    if quality not in {"low", "medium", "high"}:
                        raise ValueError(f"Unknown graphics quality: {quality or 'missing'}")
                    self.ui.set_graphics_quality(quality)
                    result = f"JARVIS graphics quality changed to {quality}."
                else:
                    self.ui.handle_ui_command(action)
                    result = f"JARVIS interface action completed: {action.replace('_', ' ')}."

            elif name == "deep_research":
                r = request_deep_research(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Deep research preference requested."

            elif name == "create_presentation":
                current_file = getattr(self.ui, "current_file", None)
                supported_sources = {
                    ".txt", ".md", ".rst", ".csv", ".json", ".jsonl", ".docx", ".pptx",
                    ".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".webp",
                    ".wav", ".mp3", ".m4a", ".mp4", ".mov", ".avi", ".webm",
                }
                if (
                    not args.get("source_file")
                    and not args.get("source_files")
                    and current_file
                    and Path(str(current_file)).suffix.lower() in supported_sources
                ):
                    args["source_files"] = [current_file]
                r = request_presentation(parameters=args, player=self.ui, speak=self.speak)
                result = r or "Presentation preference requested."

            elif name == "task_status":
                from agent.task_queue import get_queue

                queue = get_queue()
                action = str(args.get("action") or "get").lower()
                task_id = str(args.get("task_id") or "").strip()
                if action == "all" or not task_id:
                    result = json.dumps(queue.get_all_statuses(), ensure_ascii=False)
                elif action == "cancel":
                    result = f"Task {task_id} cancelled." if queue.cancel(task_id) else f"Task {task_id} could not be cancelled."
                else:
                    status = queue.get_status(task_id)
                    result = json.dumps(status, ensure_ascii=False) if status else f"Task {task_id} was not found."

            # ── LILITH integration tools (JL-W005) ─────────────────────
            elif name == "lilith_memory_search":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH is not available. Cannot search persistent memory."
                else:
                    client = bridge._runtime.client
                    query = str(args.get("query", ""))
                    limit = int(args.get("limit", 5))
                    try:
                        hits = await client.search_memory(query, limit=limit)
                        if not hits:
                            result = f"No results in LILITH memory for: {query}"
                        else:
                            lines = []
                            for h in hits[:10]:
                                canonical_key = _canonical_memory_key(h.get("key", ""))
                                text = h.get("text") or h.get("value") or h.get("key") or str(h)
                                score = h.get("score", "")
                                prefix = f"{canonical_key}: " if canonical_key else ""
                                lines.append(f"- {prefix}{text}" + (f" (score: {score})" if score else ""))
                            result = "\n".join(lines)
                    except Exception as exc:
                        result = f"LILITH memory search failed: {exc}"

            elif name == "lilith_memory_store":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH is not available. Cannot store memory."
                else:
                    client = bridge._runtime.client
                    key = str(args.get("key", ""))
                    value = str(args.get("value", ""))
                    category = str(args.get("category", "preferences"))
                    confidence = float(args.get("confidence", 1.0))
                    desc = args.get("description") or None
                    if not key or not value:
                        result = "Missing key or value for memory store."
                    else:
                        semantic_key = _canonical_memory_key(key, category)
                        category = _memory_category_from_key(semantic_key, category)
                        try:
                            data = await client.store_memory(
                                semantic_key, value, category=category,
                                confidence=confidence, description=desc,
                            )
                            action_done = data.get("action", "stored")
                            if action_done == "updated":
                                result = (
                                    f"Memory updated: {semantic_key} is now '{value[:80]}'. "
                                    f"Disregard any previous value for {semantic_key} in your context."
                                )
                            else:
                                result = f"Memory created: {semantic_key} = {value[:80]}"
                        except Exception as exc:
                            result = f"LILITH memory store failed: {exc}"

            elif name == "lilith_memory_delete":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH is not available. Cannot delete memory."
                else:
                    client = bridge._runtime.client
                    key = _canonical_memory_key(str(args.get("key", "")))
                    reason = str(args.get("reason", "user_request"))
                    if not key:
                        result = "No memory key provided."
                    else:
                        try:
                            data = await client.delete_memory(key, reason=reason)
                            action_done = data.get("action", "deleted")
                            result = (
                                f"Memory {action_done}: {key}. "
                                f"This fact no longer exists — disregard it in your context."
                            )
                        except Exception as exc:
                            result = f"LILITH memory delete failed: {exc}"

            elif name == "lilith_home_action":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH is not available. Cannot control home devices."
                else:
                    client = bridge._runtime.client
                    target = str(args.get("target", ""))
                    action_name = str(args.get("action", ""))
                    ha_params = args.get("parameters") or None
                    if isinstance(ha_params, dict):
                        ha_params = {k: v for k, v in ha_params.items() if v is not None} or None
                    else:
                        ha_params = None
                    from core.headless_permissions import check_permission, PermissionLevel
                    perm = check_permission("lilith_home_action", action_name)
                    if perm.level == PermissionLevel.DENIED:
                        result = f"Action '{action_name}' is not allowed on home devices."
                    elif action_name not in ("turn_on", "turn_off", "toggle"):
                        result = f"Only turn_on, turn_off, and toggle are supported, not '{action_name}'."
                    elif not target:
                        result = "No device target specified."
                    else:
                        try:
                            res = await client.home_resolve(target)
                            status = res.get("status")
                            if status == "ambiguous":
                                names = ", ".join(
                                    c.get("friendly_name") or c.get("entity_id")
                                    for c in res.get("candidates", [])
                                )
                                result = f"Ambiguous: which one? {names}. No action taken."
                            elif status == "unknown":
                                result = f"Unknown device: '{target}'. No action taken."
                            elif status == "not_allowed":
                                result = f"Not allowed to control '{target}' from JARVIS. No action taken."
                            elif status == "resolved" and res.get("entity_id"):
                                entity_id = res["entity_id"]
                                friendly = res.get("friendly_name") or target
                                await client.home_action(entity_id, action_name, parameters=ha_params)
                                # Home Assistant state propagation can lag the service response.
                                try:
                                    if action_name == "toggle":
                                        expected = None
                                    else:
                                        expected = "on" if action_name == "turn_on" else "off"
                                    state_data = {}
                                    current = "unknown"
                                    for attempt in range(4):
                                        state_data = await client.home_entity(entity_id)
                                        current = state_data.get("state", "unknown")
                                        if expected is None or current == expected:
                                            break
                                        if attempt < 3:
                                            await asyncio.sleep(0.25)
                                    attrs = ""
                                    if ha_params and state_data.get("attributes"):
                                        brightness = state_data["attributes"].get("brightness")
                                        if brightness is not None:
                                            attrs = f" Brightness: {round(brightness/255*100)}%."
                                    if expected is None:
                                        result = f"{action_name} on '{friendly}' ({entity_id}). Current state: {current}.{attrs}"
                                    elif current == expected:
                                        result = f"{action_name} on '{friendly}' ({entity_id}). Verified state: {current}.{attrs}"
                                    else:
                                        result = (
                                            f"{action_name} sent to '{friendly}' ({entity_id}), but the expected "
                                            f"state '{expected}' was not verified; observed '{current}'."
                                        )
                                except Exception:
                                    result = f"{action_name} sent to '{friendly}' ({entity_id}). Could not confirm state."
                            else:
                                result = f"LILITH resolve returned unexpected status: {status}"
                        except Exception as exc:
                            result = f"LILITH home action failed: {exc}"

            elif name == "lilith_request_approval":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH is not available. Cannot request approval."
                else:
                    client = bridge._runtime.client
                    entity_id = str(args.get("entity_id", ""))
                    action_name = str(args.get("action", ""))
                    if not entity_id or not action_name:
                        result = "Missing entity_id or action."
                    else:
                        try:
                            data = await client.request_approval(entity_id, action_name)
                            token = data.get("token", "")
                            expires = data.get("expires_at", "")
                            result = (
                                f"Approval requested for {action_name} on {entity_id}. "
                                f"Token: {token}. Expires: {expires}. "
                                f"Ask the user to approve or reject."
                            )
                        except Exception as exc:
                            result = f"LILITH approval request failed: {exc}"

            elif name == "lilith_resolve_approval":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH is not available. Cannot resolve approval."
                else:
                    client = bridge._runtime.client
                    token = str(args.get("token", ""))
                    resolution = str(args.get("resolution", ""))
                    if not token or resolution not in ("approved", "rejected"):
                        result = "Invalid token or resolution. Must be 'approved' or 'rejected'."
                    else:
                        try:
                            data = await client.resolve_approval(token, resolution)
                            res = data.get("resolution", "unknown")
                            if res == "executed":
                                exec_data = data.get("execution", {})
                                result = f"Approved and executed: {exec_data.get('action', '')} on {exec_data.get('entity_id', '')}."
                            elif res == "rejected":
                                result = "Action rejected. Not executed."
                            elif res == "expired":
                                result = "Approval expired. Request a new one if needed."
                            else:
                                result = f"Approval resolution: {res}"
                        except Exception as exc:
                            result = f"LILITH approval resolution failed: {exc}"

            elif name == "lilith_health":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    try:
                        health = await bridge._runtime.client.health()
                        status = health.get("status", "unknown")
                        version = health.get("version", "")
                        services = health.get("services", {})
                        svc_str = ", ".join(f"{k}: {'OK' if v else 'DOWN'}" for k, v in services.items())
                        result = f"LILITH {version} is {status}. Services: {svc_str}."
                    except Exception as exc:
                        result = f"LILITH health check failed: {exc}"

            elif name == "lilith_runtime_status":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    try:
                        status = await bridge._runtime.client.runtime_status()
                        health = status.get("health") or {}
                        services = health.get("services") or {}
                        down = sorted(k for k, ok in services.items() if not ok)
                        autonomy = status.get("autonomy") or {}
                        queue = autonomy.get("queue") or {}
                        aut6 = status.get("aut6") or {}
                        satisfaction = (aut6.get("satisfaction") or {}).get("score")
                        goals = status.get("goals") or {}
                        monitor = status.get("monitor") or {}
                        routines = status.get("routines") or {}
                        result = (
                            f"LILITH runtime: {health.get('status', 'unknown')}; "
                            f"services down: {', '.join(down) if down else 'none'}; "
                            f"autonomy: {'running' if autonomy.get('running') else 'stopped'} "
                            f"({autonomy.get('state', 'unknown')}); "
                            f"queue: {queue}; "
                            f"satisfaction: {satisfaction if satisfaction is not None else 'unknown'}; "
                            f"goals: {goals.get('total', 'unknown')}; "
                            f"recent log errors: {monitor.get('recent_errors', 'unknown')}; "
                            f"routines: {'available' if routines.get('available') else routines.get('reason', 'unavailable')}."
                        )
                    except Exception as exc:
                        result = f"LILITH runtime status failed: {exc}"

            elif name == "lilith_docs_list":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    try:
                        data = await bridge._runtime.client.docs_list(
                            prefix=(args.get("prefix") or None))
                        docs = data.get("documents") or []
                        if not docs:
                            result = "No LILITH documents found for that prefix."
                        else:
                            lines = [d.get("path", "") for d in docs[:30]]
                            more = len(docs) - len(lines)
                            result = "LILITH documents:\n" + "\n".join(f"- {p}" for p in lines)
                            if more > 0:
                                result += f"\n...and {more} more."
                    except Exception as exc:
                        result = f"LILITH document list failed: {exc}"

            elif name == "lilith_docs_read":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    path = str(args.get("path", "")).strip()
                    max_bytes = int(args.get("max_bytes", 80000))
                    if not path:
                        result = "Missing LILITH document path."
                    else:
                        try:
                            data = await bridge._runtime.client.docs_read(
                                path, max_bytes=max_bytes)
                            content = str(data.get("content") or "")
                            truncated = " (truncated)" if data.get("truncated") else ""
                            result = f"{data.get('path', path)}{truncated}:\n{content}"
                        except Exception as exc:
                            result = f"LILITH document read failed: {exc}"

            elif name == "lilith_docs_search":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    query = str(args.get("query", "")).strip()
                    limit = int(args.get("limit", 10))
                    if not query:
                        result = "Missing LILITH document search query."
                    else:
                        try:
                            data = await bridge._runtime.client.docs_search(query, limit=limit)
                            hits = data.get("results") or []
                            if not hits:
                                result = f"No LILITH documentation matches: {query}"
                            else:
                                lines = []
                                for hit in hits[:10]:
                                    lines.append(f"- {hit.get('path')}")
                                    for match in (hit.get("matches") or [])[:3]:
                                        lines.append(f"  L{match.get('line')}: {match.get('text')}")
                                result = "\n".join(lines)
                        except Exception as exc:
                            result = f"LILITH document search failed: {exc}"

            elif name == "lilith_source_list":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    try:
                        data = await bridge._runtime.client.source_list(
                            prefix=(args.get("prefix") or None))
                        files = data.get("files") or []
                        if not files:
                            result = "No LILITH source files found for that prefix."
                        else:
                            lines = [f.get("path", "") for f in files[:40]]
                            more = len(files) - len(lines)
                            result = "LILITH source files:\n" + "\n".join(f"- {p}" for p in lines)
                            if more > 0:
                                result += f"\n...and {more} more."
                    except Exception as exc:
                        result = f"LILITH source list failed: {exc}"

            elif name == "lilith_source_read":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    path = str(args.get("path", "")).strip()
                    max_bytes = int(args.get("max_bytes", 100000))
                    if not path:
                        result = "Missing LILITH source path."
                    else:
                        try:
                            data = await bridge._runtime.client.source_read(
                                path, max_bytes=max_bytes)
                            content = str(data.get("content") or "")
                            truncated = " (truncated)" if data.get("truncated") else ""
                            result = f"{data.get('path', path)}{truncated}:\n{content}"
                        except Exception as exc:
                            result = f"LILITH source read failed: {exc}"

            elif name == "lilith_source_search":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    query = str(args.get("query", "")).strip()
                    limit = int(args.get("limit", 10))
                    if not query:
                        result = "Missing LILITH source search query."
                    else:
                        try:
                            data = await bridge._runtime.client.source_search(query, limit=limit)
                            hits = data.get("results") or []
                            if not hits:
                                result = f"No LILITH source matches: {query}"
                            else:
                                lines = []
                                for hit in hits[:10]:
                                    lines.append(f"- {hit.get('path')}")
                                    for match in (hit.get("matches") or [])[:3]:
                                        lines.append(f"  L{match.get('line')}: {match.get('text')}")
                                result = "\n".join(lines)
                        except Exception as exc:
                            result = f"LILITH source search failed: {exc}"

            elif name == "lilith_git_status":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    try:
                        data = await bridge._runtime.client.git_status()
                        head = str(data.get("head") or "")[:12] or "unknown"
                        origin = str(data.get("origin_main") or "")[:12] or "unknown"
                        status = "clean" if not data.get("dirty") else "dirty"
                        sync = "matches origin/main" if data.get("head_equals_origin_main") else (
                            f"ahead {data.get('ahead', '?')} / behind {data.get('behind', '?')}"
                        )
                        lines = [
                            f"LILITH git: {data.get('branch') or 'unknown'} @ {head} ({status}); origin/main {origin}; {sync}.",
                        ]
                        dirty = data.get("dirty_files") or []
                        untracked = data.get("untracked_files") or []
                        diff_stat = data.get("diff_stat") or []
                        recent = data.get("recent") or []
                        if dirty:
                            lines.append("Dirty files: " + ", ".join(dirty[:12]))
                        if untracked:
                            lines.append("Untracked: " + ", ".join(untracked[:12]))
                        if diff_stat:
                            lines.append("Diff stat:\n" + "\n".join(diff_stat[:12]))
                        if recent:
                            lines.append("Recent commits:\n" + "\n".join(f"- {c}" for c in recent[:5]))
                        result = "\n".join(lines)
                    except Exception as exc:
                        result = f"LILITH git status failed: {exc}"

            elif name == "lilith_command_submit":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running."
                else:
                    intent = str(args.get("intent", "")).strip()
                    params = args.get("parameters") or {}
                    if not intent:
                        result = "Missing LILITH command intent."
                    elif not isinstance(params, dict):
                        result = "LILITH command parameters must be an object."
                    else:
                        try:
                            data = await bridge._runtime.client.command_submit(
                                intent=intent,
                                parameters=params,
                                request_id=(args.get("request_id") or None),
                                correlation_id=(args.get("correlation_id") or None),
                                idempotency_key=(args.get("idempotency_key") or None),
                            )
                            status = data.get("status", "unknown")
                            replay = " replayed" if data.get("replayed") else ""
                            corr = data.get("correlation_id") or "unknown"
                            err = data.get("error") or {}
                            if status == "completed":
                                result = f"LILITH command {intent} completed{replay}; correlation_id={corr}."
                            elif err:
                                result = (
                                    f"LILITH command {intent} {status}{replay}; "
                                    f"code={err.get('code', 'unknown')}; correlation_id={corr}."
                                )
                            else:
                                result = f"LILITH command {intent} status={status}{replay}; correlation_id={corr}."
                        except Exception as exc:
                            result = f"LILITH command submit failed: {exc}"

            elif name == "lilith_routine":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH integration is not configured or not running; no routine was changed."
                else:
                    operation = str(args.get("operation", "")).strip().lower()
                    allowed = {"create", "list", "get", "update", "enable", "disable", "delete", "history"}
                    params = {k: v for k, v in args.items() if k != "operation" and v is not None}
                    missing = []
                    if operation == "create":
                        missing = [k for k in ("name", "schedule_type", "schedule", "timezone", "action_intent")
                                   if k not in params]
                    elif operation not in {"list"} and "routine_id" not in params:
                        missing = ["routine_id"]
                    from core.headless_permissions import check_permission, PermissionLevel
                    perm = check_permission("lilith_routine", operation)
                    if operation not in allowed:
                        result = "Unknown routine operation; no routine was changed."
                    elif perm.level == PermissionLevel.DENIED:
                        result = f"Routine operation '{operation}' is denied."
                    elif missing:
                        result = "Routine request is ambiguous: missing " + ", ".join(missing) + "."
                    else:
                        try:
                            client = bridge._runtime.client
                            action_params = params.get("action_parameters")
                            if (
                                operation == "create"
                                and params.get("action_intent") == "home.action"
                                and isinstance(action_params, dict)
                                and action_params.get("target")
                                and not action_params.get("entity_id")
                            ):
                                target = str(action_params["target"])
                                resolved = await client.home_resolve(target)
                                resolve_status = resolved.get("status")
                                if resolve_status != "resolved" or not resolved.get("entity_id"):
                                    result = (
                                        f"Routine target '{target}' could not be resolved unambiguously "
                                        f"(status={resolve_status}); no routine was created."
                                    )
                                    raise LookupError(result)
                                params["action_parameters"] = {
                                    **{k: v for k, v in action_params.items() if k != "target"},
                                    "entity_id": resolved["entity_id"],
                                }
                            logger.info(
                                "ROUTINE_SUBMIT function_call_id=%s operation=%s schedule_type=%s schedule=%s timezone=%s action_intent=%s action_parameters=%s",
                                fc.id, operation, params.get("schedule_type"), params.get("schedule"),
                                params.get("timezone"), params.get("action_intent"),
                                params.get("action_parameters"),
                            )
                            data = await client.command_submit(
                                intent=f"routines.{operation}", parameters=params,
                                request_id=f"jarvis:{fc.id}",
                                correlation_id=f"jarvis:{fc.id}",
                                idempotency_key=f"jarvis:routine:{fc.id}",
                            )
                            status = data.get("status", "unknown")
                            corr = data.get("correlation_id") or "unknown"
                            response = data.get("response") or {}
                            error = data.get("error") or {}
                            logger.info(
                                "ROUTINE_RESULT function_call_id=%s status=%s error_code=%s error_message=%s correlation_id=%s",
                                fc.id, status, error.get("code", "none"),
                                error.get("message", "none"), corr,
                            )
                            if status == "completed":
                                result = (
                                    f"LILITH confirmed routine {operation}; correlation_id={corr}; "
                                    f"authoritative_result={json.dumps(response, ensure_ascii=False, default=str)}"
                                )
                            else:
                                result = (
                                    f"LILITH did not complete routine {operation}; status={status}; "
                                    f"code={error.get('code', 'unknown')}; correlation_id={corr}."
                                )
                        except LookupError:
                            pass
                        except Exception as exc:
                            logger.error(
                                "ROUTINE_FAILED function_call_id=%s error_code=%s error_message=%s",
                                fc.id, getattr(exc, "code", type(exc).__name__), str(exc),
                            )
                            result = f"LILITH routine request failed; no success confirmed: {exc}"

            elif name == "system_status":
                from core.headless_tools import system_status
                result = str(system_status())

            elif name == "process_list":
                from core.headless_tools import process_list
                filt = str(args.get("filter", ""))
                result = str(process_list(filt))

            elif name == "process_info":
                from core.headless_tools import process_info
                pid_val = int(args.get("pid", 0))
                result = str(process_info(pid_val))

            elif name == "systemd_status":
                from core.headless_tools import systemd_status
                svc = str(args.get("service", ""))
                result = str(systemd_status(svc))

            elif name == "systemd_action":
                from core.headless_tools import systemd_action, systemd_execute
                from core.headless_permissions import requires_confirmation
                svc = str(args.get("service", ""))
                act = str(args.get("action", ""))
                if requires_confirmation("systemd_action", act):
                    check = systemd_action(svc, act)
                    if check.get("confirmation_required"):
                        result = (
                            f"JARVIS confirmation required: {check['summary']}\n"
                            f"Di 'sí' o 'confirmo' para ejecutar."
                        )
                    else:
                        result = str(check)
                else:
                    result = str(systemd_execute(svc, act))

            elif name == "systemd_list_failed":
                from core.headless_tools import systemd_list_failed
                result = str(systemd_list_failed())

            elif name == "journal_read":
                from core.headless_tools import journal_read
                svc = str(args.get("service", ""))
                lines_n = int(args.get("lines", 50))
                prio = str(args.get("priority", ""))
                since = str(args.get("since", ""))
                result = journal_read(svc, lines=lines_n, priority=prio, since=since)

            elif name == "lilith_home_status":
                if not client:
                    result = "LILITH is not connected."
                else:
                    target = str(args.get("target", ""))
                    if not target:
                        result = "No device/sensor specified."
                    else:
                        resolved = await client.home_resolve(target)
                        status_val = resolved.get("status", "unknown")
                        if status_val == "resolved":
                            entity_id = resolved["entity_id"]
                            state_data = await client.home_entity(entity_id)
                            result = (
                                f"Device: {resolved.get('friendly_name', entity_id)}\n"
                                f"Entity: {entity_id}\n"
                                f"State: {state_data}"
                            )
                        elif status_val == "ambiguous":
                            candidates = resolved.get("candidates", [])
                            result = f"Ambiguous — multiple devices match: {candidates}"
                        else:
                            result = f"Could not resolve '{target}': {resolved}"

            elif name == "open_capabilities_catalog":
                action = str(args.get("action", "open")).strip().lower()
                if getattr(self, "headless", False):
                    from core.headless_tools import build_headless_catalog
                    catalog_text = build_headless_catalog()
                    result = (
                        "[VOZ: Resume estas capacidades de forma natural y breve. "
                        "NO digas que abriste nada. Eres solo voz.]\n\n"
                        + catalog_text
                    )
                else:
                    from core.green.capability_catalog import refresh_catalog, open_catalog
                    if action == "refresh":
                        path = await asyncio.to_thread(refresh_catalog)
                        result = f"Capability catalog refreshed at {path}."
                    else:
                        await asyncio.to_thread(refresh_catalog)
                        msg = await asyncio.to_thread(open_catalog)
                        result = msg

            else:
                result = f"Unknown tool: {name}"
                logger.warning("TOOL_UNKNOWN  %s  args=%s", name, args)

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            logger.error("TOOL_FAILED  %s  error=%s", name, e, exc_info=True)
            traceback.print_exc()
            self.speak_error(name, e)
            try:
                from core.green.runtime import trace_tool_failed
                trace_tool_failed(_green_trace, error=e)
            except Exception:
                pass
        else:
            try:
                from core.green.runtime import trace_tool_complete
                trace_tool_complete(_green_trace, result_summary=str(result)[:200])
            except Exception:
                pass

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        logger.info("TOOL_RESULT  %s  result=%s", name, str(result)[:120])
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    def _begin_schedule_turn(self, text: str, source: str) -> None:
        self._schedule_turn_sequence += 1
        self._schedule_turn_id = f"{self._schedule_session_id}:{self._schedule_turn_sequence}"
        self._schedule_turn_source = source
        self._current_input_transcript = str(text or "").strip()
        self._schedule_guard_routed = False
        try:
            from core.green.runtime import emit_turn_started
            emit_turn_started(
                session_id=self._schedule_session_id,
                turn_id=self._schedule_turn_id,
                source=source,
            )
        except Exception:
            pass
        self._memory_turn_effects.clear()
        self._capture_pending_recurring(self._current_input_transcript)

    def _update_schedule_turn(self, text: str) -> None:
        self._current_input_transcript = str(text or "").strip()
        self._capture_pending_recurring(self._current_input_transcript)

    def _capture_pending_recurring(self, text: str) -> None:
        semantics = _schedule_semantics(text)
        pending = self._pending_routine
        if semantics == "recurring":
            pending = PendingRoutineState(
                session_id=self._schedule_session_id,
                origin_turn=self._schedule_turn_sequence,
                last_turn=self._schedule_turn_sequence,
                timezone=os.getenv("JARVIS_TIMEZONE", "Europe/Madrid"),
            )
            self._pending_routine = pending
            pending.observe_text(text, self._schedule_turn_sequence)
        elif (
            pending is not None
            and pending.pending_clarification
            and self._schedule_turn_sequence - pending.last_turn <= 4
        ):
            pending.observe_text(text, self._schedule_turn_sequence)

    def _effective_schedule_text(self, tool: str) -> str:
        return self._schedule_guard_text()

    def _active_pending_routine(self) -> PendingRoutineState | None:
        pending = self._pending_routine
        if pending is None or pending.session_id != self._schedule_session_id:
            return None
        if self._schedule_turn_sequence - pending.last_turn > 4:
            self._pending_routine = None
            return None
        return pending

    def _routine_confirmation_summary(self, operation: str, args: dict) -> str:
        """Build a human-readable summary for confirmation prompt."""
        name = args.get("name", "")
        schedule = args.get("schedule", {})
        h, m = schedule.get("hour"), schedule.get("minute", 0)
        time_str = f"{h:02d}:{m:02d}" if isinstance(h, int) else ""
        tz = args.get("timezone", "")
        target = (args.get("action_parameters") or {}).get("entity_id", "") or (args.get("action_parameters") or {}).get("target", "")
        if operation == "create":
            return f"Crear rutina '{name}': {target} a las {time_str} ({tz})"
        if operation == "delete":
            rid = args.get("routine_id", "?")
            return f"Eliminar rutina #{rid}"
        if operation in ("enable", "disable"):
            rid = args.get("routine_id", "?")
            return f"{'Activar' if operation == 'enable' else 'Desactivar'} rutina #{rid}"
        if operation == "update":
            rid = args.get("routine_id", "?")
            return f"Modificar rutina #{rid}"
        return f"Operación {operation} en rutina"

    def _stash_routine_confirmation(
        self, fc_id: str, fc_name: str, operation: str, args: dict,
    ) -> PendingRoutineConfirmation:
        summary = self._routine_confirmation_summary(operation, args)
        conf = PendingRoutineConfirmation(
            session_id=self._schedule_session_id,
            turn_sequence=self._schedule_turn_sequence,
            fc_id=fc_id,
            fc_name=fc_name,
            operation=operation,
            args=args,
            summary=summary,
        )
        self._routine_confirmation = conf
        return conf

    def _check_routine_confirmation(self, text: str) -> bool | None:
        """Check if user text confirms or rejects the pending routine.

        Returns True (confirmed), False (rejected), or None (no pending).
        """
        conf = self._routine_confirmation
        if conf is None:
            return None
        if conf.session_id != self._schedule_session_id:
            self._routine_confirmation = None
            return None
        if self._schedule_turn_sequence - conf.turn_sequence > 6:
            self._routine_confirmation = None
            return None
        if conf.confirmed:
            return None
        result = _user_confirmed(text)
        if result is True:
            conf.confirmed = True
        elif result is False:
            self._routine_confirmation = None
        return result

    def _pending_create_args(self, fc, pending: PendingRoutineState) -> dict | None:
        supplied = dict(getattr(fc, "args", None) or {})
        pending.absorb_call(supplied)
        if pending.pending_clarification:
            return None
        nested = supplied.get("action_parameters")
        nested = dict(nested) if isinstance(nested, dict) else {}
        target_key = "entity_id" if pending.target.startswith(("light.", "switch.")) else "target"
        return {
            **supplied,
            "operation": "create",
            "name": str(supplied.get("name") or f"{pending.action} {pending.target} {pending.recurrence}"),
            "schedule_type": pending.recurrence,
            "schedule": {"hour": pending.hour, "minute": pending.minute},
            "timezone": pending.timezone,
            "action_intent": str(supplied.get("action_intent") or "home.action"),
            "action_parameters": {
                **nested,
                target_key: pending.target,
                "action": pending.action,
            },
        }

    def _schedule_guard_text(self) -> str:
        if not getattr(self, "_schedule_turn_id", ""):
            return ""
        return str(getattr(self, "_current_input_transcript", "") or "").strip()

    def _schedule_log(
        self, *, fc_id: str, tool: str, classification: str, decision: str,
        operation: str = "",
    ) -> None:
        raw = self._schedule_guard_text()
        pending = self._active_pending_routine()
        pending_snapshot = None if pending is None else {
            "session": pending.session_id,
            "origin_turn": pending.origin_turn,
            "last_turn": pending.last_turn,
            "operation": pending.operation,
            "target": pending.target,
            "recurrence": pending.recurrence,
            "time": None if pending.hour is None else f"{pending.hour:02d}:{pending.minute or 0:02d}",
            "timezone": pending.timezone,
            "action": pending.action,
            "pending_clarification": sorted(pending.pending_clarification),
            "consumed_call_ids": sorted(pending.consumed_call_ids),
        }
        logger.info(
            "SCHEDULE_GUARD session=%s turn=%s source=%s raw_transcript=%r normalized_transcript=%r "
            "pending_before=%s classification=%s tool=%s operation=%s decision=%s function_call_id=%s",
            self._schedule_session_id, self._schedule_turn_id or "none",
            self._schedule_turn_source or "none", raw, _normalized_turn_text(raw),
            json.dumps(pending_snapshot, ensure_ascii=False, sort_keys=True), classification, tool,
            operation or "none", decision,
            fc_id or "missing",
        )

    def _memory_guard_log(
        self, *, fc_id: str, requested_tool: str, classification: str,
        routed_tool: str, canonical_key: str, decision: str,
    ) -> None:
        raw = self._schedule_guard_text()
        evidence = _memory_authority_indicators(raw)
        local_indicators = tuple(evidence["local"])
        persistent_indicators = tuple(evidence["persistent"])
        negated_indicators = tuple(evidence["negated_lilith"])
        local_score = len(local_indicators) + (2 if negated_indicators else 0)
        persistent_score = len(persistent_indicators)
        logger.info(
            "MEMORY_GUARD session=%s turn=%s function_call_id=%s requested_tool=%s "
            "raw_control_excerpt=%r normalized_control=%r local_indicators=%s "
            "persistent_indicators=%s negated_lilith_indicators=%s local_score=%s "
            "persistent_score=%s final_authority=%s classification=%s decision=%s "
            "canonical_key=%s routed_tool=%s",
            self._schedule_session_id, self._schedule_turn_id or "none",
            fc_id or "missing", requested_tool, _memory_control_log_excerpt(raw),
            _memory_control_log_excerpt(str(evidence["control_text"])), json.dumps(local_indicators),
            json.dumps(persistent_indicators), json.dumps(negated_indicators),
            local_score, persistent_score, classification, classification, decision,
            canonical_key or "none", routed_tool,
        )

    async def _resolve_memory_delete_key(self, raw_key: str, turn_text: str) -> str:
        canonical = _canonical_memory_key(raw_key)
        if "/" in canonical:
            return canonical
        alias = _memory_key_alias(canonical)
        if alias and alias in self._memory_key_aliases:
            return self._memory_key_aliases[alias]
        bridge = getattr(self, "_lilith", None)
        if bridge is None or not bridge.is_running:
            return ""
        try:
            hits = await bridge._runtime.client.search_memory(turn_text or raw_key, limit=10)
        except Exception:
            return ""
        candidates = []
        for hit in hits:
            candidate = _canonical_memory_key(hit.get("key", ""))
            if "/" not in candidate:
                continue
            candidates.append(candidate)
            attribute_alias = _memory_key_alias(candidate.rsplit("/", 1)[-1])
            if alias and alias == attribute_alias:
                return candidate
        return candidates[0] if len(set(candidates)) == 1 else ""

    async def _execute_memory_tool_guarded(self, fc) -> types.FunctionResponse:
        name = str(getattr(fc, "name", "") or "")
        args = dict(getattr(fc, "args", None) or {})
        fc_id = str(getattr(fc, "id", "") or "").strip()
        turn_text = self._schedule_guard_text()
        classification = _classify_memory_request(
            turn_text, source=self._schedule_turn_source, requested_tool=name,
        )
        if not fc_id or not turn_text:
            self._memory_guard_log(
                fc_id=fc_id, requested_tool=name, classification="unknown",
                routed_tool=name, canonical_key="", decision="blocked_no_current_turn",
            )
            return types.FunctionResponse(
                id=getattr(fc, "id", None), name=name,
                response={"result": (
                    "JARVIS memory validation failure: no safe association with the current turn. "
                    "No memory was changed."
                )},
            )

        associated_turn = self._memory_call_turns.get(fc_id)
        if associated_turn is not None and associated_turn != self._schedule_turn_id:
            self._memory_guard_log(
                fc_id=fc_id, requested_tool=name, classification=classification,
                routed_tool=name, canonical_key="", decision="blocked_reused_function_call",
            )
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    "JARVIS memory validation failure: FunctionCall.id belongs to another turn. "
                    "No memory was changed."
                )},
            )
        if fc_id in self._memory_consumed_call_ids:
            self._memory_guard_log(
                fc_id=fc_id, requested_tool=name, classification=classification,
                routed_tool=name, canonical_key="", decision="blocked_duplicate_function_call",
            )
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "JARVIS blocked a duplicate memory FunctionCall; no second write occurred."},
            )

        if (
            name in {"save_memory", "lilith_memory_store"}
            and classification == "ambiguous"
            and not _has_explicit_memory_write_intent(turn_text)
        ):
            self._memory_call_turns[fc_id] = self._schedule_turn_id
            self._memory_consumed_call_ids.add(fc_id)
            self._memory_guard_log(
                fc_id=fc_id, requested_tool=name, classification=classification,
                routed_tool=name, canonical_key="", decision="suppressed_no_explicit_save",
            )
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    "Automatic memory save suppressed. Keep this fact only in the active logical "
                    "conversation unless the user explicitly requests saved memory."
                )},
            )

        if classification in {"ambiguous", "unknown"}:
            decision = "blocked_ambiguous_authority" if classification == "ambiguous" else "blocked_unknown_authority"
            self._memory_call_turns[fc_id] = self._schedule_turn_id
            self._memory_consumed_call_ids.add(fc_id)
            self._memory_guard_log(
                fc_id=fc_id, requested_tool=name, classification=classification,
                routed_tool=name, canonical_key="", decision=decision,
            )
            clarification = (
                "¿Quieres que lo guarde solo en JARVIS o de forma persistente en LILITH?"
                if classification == "ambiguous"
                else "JARVIS memory validation failure: memory authority is unknown. No memory was changed."
            )
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": clarification},
            )

        routed_name = name
        routed_args = dict(args)
        if name == "save_memory" and classification == "persistent":
            routed_name = "lilith_memory_store"
            supplied_key = _canonical_memory_key(str(args.get("key", "")))
            category = _automatic_memory_category(turn_text, args.get("category"))
            if not args.get("category") and "/" in supplied_key and category == "notes":
                category = supplied_key.split("/", 1)[0]
            routed_args = {
                "key": _automatic_memory_key(turn_text, args.get("key")),
                "value": args.get("value", ""),
                "category": category,
                "confidence": 1.0,
                "description": turn_text,
            }
        elif name == "lilith_memory_store" and classification == "local":
            routed_name = "save_memory"
            routed_args = {
                "key": args.get("key", ""),
                "value": args.get("value", ""),
                "category": args.get("category", "notes"),
            }

        if routed_name == "lilith_memory_store":
            supplied_key = _canonical_memory_key(str(routed_args.get("key", "")))
            category = _automatic_memory_category(turn_text, routed_args.get("category"))
            if not routed_args.get("category") and "/" in supplied_key and category == "notes":
                category = supplied_key.split("/", 1)[0]
            routed_args["category"] = category
            routed_args["key"] = _automatic_memory_key(turn_text, routed_args.get("key"))
            routed_args.setdefault("confidence", 1.0)
            routed_args.setdefault("description", turn_text)
        elif routed_name == "save_memory":
            local_category = str(routed_args.get("category") or "notes")
            routed_args["category"] = local_category if local_category in {"notes", "projects"} else "notes"
            routed_args["key"] = _automatic_memory_key(turn_text, routed_args.get("key"))

        category = str(routed_args.get("category", "jarvis_fact"))
        raw_key = str(routed_args.get("key", ""))
        if routed_name == "lilith_memory_delete":
            canonical_key = await self._resolve_memory_delete_key(raw_key, turn_text)
            if not canonical_key:
                self._memory_guard_log(
                    fc_id=fc_id, requested_tool=name, classification=classification,
                    routed_tool=routed_name, canonical_key="", decision="blocked_unresolved_key",
                )
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "JARVIS could not resolve one unique persistent-memory key from LILITH; "
                        "nothing was deleted."
                    )},
                )
        else:
            canonical_key = _canonical_memory_key(raw_key, category)
        if routed_name in {"lilith_memory_store", "lilith_memory_delete"}:
            routed_args["key"] = canonical_key
            if routed_name == "lilith_memory_store":
                routed_args["category"] = _memory_category_from_key(canonical_key, category)
        value = str(routed_args.get("value", "")) if routed_name != "lilith_memory_delete" else ""
        effect = (routed_name, canonical_key, value)

        if effect in self._memory_turn_effects:
            self._memory_guard_log(
                fc_id=fc_id, requested_tool=name, classification=classification,
                routed_tool=routed_name, canonical_key=canonical_key,
                decision="blocked_duplicate_effect",
            )
            self._memory_call_turns[fc_id] = self._schedule_turn_id
            self._memory_consumed_call_ids.add(fc_id)
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    f"JARVIS blocked a duplicate memory mutation for {canonical_key}; "
                    "no second write occurred."
                )},
            )

        self._memory_call_turns[fc_id] = self._schedule_turn_id
        self._memory_consumed_call_ids.add(fc_id)
        self._memory_turn_effects.add(effect)
        decision = (
            "rerouted_persistent_store" if routed_name == "lilith_memory_store" and routed_name != name
            else "rerouted_local_store" if routed_name == "save_memory" and routed_name != name
            else "allowed_local" if routed_name == "save_memory" and classification == "local"
            else "allowed"
        )
        self._memory_guard_log(
            fc_id=fc_id, requested_tool=name, classification=classification,
            routed_tool=routed_name, canonical_key=canonical_key, decision=decision,
        )
        routed = SimpleNamespace(id=fc.id, name=routed_name, args=routed_args)
        response = await self._execute_tool(routed)
        result_text = str(response.response.get("result", ""))
        if routed_name == "lilith_memory_store" and result_text.startswith(("Memory created:", "Memory updated:")):
            self._memory_key_aliases[_memory_key_alias(canonical_key)] = canonical_key
            self._memory_key_aliases[_memory_key_alias(canonical_key.rsplit("/", 1)[-1])] = canonical_key
        if routed_name == name:
            return response
        return types.FunctionResponse(id=fc.id, name=name, response=response.response)

    async def _execute_memory_lookup_guarded(self, fc) -> types.FunctionResponse:
        """Allow saved-memory lookup only for an explicit request in the current user turn."""
        name = str(getattr(fc, "name", "") or "")
        scope = _explicit_memory_lookup_scope(self._schedule_guard_text())
        allowed = (
            scope == "stored"
            or (name == "local_memory_search" and scope == "local")
            or (name == "lilith_memory_search" and scope == "persistent")
        )
        if allowed:
            return await self._execute_tool(fc)
        print(
            "[JARVIS] Persistent-memory lookup suppressed: "
            "active conversation context has precedence."
        )
        logger.info(
            "MEMORY_LOOKUP_GUARD  tool=%s  scope=%s  decision=suppressed_current_conversation",
            name, scope,
        )
        return types.FunctionResponse(
            id=getattr(fc, "id", None), name=name,
            response={"result": (
                "Persistent-memory lookup suppressed. Answer directly from the active/restored "
                "logical conversation. Use saved-memory tools only after an explicit user request."
            )},
        )

    async def _execute_tool_guarded(self, fc) -> types.FunctionResponse:
        name = getattr(fc, "name", "")
        if name in _MEMORY_MUTATING_TOOL_NAMES:
            return await self._execute_memory_tool_guarded(fc)
        if name in _MEMORY_LOOKUP_TOOL_NAMES:
            return await self._execute_memory_lookup_guarded(fc)
        if name not in _SCHEDULED_TOOL_NAMES:
            return await self._execute_tool(fc)
        fc_id = str(getattr(fc, "id", "") or "").strip()
        args = dict(getattr(fc, "args", None) or {})
        operation = (
            str(args.get("operation", "")).strip().lower()
            if name == "lilith_routine"
            else str(args.get("action", "create")).strip().lower()
            if name == "reminder"
            else ""
        )
        turn_text = self._effective_schedule_text(name)
        if not fc_id or not turn_text:
            self._schedule_log(
                fc_id=fc_id, tool=name, operation=operation,
                classification="unknown", decision="blocked_no_current_turn",
            )
            return types.FunctionResponse(
                id=getattr(fc, "id", None), name=name,
                response={"result": (
                    "JARVIS validation/routing failure: scheduled side effect blocked because there is "
                    "no safe association with the current turn. LILITH was not called."
                )},
            )
        associated_turn = self._schedule_call_turns.get(fc_id)
        if associated_turn is not None and associated_turn != self._schedule_turn_id:
            self._schedule_log(
                fc_id=fc_id, tool=name, operation=operation,
                classification="unknown", decision="blocked_reused_function_call",
            )
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    "JARVIS validation/routing failure: FunctionCall.id was already associated with "
                    "another turn; scheduled side effect blocked. LILITH was not called."
                )},
            )
        self._schedule_call_turns[fc_id] = self._schedule_turn_id

        # --- Confirmation gate: execute stashed mutation if user confirmed ---
        conf = getattr(self, "_routine_confirmation", None)
        if conf is not None and name == "lilith_routine" and operation in _ROUTINE_WRITE_OPERATIONS:
            user_answer = self._check_routine_confirmation(turn_text)
            if user_answer is True:
                self._schedule_guard_routed = True
                self._schedule_log(
                    fc_id=conf.fc_id, tool=conf.fc_name, operation=conf.operation,
                    classification="confirmed", decision="allowed_after_confirmation",
                )
                routed = SimpleNamespace(id=fc.id, name=conf.fc_name, args=conf.args)
                self._routine_confirmation = None
                self._pending_routine = None
                return await self._execute_tool(routed)
            if user_answer is False:
                self._schedule_log(
                    fc_id=conf.fc_id, tool=conf.fc_name, operation=conf.operation,
                    classification="rejected", decision="cancelled_by_user",
                )
                self._routine_confirmation = None
                self._pending_routine = None
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "The user cancelled the routine operation. "
                        "LILITH was not called. Acknowledge the cancellation."
                    )},
                )

        semantics = _schedule_semantics(turn_text)

        # Gemini Live can emit a FunctionCall while input transcription is still a
        # leading fragment.  Merge the structured create contract into the same
        # session/turn state before classifying; never authorize from the fragment
        # alone, and never carry state across a missing/stale turn association.
        if name == "lilith_routine" and operation == "create":
            pending = self._active_pending_routine()
            if pending is None:
                pending = PendingRoutineState(
                    session_id=self._schedule_session_id,
                    origin_turn=self._schedule_turn_sequence,
                    last_turn=self._schedule_turn_sequence,
                    timezone=os.getenv("JARVIS_TIMEZONE", "Europe/Madrid"),
                )
                self._pending_routine = pending
                pending.observe_text(turn_text, self._schedule_turn_sequence)
            pending.absorb_call(args)
            if pending.recurrence in {"daily", "weekly", "interval"}:
                semantics = "recurring"

        if name == "lilith_routine" and operation in _ROUTINE_READ_OPERATIONS:
            if self._schedule_guard_routed:
                self._schedule_log(
                    fc_id=fc_id, tool=name, operation=operation,
                    classification=semantics, decision="blocked_duplicate",
                )
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "JARVIS validation/routing failure: this turn already produced a routine call; "
                        "duplicate blocked before dispatch. LILITH was not called again."
                    )},
                )
            self._schedule_guard_routed = True
            self._schedule_log(
                fc_id=fc_id, tool=name, operation=operation,
                classification=semantics, decision="allowed_read_only",
            )
            return await self._execute_tool(fc)

        if name == "lilith_routine" and operation in _ROUTINE_WRITE_OPERATIONS - {"create"}:
            if self._schedule_guard_routed:
                self._schedule_log(
                    fc_id=fc_id, tool=name, operation=operation,
                    classification=semantics, decision="blocked_duplicate",
                )
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "JARVIS validation/routing failure: this turn already produced a routine mutation; "
                        "duplicate blocked before dispatch. LILITH was not called again."
                    )},
                )
            self._schedule_guard_routed = True
            conf = self._stash_routine_confirmation(fc_id, name, operation, args)
            self._schedule_log(
                fc_id=fc_id, tool=name, operation=operation,
                classification=semantics, decision="pending_confirmation",
            )
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    f"JARVIS confirmation required: {conf.summary}. "
                    "Ask the user to confirm before executing. LILITH was NOT called yet."
                )},
            )

        if name == "reminder" and operation in {"list", "cancel", "delete", "modify", "update"}:
            if self._schedule_guard_routed:
                self._schedule_log(
                    fc_id=fc_id, tool=name, operation=operation,
                    classification=semantics, decision="blocked_duplicate",
                )
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "JARVIS validation/routing failure: this turn already produced a reminder call; "
                        "duplicate blocked before dispatch."
                    )},
                )
            self._schedule_guard_routed = True
            self._schedule_log(
                fc_id=fc_id, tool=name, operation=operation,
                classification=semantics, decision="allowed_reminder_management",
            )
            return await self._execute_tool(fc)

        pending = self._active_pending_routine()
        pending_followup_complete = bool(
            pending is not None
            and pending.last_turn == self._schedule_turn_sequence
            and not pending.pending_clarification
        )

        if name == "lilith_routine" and operation == "create" and semantics == "recurring":
            if self._schedule_guard_routed:
                self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification="recurring", decision="blocked_duplicate")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "JARVIS validation/routing failure: the recurring request was already routed once; "
                        "duplicate side effect blocked before dispatch. LILITH was not called again."
                    )},
                )
            if pending is None:
                self._capture_pending_recurring(turn_text)
                pending = self._active_pending_routine()
            routine_args = self._pending_create_args(fc, pending) if pending is not None else None
            self._schedule_guard_routed = True
            if routine_args is None:
                missing = ", ".join(sorted(pending.pending_clarification)) if pending else "routine details"
                self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification="recurring", decision="blocked_incomplete")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        f"JARVIS validation/routing failure: recurring request is incomplete or ambiguous; "
                        f"missing {missing}. Ask only for those fields. LILITH was not called."
                    )},
                )
            pending.consumed_call_ids.add(fc_id)
            conf = self._stash_routine_confirmation(fc_id, name, operation, routine_args)
            self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification="recurring", decision="pending_confirmation")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    f"JARVIS confirmation required: {conf.summary}. "
                    "Ask the user to confirm before executing. LILITH was NOT called yet."
                )},
            )

        if semantics == "recurring" or pending_followup_complete:
            if self._schedule_guard_routed:
                self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification=semantics, decision="blocked_duplicate")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "JARVIS validation/routing failure: the recurring request was already routed once; "
                        "duplicate side effect blocked before dispatch. LILITH was not called again."
                    )},
                )
            if pending is not None:
                pending.absorb_call(args)
                routine_args = self._pending_create_args(fc, pending)
            else:
                routine_args = _routine_args_from_wrong_call(turn_text, fc)
            if routine_args is None:
                self._schedule_guard_routed = True
                self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification=semantics, decision="blocked_incomplete")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": (
                        "JARVIS validation/routing failure: recurring request is incomplete. Ask for the "
                        "missing recurrence time, action, or target. LILITH was not called."
                    )},
                )
            self._schedule_guard_routed = True
            if pending is not None:
                pending.consumed_call_ids.add(fc_id)
            conf = self._stash_routine_confirmation(fc_id, "lilith_routine", "create", routine_args)
            self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification=semantics, decision="rerouted_pending_confirmation")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    f"JARVIS confirmation required: {conf.summary}. "
                    "Ask the user to confirm before executing. LILITH was NOT called yet."
                )},
            )

        if semantics == "one_shot" and name != "reminder":
            self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification=semantics, decision="blocked_wrong_tool")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    "JARVIS validation/routing failure: this is a one-time future request; non-reminder "
                    "side effect blocked before dispatch. LILITH was not called."
                )},
            )
        if semantics == "immediate" and name in {"reminder", "lilith_routine"}:
            self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification=semantics, decision="blocked_wrong_tool")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    "JARVIS validation/routing failure: the current turn did not establish a valid "
                    "scheduled request, so JARVIS blocked the tool before dispatch. LILITH was not called."
                )},
            )
        if self._schedule_guard_routed:
            self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification=semantics, decision="blocked_duplicate")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": (
                    "JARVIS validation/routing failure: this turn already produced a scheduled side effect; "
                    "duplicate blocked before dispatch. LILITH was not called again."
                )},
            )
        self._schedule_guard_routed = True
        self._schedule_log(fc_id=fc_id, tool=name, operation=operation, classification=semantics, decision="allowed")
        return await self._execute_tool(fc)

    async def _execute_tool_batch(self, calls):
        """Run read-only calls concurrently while preserving mutation order."""
        mutating = {
            "open_app", "send_message", "prepare_message_reply", "email_control", "reminder",
            "youtube_video", "media_control", "browser_control", "agent_task",
            "computer_settings", "computer_control", "desktop_control", "file_controller",
            "file_processor", "code_helper", "dev_agent", "game_updater", "flight_finder",
            "create_presentation", "deep_research", "task_status", "save_memory",
            "jarvis_ui_control", "graphics_quality",
            "lilith_memory_store", "lilith_memory_delete", "lilith_home_action",
            "lilith_command_submit",
            "lilith_routine",
        }
        call_list = list(calls or [])
        # Real tool activity -> UI (drives the EXECUTING state of the core visual).
        ui = getattr(self, "ui", None)
        show_progress = getattr(ui, "show_tool_progress", None)
        hide_progress = getattr(ui, "hide_tool_progress", None)
        if callable(show_progress) and call_list:
            show_progress(getattr(call_list[0], "name", "tool"))
        try:
            if any(getattr(call, "name", "") in mutating for call in call_list):
                return [await self._execute_tool_guarded(call) for call in call_list]
            return list(await asyncio.gather(*(self._execute_tool_guarded(call) for call in call_list)))
        finally:
            if callable(hide_progress):
                hide_progress()

    async def _send_realtime(self):
        while True:
            if self._shutdown_requested.is_set() or not self._conversation_requested.is_set():
                return
            msg = await self.out_queue.get()
            if msg is None or self._shutdown_requested.is_set() or not self._conversation_requested.is_set():
                return
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        """Own one capture worker and hot-recreate only its local InputStream."""
        worker_lock = getattr(self, "_audio_input_worker_lock", None)
        if worker_lock is None:
            worker_lock = self._audio_input_worker_lock = threading.Lock()
        if not worker_lock.acquire(blocking=False):
            logger.warning("AUDIO_INPUT duplicate_worker_ignored")
            return
        try:
            use_direct_alsa = (
                self.headless
                and sys.platform.startswith("linux")
                and not self.external_audio
                and not hasattr(self, "_audio_input_stream_factory")
                and os.environ.get("JARVIS_HEADLESS_CAPTURE_BACKEND", "alsa").strip().lower()
                != "sounddevice"
            )
            if use_direct_alsa:
                await self._listen_audio_with_arecord()
            else:
                await self._listen_audio_with_recovery()
        finally:
            worker_lock.release()

    async def _listen_audio_with_arecord(self) -> None:
        """Capture Headless Linux audio directly from ALSA, bypassing a silent Pulse source."""
        print("[JARVIS] 🎤 Mic worker started (direct ALSA)")
        loop = asyncio.get_running_loop()
        device = (
            os.environ.get("JARVIS_HEADLESS_ALSA_CAPTURE_DEVICE", "plughw:CARD=PCH,DEV=0").strip()
            or "plughw:CARD=PCH,DEV=0"
        )
        attempt = 0

        while (
            not self._shutdown_requested.is_set()
            and self._conversation_requested.is_set()
        ):
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    "arecord", "-q", "-D", device,
                    "-t", "raw", "-f", "S16_LE",
                    "-r", str(SEND_SAMPLE_RATE),
                    "-c", str(CHANNELS),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                print(f"[JARVIS] 🎤 Mic stream open (ALSA {device})")
                self._audio_input_device_id = None
                attempt = 0
                while (
                    not self._shutdown_requested.is_set()
                    and self._conversation_requested.is_set()
                ):
                    data = await proc.stdout.read(CHUNK_SIZE * CHANNELS * 2)
                    if not data:
                        detail = ""
                        if proc.stderr is not None:
                            detail = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
                        raise AudioInputDeviceLost(detail or "arecord capture ended")
                    if not self.ui.muted:
                        _report_audio_level(self.ui, "input", data)
                        self._process_microphone_audio(data, loop)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if (
                    self._shutdown_requested.is_set()
                    or not self._conversation_requested.is_set()
                ):
                    return
                attempt += 1
                discarded = self._drain_queue(getattr(self, "out_queue", None))
                logger.warning(
                    "AUDIO_INPUT direct_alsa_lost error=%s detail=%s device=%s discarded_input_chunks=%d",
                    type(exc).__name__, _safe_live_diagnostic(exc), device, discarded,
                )
                delay = _audio_device_recovery_delay(attempt)
                await self._wait_for_audio_recovery(delay)
            finally:
                if proc is not None and proc.returncode is None:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()

    async def _wait_for_audio_recovery(self, delay: float) -> None:
        deadline = time.monotonic() + max(0.0, float(delay))
        while (
            not self._shutdown_requested.is_set()
            and self._conversation_requested.is_set()
        ):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))

    async def _listen_audio_with_recovery(self) -> None:
        print("[JARVIS] 🎤 Mic worker started")
        loop = asyncio.get_running_loop()
        stream_factory = getattr(self, "_audio_input_stream_factory", sd.InputStream)
        device_resolver = getattr(
            self, "_audio_input_device_resolver", _current_default_input_device,
        )
        attempt = 0
        recovering = False
        previous_device = getattr(self, "_audio_input_device_id", None)

        while (
            not self._shutdown_requested.is_set()
            and self._conversation_requested.is_set()
        ):
            callback_state = {
                "last_at": time.monotonic(),
                "count": 0,
                "status": "",
            }

            def callback(indata, frames, time_info, status):
                callback_state["last_at"] = time.monotonic()
                callback_state["count"] += 1
                if status:
                    callback_state["status"] = _safe_live_diagnostic(status, 80)
                if not self.ui.muted:
                    data = indata.tobytes()
                    _report_audio_level(self.ui, "input", data)
                    self._process_microphone_audio(data, loop)

            try:
                device_id, device_name = device_resolver()
                opened_at = time.monotonic()
                with stream_factory(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    callback=callback,
                    device=device_id,
                ) as stream:
                    print("[JARVIS] 🎤 Mic stream open")
                    recovered_logged = False
                    while (
                        not self._shutdown_requested.is_set()
                        and self._conversation_requested.is_set()
                    ):
                        await asyncio.sleep(0.1)
                        now = time.monotonic()
                        active = getattr(stream, "active", True)
                        if active is False:
                            raise AudioInputDeviceLost("capture stream became inactive")
                        if now - callback_state["last_at"] > LIVE_INPUT_CALLBACK_STALE_SECONDS:
                            raise AudioInputDeviceLost(
                                f"no capture callback for {now - callback_state['last_at']:.1f}s"
                            )
                        if callback_state["count"] >= 3:
                            if recovering and not recovered_logged:
                                changed = previous_device != device_id
                                logger.info(
                                    "AUDIO_INPUT recovered device_id=%s device_name=%s "
                                    "default_changed=%s attempts=%d",
                                    device_id if device_id is not None else "default",
                                    device_name, changed, attempt,
                                )
                                try:
                                    self.ui.write_log("SYS: Micrófono recuperado automáticamente.")
                                except Exception:
                                    pass
                                recovered_logged = True
                                recovering = False
                            previous_device = device_id
                            self._audio_input_device_id = device_id
                            if now - opened_at >= 1.0:
                                attempt = 0
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if (
                    self._shutdown_requested.is_set()
                    or not self._conversation_requested.is_set()
                ):
                    return
                attempt += 1
                discarded = self._drain_queue(getattr(self, "out_queue", None))
                if not recovering:
                    logger.warning(
                        "AUDIO_INPUT device_lost error=%s detail=%s device_id=%s "
                        "discarded_input_chunks=%d",
                        type(exc).__name__, _safe_live_diagnostic(exc),
                        previous_device if previous_device is not None else "default",
                        discarded,
                    )
                    try:
                        self.ui.write_log(
                            "SYS: Micrófono no disponible; JARVIS reintentará conectarlo automáticamente."
                        )
                    except Exception:
                        pass
                recovering = True
                delay = _audio_device_recovery_delay(attempt)
                logger.info(
                    "AUDIO_INPUT recovery_wait attempt=%d delay=%.1fs",
                    attempt, delay,
                )
                await self._wait_for_audio_recovery(delay)

    def _enqueue_microphone_audio(self, data: bytes) -> None:
        queue = getattr(self, "out_queue", None)
        if queue is None:
            return
        try:
            queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
        except asyncio.QueueFull:
            logger.warning("BARGE_IN microphone_frame_dropped reason=input_queue_full")
            try:
                from core.voice_stability import get_monitor as _get_voice_monitor
                _get_voice_monitor().record_audio_frame(dropped=True)
            except Exception:
                pass

    @staticmethod
    def _barge_in_metrics(decision: BargeInDecision) -> tuple[int, float, float, float]:
        return (
            decision.speech_duration_ms,
            round(decision.rms, 4),
            round(decision.noise_floor, 4),
            round(decision.echo_similarity, 3),
        )

    def _log_barge_in(self, event: str, decision: BargeInDecision) -> None:
        duration, rms, noise, echo = self._barge_in_metrics(decision)
        logger.info(
            "BARGE_IN %s speech_duration_ms=%d rms=%.4f noise_floor=%.4f echo_similarity=%.3f",
            event, duration, rms, noise, echo,
        )

    def _process_microphone_audio(self, data: bytes, loop) -> BargeInDecision:
        """Capture full duplex, but expose playback-time audio only after speech validation."""
        with self._speaking_lock:
            speaking = self._is_speaking
        gate = getattr(self, "_barge_in_gate", None)
        if gate is None:
            gate = self._barge_in_gate = SpeechAwareBargeInGate(
                input_sample_rate=SEND_SAMPLE_RATE,
            )
        previously_accepted = gate.accepted
        decision = gate.process(data, playback_active=speaking)
        now = time.monotonic()
        # ── voice stability metrics ──
        try:
            from core.voice_stability import get_monitor as _get_voice_monitor
            _vm = _get_voice_monitor()
            _vm.record_audio_frame(dropped=False)
            _vm.update_noise_floor(decision.rms, decision.noise_floor)
        except Exception:
            pass
        if decision.candidate and not self._barge_in_candidate_logged:
            self._barge_in_candidate_logged = True
            loop.call_soon_threadsafe(self._log_barge_in, "candidate", decision)
        if decision.rejected_reason and now - self._barge_in_last_reject_log >= 1.0:
            self._barge_in_last_reject_log = now
            event = f"rejected reason={decision.rejected_reason}"
            loop.call_soon_threadsafe(self._log_barge_in, event, decision)
            try:
                from core.voice_stability import get_monitor as _get_voice_monitor
                _get_voice_monitor().record_barge_in(accepted=False)
            except Exception:
                pass
        if decision.accepted and not previously_accepted and not self._local_barge_in_active:
            self._local_barge_in_active = True
            self._suppress_interrupted_output = True
            self._turn_interrupted = True
            loop.call_soon_threadsafe(self._log_barge_in, "accepted", decision)
            loop.call_soon_threadsafe(self._interrupt_live_playback, "local_barge_in")
            try:
                from core.voice_stability import get_monitor as _get_voice_monitor
                _get_voice_monitor().record_barge_in(accepted=True)
            except Exception:
                pass
        for frame in decision.forward_frames:
            loop.call_soon_threadsafe(self._enqueue_microphone_audio, frame)
        return decision

    @staticmethod
    def _drain_queue(queue: asyncio.Queue | None) -> int:
        drained = 0
        if queue is None:
            return drained
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return drained
            else:
                drained += 1

    def _interrupt_live_playback(self, reason: str) -> int:
        """Accept a provider interruption and discard only stale output audio."""
        drained = self._drain_queue(getattr(self, "audio_in_queue", None))
        self.set_speaking(False)
        logger.info(
            "LIVE_AUDIO interrupted reason=%s flushed_chunks=%d",
            _safe_live_diagnostic(reason, 64), drained,
        )
        return drained

    async def _wait_for_playback_drain(
        self,
        timeout: float = LIVE_PLAYBACK_DRAIN_TIMEOUT_SECONDS,
    ) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            queue = getattr(self, "audio_in_queue", None)
            with self._speaking_lock:
                speaking = self._is_speaking
            if (queue is None or queue.empty()) and not speaking:
                return True
            await asyncio.sleep(0.02)
        return False

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        receive_conversation_id = self._conversation_id
        pending_goaway: str | None = None

        try:
            while True:
                if self._shutdown_requested.is_set() or not self._conversation_requested.is_set():
                    return
                out_buf, in_buf = [], []
                live_turn_id = uuid.uuid4().hex
                _new_turn = True
                turn_had_audio = False
                self._suppress_interrupted_output = False
                self._local_barge_in_active = False
                self._active_turn_id = live_turn_id
                self._turn_interrupted = False
                self._turn_tool_signatures = set()
                received_message = False
                _turn_start_t = time.monotonic()
                _last_input_transcript_t = None
                _first_response_audio_t = None
                _input_validated = False
                _audio_quarantine = []
                _output_quarantine = []
                _replay_rejected = False
                logger.info("TURN start id=%s", live_turn_id)
                async for response in self.session.receive():
                    received_message = True

                    resumption = getattr(response, "session_resumption_update", None)
                    handle = getattr(resumption, "new_handle", None)
                    if (
                        getattr(resumption, "resumable", None) is True
                        and isinstance(handle, str)
                        and handle.strip()
                    ):
                        with self._conversation_lock:
                            if self._conversation_requested.is_set():
                                if receive_conversation_id != self._conversation_id:
                                    return
                                self._session_resumption_handle = handle.strip()
                                self._session_resumption_handle_at = time.monotonic()
                                print("[JARVIS] Session resumption handle updated.")

                    go_away = getattr(response, "go_away", None)
                    if go_away is not None:
                        pending_goaway = _safe_live_diagnostic(
                            getattr(go_away, "time_left", None), 32,
                        )
                        logger.info(
                            "LIVE_SESSION go_away received time_left=%s active_playback=%s queued_audio=%d",
                            pending_goaway,
                            bool(self._is_speaking),
                            self.audio_in_queue.qsize() if self.audio_in_queue else 0,
                        )

                    response_audio = _live_response_audio_bytes(response)
                    if response_audio:
                        if self._suppress_interrupted_output:
                            logger.debug(
                                "LIVE_AUDIO suppressed reason=local_barge_in bytes=%d",
                                len(response_audio),
                            )
                        else:
                            if not turn_had_audio:
                                _first_response_audio_t = time.monotonic()
                                self._first_response_audio_t = _first_response_audio_t
                            turn_had_audio = True
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            if _input_validated:
                                self.audio_in_queue.put_nowait(response_audio)
                            else:
                                _audio_quarantine.append(response_audio)

                    if response.server_content:
                        sc = response.server_content

                        if getattr(sc, "interrupted", False):
                            self._interrupt_live_playback("provider_interruption")
                            self._turn_interrupted = True
                            self._suppress_interrupted_output = False
                            self._local_barge_in_active = False

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                merged_output = _merge_transcript_text(
                                    " ".join(out_buf), txt
                                )
                                out_buf = [merged_output]
                                self._interrupted_text = merged_output
                                if _input_validated:
                                    self._remember_conversation_text(
                                        "assistant",
                                        self._interrupted_text,
                                        expected_conversation_id=receive_conversation_id,
                                        turn_id=live_turn_id,
                                    )
                                    if not self.ui.muted:
                                        if _new_turn:
                                            self.ui.clear_subtitle()
                                            _new_turn = False
                                        self.ui.show_subtitle(txt)
                                else:
                                    _output_quarantine.append(("assistant_text", self._interrupted_text, txt))

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                _last_input_transcript_t = time.monotonic()
                                _is_first_input = not in_buf
                                current_input = _merge_transcript_text(
                                    " ".join(in_buf), txt
                                )
                                in_buf = [current_input]
                                if not _input_validated and not _replay_rejected and _is_semantic_transcript(_strip_noise_tags(current_input)):
                                    _norm = _strip_noise_tags(current_input).strip().lower()
                                    if (
                                        self._last_interrupted_turn is not None
                                        and self._last_interrupted_turn.get("normalized_input") == _norm
                                    ):
                                        _replay_rejected = True
                                        logger.info(
                                            "TURN_REPLAY rejected source_turn=%s current_turn=%s input=%r reason=interrupted_turn_replay",
                                            self._last_interrupted_turn.get("turn_id", "?"),
                                            live_turn_id, current_input[:80],
                                        )
                                        _audio_quarantine.clear()
                                        _output_quarantine.clear()
                                    else:
                                        _input_validated = True
                                        if _is_first_input:
                                            self._begin_schedule_turn("", "voice")
                                        self._update_schedule_turn(current_input)
                                        self._remember_conversation_text(
                                            "user",
                                            current_input,
                                            expected_conversation_id=receive_conversation_id,
                                            turn_id=live_turn_id,
                                        )
                                        for _qchunk in _audio_quarantine:
                                            self.audio_in_queue.put_nowait(_qchunk)
                                        _audio_quarantine.clear()
                                        for _qtype, _qtext, _qtxt in _output_quarantine:
                                            self._remember_conversation_text(
                                                "assistant",
                                                _qtext,
                                                expected_conversation_id=receive_conversation_id,
                                                turn_id=live_turn_id,
                                            )
                                            if not self.ui.muted:
                                                self.ui.show_subtitle(_qtxt)
                                        _output_quarantine.clear()
                                        if (
                                            not getattr(self, "_pending_self_quit", False)
                                            and self._is_explicit_self_quit_transcript(current_input)
                                        ):
                                            self._queue_self_quit_after_farewell()
                                elif _input_validated:
                                    if _is_first_input:
                                        self._begin_schedule_turn("", "voice")
                                    self._update_schedule_turn(current_input)
                                    self._remember_conversation_text(
                                        "user",
                                        current_input,
                                        expected_conversation_id=receive_conversation_id,
                                        turn_id=live_turn_id,
                                    )

                        if sc.turn_complete:
                            logger.info(
                                "TURN close id=%s reason=turn_complete interrupted=%s replay_rejected=%s",
                                live_turn_id, self._turn_interrupted, _replay_rejected,
                            )
                            print("[JARVIS] Turn complete; Live session remains open.")
                            self._suppress_interrupted_output = False
                            self._local_barge_in_active = False
                            if self._turn_done_event:
                                self._turn_done_event.set()
                            try:
                                from core.voice_stability import get_monitor as _get_voice_monitor
                                _vm = _get_voice_monitor()
                                _tc_t = time.monotonic()
                                if _last_input_transcript_t and _first_response_audio_t:
                                    _vm.record_latency(
                                        (_first_response_audio_t - _last_input_transcript_t) * 1000,
                                        label="speech_to_first_audio",
                                    )
                                if _first_response_audio_t and _turn_start_t:
                                    _vm.record_latency(
                                        (_tc_t - _turn_start_t) * 1000,
                                        label="turn_total",
                                    )
                            except Exception:
                                pass

                            full_in = " ".join(in_buf).strip()
                            _clean_in = _strip_noise_tags(full_in) if full_in else ""
                            _void_turn = bool(full_in) and not _is_semantic_transcript(_clean_in)

                            if _replay_rejected:
                                logger.info(
                                    "TURN_REPLAY discard turn_id=%s input=%r",
                                    live_turn_id, full_in[:80],
                                )
                                _audio_quarantine.clear()
                                _output_quarantine.clear()
                                if turn_had_audio:
                                    self._interrupt_live_playback("replay_discard")
                                    turn_had_audio = False
                                with self._conversation_lock:
                                    self._conversation_continuity = [
                                        t for t in self._conversation_continuity
                                        if t.get("turn_id") != live_turn_id
                                    ]
                                    self._persist_conversation_state()
                                self._last_interrupted_turn = None

                            elif _void_turn:
                                logger.info(
                                    "VOID_TURN id=%s raw=%r quarantined_chunks=%d",
                                    live_turn_id, full_in[:80], len(_audio_quarantine),
                                )
                                _audio_quarantine.clear()
                                _output_quarantine.clear()
                                if turn_had_audio:
                                    self._interrupt_live_playback("void_turn_discard")
                                    turn_had_audio = False
                                with self._conversation_lock:
                                    self._conversation_continuity = [
                                        t for t in self._conversation_continuity
                                        if t.get("turn_id") != live_turn_id
                                    ]
                                    self._persist_conversation_state()
                            elif full_in:
                                save_in = _clean_in if _clean_in != full_in else full_in
                                self._current_input_transcript = save_in
                                self._last_input_transcript = save_in
                                self._last_input_transcript_at = time.monotonic()
                                if (
                                    not getattr(self, "_pending_self_quit", False)
                                    and self._is_explicit_self_quit_transcript(save_in)
                                ):
                                    self._queue_self_quit_after_farewell()
                                self.ui.write_log(f"Tú: {save_in}")
                                self._remember_conversation_text(
                                    "user",
                                    save_in,
                                    expected_conversation_id=receive_conversation_id,
                                    turn_id=live_turn_id,
                                )
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out and _input_validated and not _void_turn and not _replay_rejected:
                                self.ui.write_log(f"AURORA: {full_out}")
                                self._remember_conversation_text(
                                    "assistant",
                                    full_out,
                                    expected_conversation_id=receive_conversation_id,
                                    turn_id=live_turn_id,
                                )
                            if (
                                _input_validated
                                and getattr(self, "_pending_self_quit", False)
                                and (full_out or turn_had_audio)
                            ):
                                self._mark_self_quit_farewell_received()
                                
                            if _audio_quarantine:
                                if _input_validated and not _void_turn and not _replay_rejected:
                                    for _qchunk in _audio_quarantine:
                                        self.audio_in_queue.put_nowait(_qchunk)
                                else:
                                    logger.info(
                                        "AUDIO_QUARANTINE discarded turn_id=%s chunks=%d",
                                        live_turn_id, len(_audio_quarantine),
                                    )
                                _audio_quarantine.clear()
                            if _output_quarantine:
                                if not _void_turn and not _replay_rejected and _input_validated:
                                    for _qtype, _qtext, _qtxt in _output_quarantine:
                                        self._remember_conversation_text(
                                            "assistant",
                                            _qtext,
                                            expected_conversation_id=receive_conversation_id,
                                            turn_id=live_turn_id,
                                        )
                                _output_quarantine.clear()

                            if not _replay_rejected:
                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):
                                    self._last_interrupted_turn = {
                                        "turn_id": live_turn_id,
                                        "normalized_input": _clean_in.strip().lower(),
                                    }
                                elif not self._turn_interrupted:
                                    self._last_interrupted_turn = None

                            out_buf = []
                            turn_had_audio = False
                            _new_turn = True

                            if pending_goaway is not None:
                                drained = await self._wait_for_playback_drain()
                                raise RecoverableLiveDisconnect(
                                    f"provider GoAway time_left={pending_goaway} playback_drained={drained}",
                                    category="provider_goaway",
                                )

                    if response.tool_call:
                        function_calls = list(response.tool_call.function_calls)
                        # ── turn integrity guards ──
                        if self._turn_interrupted or self._suppress_interrupted_output:
                            logger.info(
                                "TOOL_CALL rejected reason=stale_turn turn_id=%s tools=%s",
                                live_turn_id,
                                [getattr(fc, "name", "?") for fc in function_calls],
                            )
                            fn_responses = [
                                types.FunctionResponse(
                                    id=fc.id,
                                    name=getattr(fc, "name", "tool"),
                                    response={"result": "Turn was interrupted; tool call discarded."},
                                )
                                for fc in function_calls
                            ]
                        else:
                            if _replay_rejected or not _input_validated:
                                current_input = " ".join(in_buf).strip()
                                _reject_reason = "interrupted_turn_replay" if _replay_rejected else "no_valid_semantic_input"
                                logger.info(
                                    "TOOL_CALL rejected reason=%s turn_id=%s text=%r tools=%s",
                                    _reject_reason,
                                    live_turn_id, current_input[:80],
                                    [getattr(fc, "name", "?") for fc in function_calls],
                                )
                                fn_responses = [
                                    types.FunctionResponse(
                                        id=fc.id,
                                        name=getattr(fc, "name", "tool"),
                                        response={"result": f"{_reject_reason}; tool call rejected."},
                                    )
                                    for fc in function_calls
                                ]
                            else:
                                filtered_calls = []
                                dup_responses = []
                                import json as _json
                                for fc in function_calls:
                                    _fc_args = getattr(fc, "args", {}) or {}
                                    sig = f"{getattr(fc, 'name', '')}:{_json.dumps(_fc_args, sort_keys=True, default=str)}"
                                    if sig in self._turn_tool_signatures:
                                        logger.info(
                                            "TOOL_CALL rejected reason=duplicate_turn_call turn_id=%s tool=%s",
                                            live_turn_id, getattr(fc, "name", "?"),
                                        )
                                        dup_responses.append(types.FunctionResponse(
                                            id=fc.id,
                                            name=getattr(fc, "name", "tool"),
                                            response={"result": "Duplicate call in same turn; skipped."},
                                        ))
                                    else:
                                        self._turn_tool_signatures.add(sig)
                                        filtered_calls.append(fc)
                                if filtered_calls:
                                    exec_responses = await self._execute_tool_batch(filtered_calls)
                                    fn_responses = []
                                    exec_iter = iter(exec_responses)
                                    dup_iter = iter(dup_responses)
                                    for fc in function_calls:
                                        if any(getattr(d, 'id', None) == fc.id for d in dup_responses):
                                            fn_responses.append(next(d for d in dup_responses if getattr(d, 'id', None) == fc.id))
                                        else:
                                            fn_responses.append(next(exec_iter))
                                else:
                                    fn_responses = dup_responses
                        for function_call, function_response in zip(function_calls, fn_responses):
                            self._remember_conversation_tool_result(
                                str(getattr(function_call, "name", "tool")),
                                getattr(function_response, "response", function_response),
                                expected_conversation_id=receive_conversation_id,
                            )
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
                    if self._shutdown_requested.is_set() or not self._conversation_requested.is_set():
                        return
                    if pending_goaway is not None and not response_audio and response.server_content is None:
                        raise RecoverableLiveDisconnect(
                            f"provider GoAway time_left={pending_goaway} idle=true",
                            category="provider_goaway",
                        )
                # AsyncSession.receive() covers one complete model turn. Normal
                # exhaustion means that turn ended, not that the Live transport did.
                if not received_message:
                    await asyncio.sleep(0.05)
                else:
                    await asyncio.sleep(0)
        except Exception as e:
            if not self._conversation_requested.is_set() or self._shutdown_requested.is_set():
                return
            if isinstance(e, RecoverableLiveDisconnect):
                raise
            if isinstance(e, genai.errors.APIError) and "1000" in str(e):
                print("[JARVIS] Live session closed by the server; reconnecting.")
                raise RecoverableLiveDisconnect(
                    "Gemini Live session expired", category="provider_close", close_code=1000,
                ) from e
            if _is_transient_live_connection_error(e):
                raise RecoverableLiveDisconnect(
                    _safe_live_diagnostic(e), category="network",
                    close_code=getattr(e, "code", None),
                ) from e
            print(f"[JARVIS] ❌ Recv: {e}")
            raise



    _SILENCE_PRIME = b"\x00" * (CHUNK_SIZE * CHANNELS * 2)

    def _open_playback_stream(self):
        """Create and start a PortAudio output stream.

        In headless mode the stream is primed with one silence block so the
        internal ring buffer is never empty at the first real write.
        """
        output_device = getattr(self, "_audio_output_device_id", None)
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            device=output_device,
            latency="high" if self.headless else None,
        )
        t_open = time.monotonic()
        stream.start()
        if getattr(self, "headless", False):
            stream.write(self._SILENCE_PRIME)
            t_prime = time.monotonic()
            wa = getattr(stream, "write_available", None)
            logger.info(
                "PLAYBACK_DIAG stream_open=%.4f prime_done=%.4f "
                "prime_latency_ms=%.2f write_available=%s blocksize=%d",
                t_open, t_prime, (t_prime - t_open) * 1000,
                wa, CHUNK_SIZE,
            )
            self._playback_stream_opened_at = t_open
            self._playback_first_chunk_logged = False
        return stream

    def _close_playback_stream(self, stream):
        if stream is not None:
            with self._playback_stream_lock:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")
        lazy_lifecycle = self.headless and not self.external_audio

        stream = None
        if not self.external_audio and not lazy_lifecycle:
            stream = self._open_playback_stream()

        try:
            while True:
                if self._shutdown_requested.is_set() or not self._conversation_requested.is_set():
                    return
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                        if lazy_lifecycle and stream is not None:
                            self._close_playback_stream(stream)
                            stream = None
                        if self._complete_self_quit_after_audio():
                            return
                    continue
                # Skip Gemini audio when external TTS is active
                if self._tts_engine and self._ext_tts_provider and self._ext_tts_provider != "gemini":
                    pass  # drain silently
                else:
                    if lazy_lifecycle and stream is None:
                        stream = self._open_playback_stream()
                    self.set_speaking(True)
                    gate = getattr(self, "_barge_in_gate", None)
                    if gate is not None:
                        gate.observe_playback(chunk, sample_rate=RECEIVE_SAMPLE_RATE)
                    _report_audio_level(self.ui, "output", chunk)
                    try:
                        from core.voice_stability import get_monitor as _get_voice_monitor
                        _get_voice_monitor().record_audio_frame(dropped=False)
                    except Exception:
                        pass
                    if self.external_audio:
                        send_audio = getattr(self.client, "send_audio", None)
                        if callable(send_audio):
                            send_audio(chunk, f"audio/pcm;rate={RECEIVE_SAMPLE_RATE}")
                    elif stream is not None:
                        if (
                            lazy_lifecycle
                            and not getattr(self, "_playback_first_chunk_logged", True)
                        ):
                            t_now = time.monotonic()
                            t_open = getattr(self, "_playback_stream_opened_at", t_now)
                            wa = getattr(stream, "write_available", None)
                            logger.info(
                                "PLAYBACK_DIAG first_real_chunk=%.4f "
                                "delay_since_open_ms=%.2f chunk_bytes=%d "
                                "write_available=%s",
                                t_now, (t_now - t_open) * 1000,
                                len(chunk), wa,
                            )
                            self._playback_first_chunk_logged = True
                            try:
                                from core.voice_stability import get_monitor as _get_voice_monitor
                                _fra_t = getattr(self, "_first_response_audio_t", None)
                                if _fra_t:
                                    _get_voice_monitor().record_latency(
                                        (t_now - _fra_t) * 1000,
                                        label="first_audio_to_playback",
                                    )
                            except Exception:
                                pass
                        def _locked_write(s, c, lk):
                            with lk:
                                s.write(c)
                        await asyncio.to_thread(_locked_write, stream, chunk, self._playback_stream_lock)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            self._close_playback_stream(stream)

    async def run(self):
        # JL-W003: one LILITH runtime inside this asyncio loop (same loop as send_text).
        # Disabled in cloud_safe/hosted mode: a remote web client must not use this
        # machine's LILITH credential.
        if not self.cloud_safe:
            self._lilith = LilithBridge.from_env()
            if self._lilith is None and os.environ.get("LILITH_API_URL") and os.environ.get("LILITH_API_KEY"):
                # Configured but not loadable (e.g. stale editable install): never fail silently.
                self.ui.write_log("SYS: LILITH está configurada, pero no se pudo cargar la integración.")
            if self._lilith is not None:
                started = await self._lilith.start()
                state = "en línea" if self._lilith.lilith_available else "desconectada (se reconectará)"
                self.ui.write_log(
                    f"SYS: Integración con LILITH {state}." if started
                    else "SYS: Integración con LILITH no disponible."
                )
        self._loop = asyncio.get_running_loop()
        if not self._conversation_requested.is_set():
            self._set_conversation_state(ConversationState.STANDBY)
            print("[JARVIS] STANDBY; waiting for F8 or conversation button.")
        try:
            while not self._shutdown_requested.is_set():
                if not self._conversation_requested.is_set():
                    await asyncio.sleep(0.05)
                    continue
                try:
                    await self._run_live()
                except Exception as exc:
                    self.ui.write_log(f"ERR: Falló la conexión con Gemini Live: {exc}")
                    traceback.print_exc()
                self._conversation_requested.clear()
                if not self._shutdown_requested.is_set():
                    self._set_conversation_state(ConversationState.STANDBY)
        finally:
            self._persist_conversation_state()
            await self._close_live_session()
            bridge, self._lilith = self._lilith, None
            if bridge is not None:
                await bridge.stop()

    async def _run_live(self):
        """Own the single Gemini lifecycle runner for this JarvisLive instance."""
        if not self._live_runner_lock.acquire(blocking=False):
            print("[JARVIS] ⚠️ Duplicate Live runner request ignored.")
            return
        try:
            await self._run_live_session_loop()
        finally:
            self._live_runner_lock.release()

    async def _run_live_session_loop(self):
        api_key = self._api_key or _get_api_key()
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )
        live_model = await asyncio.to_thread(
            pick_live_model, client, API_CONFIG_PATH, headless=self.headless,
        )
        live_model_id = live_model.removeprefix("models/")
        self.ui.write_log(f"SYS: Modelo de Gemini Live seleccionado: {live_model_id}")

        start_time = time.time()
        reconnect_attempt = 0
        ever_connected = False
        goaway_resume_handle: str | None = None
        clean_goaway_fallback_used = False
        initial_history_disabled = live_model_id in _INITIAL_HISTORY_UNSUPPORTED_MODELS
        initial_history_fallback_logged = False
        while self._conversation_requested.is_set():
            if self._shutdown_requested.is_set():
                return
            # enforce runtime limit if configured
            if self.runtime_limit_seconds is not None:
                elapsed = time.time() - start_time
                if elapsed >= float(self.runtime_limit_seconds):
                    print(f"[JARVIS] ⏱️ Runtime limit reached ({self.runtime_limit_seconds}s). Exiting.")
                    try:
                        jarvis_status.write_status({"state": "expired"})
                    except Exception:
                        pass
                    os._exit(0)

            # enforce presence of required unlock path (e.g. mounted encrypted volume)
            if getattr(self, "required_unlock_path", None):
                try:
                    path = Path(self.required_unlock_path)
                    if not path.exists():
                        print(f"[JARVIS] 🔒 Required unlock path not present: {self.required_unlock_path}")
                        print("Please mount the locked container (see scripts/create_locked_dmg.sh).")
                        time.sleep(5)
                        continue
                    if self.required_unlock_secret is not None:
                        content = path.read_text(encoding="utf-8").strip()
                        if content != self.required_unlock_secret:
                            print("[JARVIS] 🔒 unlock.key content does not match expected secret.")
                            print("Please mount the locked container with the correct unlock.key file.")
                            time.sleep(5)
                            continue
                except Exception as e:
                    print(f"[JARVIS] 🔒 Locked path check error: {e}")
                    time.sleep(1)
                    continue
            attempt_initial_history = False
            try:
                if not self._conversation_requested.is_set():
                    return
                connect_kind = "reconnect" if ever_connected else "connect"
                logger.info(
                    "LIVE_SESSION %s attempt=%d handle=%s local_continuity=%s",
                    connect_kind, reconnect_attempt,
                    bool(self._session_resumption_handle),
                    bool(self._resume_from_local_continuity or self._logical_conversation_started),
                )
                print(f"[JARVIS] 🔌 {'Reconnecting' if ever_connected else 'Connecting'}...")
                self._set_conversation_state(
                    ConversationState.RECONNECTING if ever_connected
                    else ConversationState.CONNECTING
                )
                # JL-M003: fetch LILITH personal knowledge for system-prompt injection.
                lilith_ctx = None
                bridge = getattr(self, "_lilith", None)
                if bridge is not None and bridge.is_running:
                    try:
                        lilith_ctx = await bridge._runtime.client.get_context()
                        n = lilith_ctx.get("total_facts", 0) if lilith_ctx else 0
                        if n:
                            print(f"[JARVIS] LILITH context loaded: {n} facts")
                    except Exception as exc:
                        print(f"[JARVIS] LILITH context fetch skipped: {exc}")
                # Expire stale resumption handles to avoid 1008 errors.
                if (
                    self._session_resumption_handle is not None
                    and self._session_resumption_handle_at is not None
                    and (time.monotonic() - self._session_resumption_handle_at)
                    > _SESSION_RESUMPTION_HANDLE_MAX_AGE
                ):
                    handle_age = time.monotonic() - self._session_resumption_handle_at
                    logger.info(
                        "LIVE_SESSION handle_expired age=%.1fs max=%.0fs",
                        handle_age, _SESSION_RESUMPTION_HANDLE_MAX_AGE,
                    )
                    print(
                        f"[JARVIS] 🔌 Resumption handle expired ({handle_age:.0f}s old); "
                        "rebuilding from local continuity."
                    )
                    self._session_resumption_handle = None
                    self._session_resumption_handle_at = None
                    self._resume_from_local_continuity = True

                native_resumption = self._session_resumption_handle is not None
                restore_durable_context = bool(
                    not native_resumption
                    and (
                        self._resume_from_local_continuity
                        or self._logical_conversation_started
                    )
                )
                attempt_initial_history = bool(
                    restore_durable_context
                    and self._conversation_continuity
                    and not initial_history_disabled
                )
                if (
                    restore_durable_context
                    and initial_history_disabled
                    and not initial_history_fallback_logged
                ):
                    print(
                        "[JARVIS] Initial history rejected by Gemini; using compact "
                        "durable continuity fallback."
                    )
                    initial_history_fallback_logged = True
                config = self._build_config(
                    lilith_context=lilith_ctx,
                    resumption_handle=self._session_resumption_handle,
                    local_continuity=(
                        self._local_continuity_prompt()
                        if restore_durable_context
                        else ""
                    ),
                    initial_history=attempt_initial_history,
                    live_model_id=live_model_id,
                )

                if not self._conversation_requested.is_set():
                    return

                async with client.aio.live.connect(
                    model=live_model_id, config=config
                ) as session:
                    if not self._conversation_requested.is_set():
                        await session.close()
                        return
                    first_connection = not self._logical_conversation_started
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    # A clean Live transport has no server-side history. Prefill
                    # durable turns before exposing the session to typed or
                    # microphone input and before publishing LISTENING.
                    if attempt_initial_history:
                        stats = self._durable_history_diagnostics()
                        print(
                            "[JARVIS] Durable history structure: "
                            f"items={stats['items']} user={stats['user']} "
                            f"model={stats['model']} empty={stats['empty']} "
                            f"max_chars={stats['max_chars']} total_chars={stats['total_chars']}."
                        )
                        await self._restore_durable_continuity(session)
                    if not self._conversation_requested.is_set():
                        await session.close()
                        return

                    self.session        = session
                    self._loop          = asyncio.get_event_loop()

                    connected_at = time.monotonic()
                    logger.info(
                        "LIVE_SESSION connected model=%s resumption=%s initial_history=%s",
                        live_model_id, native_resumption, attempt_initial_history,
                    )
                    print("[JARVIS] ✅ Connected.")
                    self._set_conversation_state(ConversationState.LISTENING)
                    if first_connection:
                        self.ui.write_log("SYS: AURORA en línea.")
                    self._logical_conversation_started = True
                    self._resume_from_local_continuity = False
                    ever_connected = True
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({
                                "state": "online",
                                "voice": self._get_current_voice(),
                                "pid": os.getpid(),
                            })
                        except Exception:
                            pass

                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._send_realtime())
                        if not self.no_audio and not self.external_audio:
                            tg.create_task(self._listen_audio())
                        tg.create_task(self._receive_audio())
                        if not self.no_audio:
                            tg.create_task(self._play_audio())
                        if first_connection:
                            tg.create_task(self._announce_startup())

            except Exception as e:
                if self._shutdown_requested.is_set() or not self._conversation_requested.is_set():
                    return
                actual = next(_exception_leaves(e), e)

                if attempt_initial_history and (
                    isinstance(actual, InitialHistoryRejected)
                    or _is_invalid_argument_1007(e)
                ):
                    initial_history_disabled = True
                    initial_history_fallback_logged = True
                    print(
                        "[JARVIS] Initial history rejected by Gemini; using compact "
                        "durable continuity fallback."
                    )
                    continue
                if _is_session_not_found_1008(e):
                    logger.warning(
                        "LIVE_SESSION session_not_found_1008 handle=%s",
                        bool(self._session_resumption_handle),
                    )
                    self._session_resumption_handle = None
                    self._session_resumption_handle_at = None
                    self._resume_from_local_continuity = True
                    print(
                        "[JARVIS] 🔌 Session not found (1008); "
                        "discarding stale handle, rebuilding from local continuity."
                    )
                elif (
                    self._session_resumption_handle is not None
                    and _is_resumption_handle_rejected(e)
                ):
                    logger.warning(
                        "LIVE_SESSION resumption_rejected handle_age=%.1fs",
                        (time.monotonic() - (self._session_resumption_handle_at or 0)),
                    )
                    self._session_resumption_handle = None
                    self._session_resumption_handle_at = None
                    self._resume_from_local_continuity = True
                    print(
                        "[JARVIS] 🔌 Live resumption was rejected; rebuilding from local continuity."
                    )
                elif _is_recoverable_live_disconnect(e):
                    diagnostic = _live_disconnect_diagnostics(e)
                    logger.info(
                        "LIVE_SESSION disconnect recoverable category=%s error=%s close_code=%s "
                        "detail=%s handle=%s active_playback=%s queued_audio=%d queued_input=%d",
                        diagnostic["category"], diagnostic["exception"],
                        diagnostic["close_code"], diagnostic["detail"],
                        bool(self._session_resumption_handle), bool(self._is_speaking),
                        self.audio_in_queue.qsize() if self.audio_in_queue else 0,
                        self.out_queue.qsize() if self.out_queue else 0,
                    )
                    is_goaway = diagnostic["category"] == "provider_goaway"
                    if is_goaway and self._session_resumption_handle is not None:
                        if goaway_resume_handle == self._session_resumption_handle:
                            self._session_resumption_handle = None
                            self._session_resumption_handle_at = None
                            self._resume_from_local_continuity = True
                            clean_goaway_fallback_used = True
                            print(
                                "[JARVIS] Repeated GoAway; falling back to local continuity."
                            )
                        else:
                            goaway_resume_handle = self._session_resumption_handle
                    elif is_goaway and clean_goaway_fallback_used:
                        self._session_resumption_handle = None
                        self._session_resumption_handle_at = None
                        self._resume_from_local_continuity = True
                    print(
                        "[JARVIS] Live transport disconnected; resuming session. "
                        f"({actual})"
                    )
                elif _is_unsupported_voice_error(actual) and self.voice_name != DEFAULT_VOICE_NAME:
                    old_voice = self.voice_name
                    self.voice_name = DEFAULT_VOICE_NAME
                    self.ui.write_log(
                        f"SYS: La voz '{old_voice}' no está disponible. Se usará {DEFAULT_VOICE_NAME}."
                    )
                    print(f"[JARVIS] ⚠️ Voice '{old_voice}' unsupported; falling back to {DEFAULT_VOICE_NAME}.")
                    self.ui.sync_voice_display(DEFAULT_VOICE_NAME)
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({"state": "voice_fallback", "voice": DEFAULT_VOICE_NAME})
                        except Exception:
                            pass
                else:
                    print(f"[JARVIS] ⚠️ {e}")
                    traceback.print_exc()
                    self.ui.write_log(f"ERR: Falló la conexión con Gemini Live: {actual}")
                    return
            finally:
                queued_audio = self._drain_queue(self.audio_in_queue)
                queued_input = self._drain_queue(self.out_queue)
                if queued_audio or queued_input:
                    logger.info(
                        "LIVE_SESSION queue_cleanup audio_chunks=%d input_chunks=%d",
                        queued_audio, queued_input,
                    )
                self.set_speaking(False)
                self.session = None
                self.audio_in_queue = None
                self.out_queue = None
                self._turn_done_event = None

            if not self._conversation_requested.is_set():
                return
            if "connected_at" in locals() and time.monotonic() - connected_at >= 30.0:
                reconnect_attempt = 0
                try:
                    from core.voice_stability import get_monitor as _get_voice_monitor
                    _get_voice_monitor().record_reconnect(
                        attempt=0, delay=0, success=True, reason="connected",
                    )
                except Exception:
                    pass
            reconnect_attempt += 1
            if reconnect_attempt > MAX_LIVE_RECONNECT_ATTEMPTS:
                self.ui.write_log(
                    f"ERR: Gemini Live se desconectó tras {MAX_LIVE_RECONNECT_ATTEMPTS} intentos de reconexión."
                )
                return
            self._set_conversation_state(ConversationState.RECONNECTING)
            delay = _live_reconnect_delay(reconnect_attempt)
            try:
                from core.voice_stability import get_monitor as _get_voice_monitor
                _get_voice_monitor().record_reconnect(
                    attempt=reconnect_attempt, delay=delay, success=False,
                    reason="session_lost",
                )
            except Exception:
                pass
            logger.info(
                "LIVE_SESSION reconnect_wait attempt=%d/%d delay=%.1fs",
                reconnect_attempt, MAX_LIVE_RECONNECT_ATTEMPTS, delay,
            )
            print(
                f"[JARVIS] 🔌 Reconnecting in {delay:.0f}s "
                f"(attempt {reconnect_attempt}/{MAX_LIVE_RECONNECT_ATTEMPTS})..."
            )
            await self._wait_before_reconnect(delay)
            if not self._conversation_requested.is_set():
                return

def main():
    import sys

    if "--self-test" in sys.argv[1:]:
        from scripts.self_test import main as self_test_main

        return self_test_main([argument for argument in sys.argv[1:] if argument != "--self-test"])

    from ui import JarvisUI

    running_as_app = getattr(sys, "frozen", False)

    if os.environ.get("JARVIS_CLI") != "1" and not running_as_app:
        print("[JARVIS] Please launch with the JARVIS CLI: jarvis")
        return
    if not wait_for_startup_claps():
        return
    print("[JARVIS] ⚡ Powering up the interface...")
    try:
        ui = JarvisUI("face.png")
    except Exception as exc:
        print(f"[JARVIS] ❌ Interface startup failed: {exc}")
        traceback.print_exc()
        return

    def runner():
        ui.wait_for_api_key()
        voice_name = _load_voice_name()
        jarvis = JarvisLive(
            ui,
            voice_name,
            conversation_store_path=default_conversation_store_path(),
        )
        ui.on_quit_requested = jarvis.request_shutdown
        ui.on_conversation_toggle = jarvis.toggle_conversation

        # Trial/keyword runtime limiting: set via env `JARVIS_TRIAL_KEYWORD`.
        # If set to any non-empty string, jarvis will run for 3600 seconds (1 hour).
        trial_kw = os.environ.get("JARVIS_TRIAL_KEYWORD")
        if trial_kw:
            jarvis.runtime_limit_seconds = int(os.environ.get("JARVIS_RUNTIME_SECONDS", "3600"))
            jarvis.ui.write_log(f"SYS: Palabra de prueba detectada. Ejecución durante {jarvis.runtime_limit_seconds} segundos.")

        locked_secret = os.environ.get("JARVIS_LOCKED_KEY_SECRET")
        if locked_secret:
            jarvis.required_unlock_secret = locked_secret.strip()

        # Locked container check: if `JARVIS_LOCKED_VOLUME` is set, require
        # presence of `/Volumes/<name>/unlock.key` before full operation.
        locked_vol = os.environ.get("JARVIS_LOCKED_VOLUME")
        if locked_vol:
            mount_path = f"/Volumes/{locked_vol}/unlock.key"
            jarvis.required_unlock_path = mount_path
            jarvis.ui.write_log(f"SYS: Se requiere el volumen bloqueado: {mount_path}")
        ui.on_voice_change = jarvis.update_voice
        def _on_tts_change(provider, api_key, voice_id):
            if provider == "gemini":
                jarvis._tts_engine = None
                jarvis._ext_tts_provider = ""
                jarvis._ext_tts_voice_id = ""
                jarvis._ext_tts_api_key = ""
                jarvis.update_voice(voice_id)
            else:
                jarvis._ext_tts_provider = provider
                jarvis._ext_tts_voice_id = voice_id
                jarvis._ext_tts_api_key = api_key
                try:
                    from actions.tts_engine import TTSEngine
                    jarvis._tts_engine = TTSEngine(
                        provider=provider,
                        api_key=api_key,
                        voice_id=voice_id,
                    )
                    jarvis.ui.write_log(f"SYS: Motor TTS preparado: {provider} / {voice_id}")
                    jarvis.ui.write_log("SYS: Audio de Gemini silenciado; se usa TTS externo")
                except Exception as e:
                    jarvis.ui.write_log(f"SYS: Error del motor TTS: {e}")
                # Restart session so new TTS takes effect
                if jarvis.session and jarvis._loop:
                    try:
                        asyncio.run_coroutine_threadsafe(jarvis.session.close(), jarvis._loop)
                    except Exception as e:
                        print(f"[JARVIS] Could not close session: {e}")
        ui.on_tts_provider_change = _on_tts_change
        logger.info("JARVIS_START  model=%s", LIVE_MODEL)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")
            logger.info("JARVIS_SHUTDOWN  reason=KeyboardInterrupt")
        except Exception as exc:
            message = f"Falló el arranque de Gemini: {str(exc)[:180]}"
            print(f"[JARVIS] ❌ {message}")
            logger.error("JARVIS_STARTUP_FAILED  %s", message, exc_info=True)
            try:
                ui.write_log(f"ERR: {message}")
                ui.set_state("STANDBY")
            except Exception:
                pass

    threading.Thread(target=runner, daemon=True).start()
    print("[JARVIS] ✅ Interface ready.")
    ui.root.mainloop()
    print("[JARVIS] Interface closed.")

def cli_main():
    """Canonical console entry point installed as the `jarvis` command."""
    os.environ["JARVIS_CLI"] = "1"
    return main()


if __name__ == "__main__":
    raise SystemExit(main() or 0)
