from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_VISION_MODEL = "gemini-3.8-flash"
DEFAULT_VISION_FALLBACK_MODEL = "gemini-3.6-flash"
DEFAULT_OLLAMA_VISION_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_VISION_MODEL = "qwen3-vl:4b-instruct"


@dataclass(frozen=True)
class OllamaVisionConfig:
    enabled: bool
    url: str
    model: str
    connect_timeout: float = 3.0
    read_timeout: float = 90.0


def configured_vision_model(config_path: Path) -> str:
    """Resolve the image-analysis model without exposing configuration values."""
    env_model = os.environ.get("GEMINI_VISION_MODEL", "").strip()
    if env_model:
        return env_model

    try:
        configured = str(
            json.loads(config_path.read_text(encoding="utf-8")).get(
                "vision_model", ""
            )
            or ""
        ).strip()
    except (OSError, ValueError, TypeError):
        configured = ""

    return configured or DEFAULT_VISION_MODEL


def configured_vision_fallback_model(config_path: Path) -> str:
    """Resolve the fallback used only after bounded primary 503 failures."""
    env_model = os.environ.get("GEMINI_VISION_FALLBACK_MODEL", "").strip()
    if env_model:
        return env_model

    try:
        configured = str(
            json.loads(config_path.read_text(encoding="utf-8")).get(
                "vision_fallback_model", ""
            )
            or ""
        ).strip()
    except (OSError, ValueError, TypeError):
        configured = ""

    return configured or DEFAULT_VISION_FALLBACK_MODEL


def _load_config(config_path: Path) -> dict:
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _enabled(value: object, *, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().casefold() not in {"0", "false", "no", "off"}


def _local_ollama_url(value: str) -> str:
    url = (value or DEFAULT_OLLAMA_VISION_URL).strip().rstrip("/")
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("OLLAMA_VISION_URL must be a credential-free loopback URL.")
    return url


def configured_ollama_vision(config_path: Path) -> OllamaVisionConfig:
    """Resolve local-only Ollama vision settings without credentials."""
    config = _load_config(config_path)
    enabled_value = os.environ.get(
        "OLLAMA_VISION_ENABLED", config.get("ollama_vision_enabled", "1")
    )
    url_value = os.environ.get(
        "OLLAMA_VISION_URL",
        str(config.get("ollama_vision_url", DEFAULT_OLLAMA_VISION_URL)),
    )
    model = os.environ.get(
        "OLLAMA_VISION_MODEL",
        str(config.get("ollama_vision_model", DEFAULT_OLLAMA_VISION_MODEL)),
    ).strip()
    if not model:
        model = DEFAULT_OLLAMA_VISION_MODEL

    return OllamaVisionConfig(
        enabled=_enabled(enabled_value),
        url=_local_ollama_url(url_value),
        model=model,
    )
