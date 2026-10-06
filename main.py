import asyncio
import os
import re
import threading
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from api import status as jarvis_status
from core.jarvis_client import JarvisClient
from core.lilith_gateway import LilithBridge
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)
import hashlib
import importlib
import time
import logging
import logging.handlers

from core.live_model import pick_live_model


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
SUPPORTED_VOICE_NAMES = {
    "puck", "charon", "kore", "fenrir", "aoede",
    "leda", "orus", "schedar", "zubenelgenubi"
}
DEFAULT_VOICE_NAME   = "puck"

RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024
LIVE_VAD_SILENCE_MS = 200
STARTUP_CLAPS_REQUIRED = 2
STARTUP_CLAP_MAX_GAP_SECONDS = 4.0
STARTUP_CLAP_COOLDOWN_SECONDS = 0.22
SELF_QUIT_GOODBYE = (
    "Por supuesto, flako. Ha sido un placer. AURORA se desconecta ahora. "
    "Hasta la próxima."
)

# Always first in the system instruction: the model must answer in Spanish whatever the
# language of the user, tool results or internal prompts.
LANGUAGE_RULE = (
    "Instrucción de idioma (no la menciones ni la repitas): responde SIEMPRE en español (castellano), en cada respuesta, aunque el usuario "
    "hable en inglés o los mensajes del sistema, resultados de herramientas y avisos internos estén en inglés: "
    "tradúcelos y contesta en español. Nunca respondas en inglés. Nunca pronuncies etiquetas entre corchetes."
)

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


def _live_reconnect_delay(attempt: int) -> float:
    return min(30.0, float(2 ** max(0, int(attempt) - 1)))


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
    if not voice_name:
        return DEFAULT_VOICE_NAME
    candidate = voice_name.strip().lower()
    return candidate if candidate in SUPPORTED_VOICE_NAMES else DEFAULT_VOICE_NAME


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
            prompt
            + "\n\nDirígete al usuario por su nombre (flako) con respeto, de forma eficiente y directa, siempre en español."
        )
    except Exception:
        return (
            "Eres AURORA, un asistente personal de IA. Responde siempre en español. "
            "Sé conciso y directo, y usa siempre las herramientas disponibles para completar tareas. "
            "Nunca simules ni adivines resultados: llama a la herramienta adecuada. "
            "Dirígete al usuario por su nombre (flako) con respeto, de forma eficiente y directa, siempre en español."
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

TOOL_DECLARATIONS = [
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
                    "enum": ["connect", "status", "disconnect", "inbox", "unread", "search", "read", "prepare", "approve", "cancel"],
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
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
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
                    "enum": ["play", "pause", "stop", "toggle", "next", "previous", "play_query"],
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
                }
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
                "action":      {"type": "STRING", "description": "The action to perform"},
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
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
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
            "Save a LOCAL operational note (runtime hints, session context, temporary flags). "
            "For persistent personal facts about the user (name, age, preferences, relationships, "
            "projects, wishes), use lilith_memory_store instead — LILITH is the canonical memory. "
            "Do NOT use this tool to store identity, preferences, relationships, or any personal "
            "knowledge. Those categories are restricted to LILITH. "
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
            "required": ["category", "key", "value"]
        }
    },
    # ── LILITH integration tools (JL-W005) ─────────────────────────────
    {
        "name": "lilith_memory_search",
        "description": (
            "Search the user's persistent memory stored in LILITH. "
            "Use when the user asks what LILITH knows, remembers, or has stored. "
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
            "LILITH is the canonical source for personal knowledge about the user. "
            "Use a stable semantic key for each fact (e.g. favorite_color, birthday, pet_name). "
            "To CORRECT a fact, call this again with the SAME key and the new value — "
            "this upserts, replacing the old value. Do NOT delete-then-recreate. "
            "Do NOT use lilith_memory_delete to correct a fact — only to forget one. "
            "LILITH enforces restricted categories (identity, housing, beliefs, economy, psychology). "
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
            "required": ["key", "value"]
        }
    },
    {
        "name": "lilith_memory_delete",
        "description": (
            "Delete a fact from LILITH's persistent memory. Use ONLY when the user "
            "explicitly asks to FORGET something entirely (e.g. 'forget my favorite color'). "
            "Do NOT use this to correct a fact — use lilith_memory_store with the same key instead. "
            "Key format: category/attribute (e.g. preferences/favorite_color). "
            "LILITH only allows deleting facts JARVIS created."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING", "description": "The semantic key to delete (category/attribute, e.g. preferences/favorite_color)"},
                "reason": {"type": "STRING", "description": "Why: 'user_request' (explicit forget) or 'obsolete'"},
            },
            "required": ["key"]
        }
    },
    {
        "name": "lilith_home_action",
        "description": (
            "Control a smart home device through LILITH and Home Assistant. "
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
                    "enum": ["turn_on", "turn_off"],
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
        "name": "lilith_request_approval",
        "description": (
            "Request approval for a home action that LILITH requires confirmation for. "
            "Use ONLY when lilith_home_action returned 'approval_required'. "
            "Returns a token — ask the user to approve or reject, then call lilith_resolve_approval."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "entity_id": {"type": "STRING", "description": "The entity_id from the resolve step"},
                "action": {"type": "STRING", "enum": ["turn_on", "turn_off"], "description": "The action"},
            },
            "required": ["entity_id", "action"]
        }
    },
    {
        "name": "lilith_resolve_approval",
        "description": (
            "Approve or reject a pending home-action approval. "
            "Use ONLY after the user explicitly said yes or no to the approval request. "
            "Never approve without explicit user consent."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "token": {"type": "STRING", "description": "The approval token from lilith_request_approval"},
                "resolution": {"type": "STRING", "enum": ["approved", "rejected"], "description": "User's decision"},
            },
            "required": ["token", "resolution"]
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
            "Manage persistent routines in LILITH. Map natural-language requests to exactly one "
            "operation. Ask the user for clarification before calling when the routine, time, "
            "timezone, recurrence, target, or action is ambiguous. LILITH is authoritative: never "
            "claim created/updated/enabled/disabled/deleted unless status is completed."
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
]

