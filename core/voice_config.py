"""Static, provider-independent voice catalog used across JARVIS.

The Live API does not expose a reliable voice-list endpoint, so the supported
catalog is intentionally versioned in code and shared by runtime and HUD.
"""

GEMINI_VOICES: tuple[tuple[str, str], ...] = (
    ("Puck", "puck"), ("Charon", "charon"), ("Kore", "kore"),
    ("Fenrir", "fenrir"), ("Aoede", "aoede"), ("Leda", "leda"),
    ("Orus", "orus"), ("Schedar", "schedar"),
    ("Zubenelgenubi", "zubenelgenubi"),
)
SUPPORTED_GEMINI_VOICE_NAMES = frozenset(value for _label, value in GEMINI_VOICES)
DEFAULT_GEMINI_VOICE = "puck"


def normalize_gemini_voice(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in SUPPORTED_GEMINI_VOICE_NAMES else DEFAULT_GEMINI_VOICE
