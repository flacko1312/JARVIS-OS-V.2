"""Central Gemini key, model and client resolution for component consumers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory.config_manager import CONFIG_FILE, get_gemini_key

DEFAULT_GENERAL_MODEL = "gemini-3.8-flash"


def _read_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def component_model(
    component: str,
    *,
    explicit: str | None = None,
    default: str = DEFAULT_GENERAL_MODEL,
    config_path: Path = CONFIG_FILE,
) -> str:
    """Resolve explicit → component env/config → global env/config → default."""
    if str(explicit or "").strip():
        return str(explicit).strip()
    normalized = "_".join(str(component).strip().upper().replace("-", "_").split())
    component_key = normalized.lower() + "_model"
    config = _read_config(config_path)
    return (
        os.environ.get(f"GEMINI_{normalized}_MODEL", "").strip()
        or str(config.get(component_key, "") or "").strip()
        or os.environ.get("GEMINI_TEXT_MODEL", "").strip()
        or str(config.get("text_model", "") or "").strip()
        or default
    )


def gemini_api_key() -> str:
    key = str(get_gemini_key() or "").strip()
    if not key:
        raise RuntimeError("Gemini API key is not configured.")
    return key


def gemini_client(*, api_key: str | None = None, timeout_ms: int | None = None):
    from google import genai
    from google.genai import types

    options = types.HttpOptions(timeout=timeout_ms) if timeout_ms else None
    return genai.Client(api_key=api_key or gemini_api_key(), http_options=options)


@dataclass
class GeminiModelAdapter:
    """Minimal legacy-compatible `generate_content` surface backed by google.genai."""

    model: str
    client: Any

    def generate_content(self, contents: Any, **kwargs: Any):
        config = kwargs.pop("generation_config", None) or kwargs.pop("config", None)
        return self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
            **kwargs,
        )


def component_model_client(
    component: str,
    *,
    explicit_model: str | None = None,
    default_model: str = DEFAULT_GENERAL_MODEL,
    config_path: Path = CONFIG_FILE,
) -> GeminiModelAdapter:
    return GeminiModelAdapter(
        component_model(
            component,
            explicit=explicit_model,
            default=default_model,
            config_path=config_path,
        ),
        gemini_client(),
    )
