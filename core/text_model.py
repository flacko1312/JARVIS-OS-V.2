from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_TEXT_MODEL = "gemini-3.8-flash"


def configured_text_model(config_path: Path) -> str:
    """Resolve the non-Live text-processing model."""
    env_model = os.environ.get("GEMINI_TEXT_MODEL", "").strip()
    if env_model:
        return env_model

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        configured = str(
            loaded.get("text_model", "") if isinstance(loaded, dict) else ""
        ).strip()
    except (OSError, ValueError, TypeError):
        configured = ""

    return configured or DEFAULT_TEXT_MODEL