# Tool names exposed by hosted clients. The names here are Gemini function
# declaration names (which differ from a few implementation module names).
CLOUD_SAFE_ACTIONS = frozenset({
    "web_search",
    "deep_research",
    "create_presentation",
    "flight_finder",
    "email_control",
    "code_helper",
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


def get_tool_declarations(*, cloud_safe: bool = False) -> list[dict]:
    """Return the Gemini tools available for the requested runtime."""
    if not cloud_safe:
        return list(TOOL_DECLARATIONS)
    return [
        declaration
        for declaration in TOOL_DECLARATIONS
        if declaration.get("name") in CLOUD_SAFE_ACTIONS
    ]


class JarvisLive:

    def __init__(
        self,
        client: JarvisClient,
        voice_name: str = "Puck",
        *,
        cloud_safe: bool = False,
        api_key: str | None = None,
        external_audio: bool = False,
    ):
        # Keep ``ui`` as a compatibility alias for desktop integrations that
        # already inspect JarvisLive.ui. The engine contract is JarvisClient.
        self.client         = client
        self.ui             = client
        self.cloud_safe     = bool(cloud_safe)
        self.external_audio = bool(external_audio)
        self._api_key       = api_key.strip() if isinstance(api_key, str) else None
        self.tool_declarations = get_tool_declarations(cloud_safe=self.cloud_safe)
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.voice_name     = voice_name
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
        self._pending_self_quit = False
        self._pending_self_quit_farewell_received = False
        self._self_quit_timer = None
        self._shutdown_requested = threading.Event()
        self._tour_active = False
        # JL-W003: optional LILITH bridge for typed input (None when not configured).
        self._lilith: LilithBridge | None = None

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
        self._last_input_transcript = self._current_input_transcript
        self._last_input_transcript_at = time.monotonic()
        outgoing_text = self._current_input_transcript
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
            self._is_speaking = value
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
            self.ui.write_log("SYS: Shutdown queued; waiting for AURORA's farewell.")
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
        shutdown_requested.set()
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
        while not self._shutdown_requested.is_set():
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
        self.ui.write_log(f"SYS: Voice change requested: {self.voice_name}")
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

    def _build_config(self, *, lilith_context: dict | None = None) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [LANGUAGE_RULE, time_ctx]
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
        parts.append(sys_prompt)
        parts.append(LANGUAGE_RULE)  # repeated last: recency keeps the rule in force

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
                )
            ),
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            session_resumption=types.SessionResumptionConfig(),
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
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": "Startup sequence active. Try this action again when JARVIS is ready."},
            )

        from core.qa_mode import guard_tool_call, qa_block_message

        qa_decision = guard_tool_call(name, args)
        if not qa_decision.allowed:
            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={"result": qa_block_message(qa_decision)},
            )

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
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
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
                                text = h.get("text") or h.get("value") or h.get("key") or str(h)
                                score = h.get("score", "")
                                lines.append(f"- {text}" + (f" (score: {score})" if score else ""))
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
                        semantic_key = f"{category}/{key}"
                        try:
                            data = await client.store_memory(
                                semantic_key, value, category=category,
                                confidence=confidence, description=desc,
                            )
                            action_done = data.get("action", "stored")
                            if action_done == "updated":
                                result = (
                                    f"Memory updated: {key} is now '{value[:80]}'. "
                                    f"Disregard any previous value for {key} in your context."
                                )
                            else:
                                result = f"Memory created: {key} = {value[:80]}"
                        except Exception as exc:
                            result = f"LILITH memory store failed: {exc}"

            elif name == "lilith_memory_delete":
                bridge = getattr(self, "_lilith", None)
                if bridge is None or not bridge.is_running:
                    result = "LILITH is not available. Cannot delete memory."
                else:
                    client = bridge._runtime.client
                    key = str(args.get("key", ""))
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
                    if action_name not in ("turn_on", "turn_off"):
                        result = f"Only turn_on and turn_off are supported, not '{action_name}'."
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
                                # readback
                                try:
                                    state_data = await client.home_entity(entity_id)
                                    current = state_data.get("state", "unknown")
                                    attrs = ""
                                    if ha_params and state_data.get("attributes"):
                                        brightness = state_data["attributes"].get("brightness")
                                        if brightness is not None:
                                            attrs = f" Brightness: {round(brightness/255*100)}%."
                                    result = f"{action_name} on '{friendly}' ({entity_id}). Current state: {current}.{attrs}"
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
                    if operation not in allowed:
                        result = "Unknown routine operation; no routine was changed."
                    elif missing:
                        result = "Routine request is ambiguous: missing " + ", ".join(missing) + "."
                    else:
                        try:
                            data = await bridge._runtime.client.command_submit(
                                intent=f"routines.{operation}", parameters=params,
                                request_id=f"jarvis:{fc.id}",
                                correlation_id=f"jarvis:{fc.id}",
                                idempotency_key=f"jarvis:routine:{fc.id}",
                            )
                            status = data.get("status", "unknown")
                            corr = data.get("correlation_id") or "unknown"
                            response = data.get("response") or {}
                            error = data.get("error") or {}
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
                        except Exception as exc:
                            result = f"LILITH routine request failed; no success confirmed: {exc}"

            else:
                result = f"Unknown tool: {name}"
                logger.warning("TOOL_UNKNOWN  %s  args=%s", name, args)

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            logger.error("TOOL_FAILED  %s  error=%s", name, e, exc_info=True)
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        logger.info("TOOL_RESULT  %s  result=%s", name, str(result)[:120])
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _execute_tool_batch(self, calls):
        """Run read-only calls concurrently while preserving mutation order."""
        mutating = {
            "send_message", "prepare_message_reply", "email_control", "reminder",
            "computer_settings", "computer_control", "desktop_control", "file_controller",
            "file_processor", "code_helper", "dev_agent", "game_updater",
            "create_presentation", "save_memory", "jarvis_ui_control", "graphics_quality",
            "lilith_memory_store", "lilith_memory_delete", "lilith_home_action",
            "lilith_resolve_approval", "lilith_routine",
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
                return [await self._execute_tool(call) for call in call_list]
            return list(await asyncio.gather(*(self._execute_tool(call) for call in call_list)))
        finally:
            if callable(hide_progress):
                hide_progress()

    async def _send_realtime(self):
        while True:
            if self._shutdown_requested.is_set():
                return
            msg = await self.out_queue.get()
            if msg is None or self._shutdown_requested.is_set():
                return
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                _report_audio_level(self.ui, "input", data)
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while not self._shutdown_requested.is_set():
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []
        _new_turn = True
        turn_had_audio = False

        try:
            while True:
                if self._shutdown_requested.is_set():
                    return
                async for response in self.session.receive():

                    response_audio = _live_response_audio_bytes(response)
                    if response_audio:
                        turn_had_audio = True
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response_audio)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                self._interrupted_text = " ".join(out_buf)
                                if not self.ui.muted:
                                    if _new_turn:
                                        self.ui.clear_subtitle()
                                        _new_turn = False
                                    self.ui.show_subtitle(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                if not in_buf:
                                    self._current_input_transcript = ""
                                in_buf.append(txt)
                                self._current_input_transcript = " ".join(in_buf).strip()
                                if (
                                    not getattr(self, "_pending_self_quit", False)
                                    and self._is_explicit_self_quit_transcript(self._current_input_transcript)
                                ):
                                    self._queue_self_quit_after_farewell()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self._current_input_transcript = full_in
                                self._last_input_transcript = full_in
                                self._last_input_transcript_at = time.monotonic()
                                if (
                                    not getattr(self, "_pending_self_quit", False)
                                    and self._is_explicit_self_quit_transcript(full_in)
                                ):
                                    self._queue_self_quit_after_farewell()
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            if (
                                getattr(self, "_pending_self_quit", False)
                                and (full_out or turn_had_audio)
                            ):
                                self._mark_self_quit_farewell_received()
                                
                            out_buf = []
                            turn_had_audio = False
                            _new_turn = True

                    if response.tool_call:
                        function_calls = list(response.tool_call.function_calls)
                        for fc in function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                        fn_responses = await self._execute_tool_batch(function_calls)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
                    if self._shutdown_requested.is_set():
                        return
        except Exception as e:
            if isinstance(e, genai.errors.APIError) and "1000" in str(e):
                print("[JARVIS] 🔌 Session closed normally.")
                return
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise



    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = None
        if not self.external_audio:
            stream = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
            )
            stream.start()

        try:
            while True:
                if self._shutdown_requested.is_set():
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
                        if self._complete_self_quit_after_audio():
                            return
                    continue
                # Skip Gemini audio when external TTS is active
                if self._tts_engine and self._ext_tts_provider and self._ext_tts_provider != "gemini":
                    pass  # drain silently
                else:
                    self.set_speaking(True)
                    _report_audio_level(self.ui, "output", chunk)
                    if self.external_audio:
                        send_audio = getattr(self.client, "send_audio", None)
                        if callable(send_audio):
                            send_audio(chunk, f"audio/pcm;rate={RECEIVE_SAMPLE_RATE}")
                    elif stream is not None:
                        await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            if stream is not None:
                stream.stop()
                stream.close()

    async def run(self):
        # JL-W003: one LILITH runtime inside this asyncio loop (same loop as send_text).
        # Disabled in cloud_safe/hosted mode: a remote web client must not use this
        # machine's LILITH credential.
        if not self.cloud_safe:
            self._lilith = LilithBridge.from_env()
            if self._lilith is None and os.environ.get("LILITH_API_URL") and os.environ.get("LILITH_API_KEY"):
                # Configured but not loadable (e.g. stale editable install): never fail silently.
                self.ui.write_log("SYS: LILITH is configured but the integration could not be loaded.")
            if self._lilith is not None:
                started = await self._lilith.start()
                state = "online" if self._lilith.lilith_available else "offline (will reconnect)"
                self.ui.write_log(
                    f"SYS: LILITH integration {state}." if started
                    else "SYS: LILITH integration unavailable."
                )
        try:
            await self._run_live()
        finally:
            bridge, self._lilith = self._lilith, None
            if bridge is not None:
                await bridge.stop()

    async def _run_live(self):
        api_key = self._api_key or _get_api_key()
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )
        live_model = await asyncio.to_thread(pick_live_model, client, API_CONFIG_PATH)
        live_model_id = live_model.removeprefix("models/")
        self.ui.write_log(f"SYS: Gemini Live model selected: {live_model_id}")

        start_time = time.time()
        while True:
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
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
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
                config = self._build_config(lilith_context=lilith_ctx)

                async with (
                    client.aio.live.connect(model=live_model_id, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: AURORA online.")
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({
                                "state": "online",
                                "voice": self._get_current_voice(),
                                "pid": os.getpid(),
                            })
                        except Exception:
                            pass

                    tg.create_task(self._send_realtime())
                    if not self.external_audio:
                        tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._announce_startup())

            except Exception as e:
                if self._shutdown_requested.is_set():
                    return
                actual = e
                if isinstance(e, ExceptionGroup) and len(e.exceptions) == 1:
                    actual = e.exceptions[0]

                if _is_unsupported_voice_error(actual) and self.voice_name != DEFAULT_VOICE_NAME:
                    old_voice = self.voice_name
                    self.voice_name = DEFAULT_VOICE_NAME
                    self.ui.write_log(
                        f"SYS: Voice '{old_voice}' not available. Falling back to {DEFAULT_VOICE_NAME}."
                    )
                    print(f"[JARVIS] ⚠️ Voice '{old_voice}' unsupported; falling back to {DEFAULT_VOICE_NAME}.")
                    self.ui.sync_voice_display(DEFAULT_VOICE_NAME)
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({"state": "voice_fallback", "voice": DEFAULT_VOICE_NAME})
                        except Exception:
                            pass
                elif isinstance(actual, genai.errors.APIError) and "1000" in str(actual):
                    print("[JARVIS] 🔌 Session ended normally.")
                    if not self.cloud_safe:
                        try:
                            jarvis_status.write_status({"state": "offline"})
                        except Exception:
                            pass
                else:
                    print(f"[JARVIS] ⚠️ {e}")
                    traceback.print_exc()

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
        jarvis = JarvisLive(ui, voice_name)
        ui.on_quit_requested = jarvis.request_shutdown

        # Trial/keyword runtime limiting: set via env `JARVIS_TRIAL_KEYWORD`.
        # If set to any non-empty string, jarvis will run for 3600 seconds (1 hour).
        trial_kw = os.environ.get("JARVIS_TRIAL_KEYWORD")
        if trial_kw:
            jarvis.runtime_limit_seconds = int(os.environ.get("JARVIS_RUNTIME_SECONDS", "3600"))
            jarvis.ui.write_log(f"SYS: Trial keyword detected. Running for {jarvis.runtime_limit_seconds} seconds.")

        locked_secret = os.environ.get("JARVIS_LOCKED_KEY_SECRET")
        if locked_secret:
            jarvis.required_unlock_secret = locked_secret.strip()

        # Locked container check: if `JARVIS_LOCKED_VOLUME` is set, require
        # presence of `/Volumes/<name>/unlock.key` before full operation.
        locked_vol = os.environ.get("JARVIS_LOCKED_VOLUME")
        if locked_vol:
            mount_path = f"/Volumes/{locked_vol}/unlock.key"
            jarvis.required_unlock_path = mount_path
            jarvis.ui.write_log(f"SYS: Locked volume required: {mount_path}")
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
                    jarvis.ui.write_log(f"SYS: TTS engine ready: {provider} / {voice_id}")
                    jarvis.ui.write_log("SYS: Gemini audio muted - using external TTS")
                except Exception as e:
                    jarvis.ui.write_log(f"SYS: TTS engine error: {e}")
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
            message = f"Gemini startup failed: {str(exc)[:180]}"
            print(f"[JARVIS] ❌ {message}")
            logger.error("JARVIS_STARTUP_FAILED  %s", message, exc_info=True)
            try:
                ui.write_log(f"ERR: {message}")
                ui.set_state("LISTENING")
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
