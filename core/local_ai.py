"""Safe loopback-only Ollama text provider for JARVIS."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from core.vision_model import DEFAULT_OLLAMA_VISION_URL, _load_config, _local_ollama_url

DEFAULT_OLLAMA_TEXT_MODEL = "qwen3:4b"


class LocalAIState(str, Enum):
    ONLINE = "online"
    DISABLED = "disabled"
    OFFLINE = "offline"
    MODEL_MISSING = "model_missing"
    ERROR = "error"


@dataclass(frozen=True)
class OllamaTextConfig:
    enabled: bool
    url: str
    model: str
    connect_timeout: float = 3.0
    read_timeout: float = 60.0


@dataclass(frozen=True)
class LocalAIStatus:
    state: LocalAIState
    model: str
    message: str
    available_models: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.state == LocalAIState.ONLINE


@dataclass(frozen=True)
class LocalAIResponse:
    ok: bool
    text: str
    status: LocalAIStatus


def _positive_float(value: object, default: float, *, maximum: float) -> float:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if 0.1 <= parsed <= maximum else default


def configured_ollama_text(config_path: Path) -> OllamaTextConfig:
    """Resolve local text settings without accepting remote or credentialed URLs."""
    config = _load_config(config_path)
    enabled_raw = os.environ.get(
        "OLLAMA_TEXT_ENABLED", config.get("ollama_text_enabled", "1")
    )
    enabled = str(enabled_raw).strip().casefold() not in {"0", "false", "no", "off"}
    url = os.environ.get(
        "OLLAMA_TEXT_URL",
        str(config.get("ollama_text_url", DEFAULT_OLLAMA_VISION_URL)),
    )
    model = os.environ.get(
        "OLLAMA_TEXT_MODEL",
        str(config.get("ollama_text_model", DEFAULT_OLLAMA_TEXT_MODEL)),
    ).strip() or DEFAULT_OLLAMA_TEXT_MODEL
    connect_timeout = _positive_float(
        os.environ.get("OLLAMA_TEXT_CONNECT_TIMEOUT", config.get("ollama_text_connect_timeout")),
        3.0,
        maximum=30.0,
    )
    read_timeout = _positive_float(
        os.environ.get("OLLAMA_TEXT_READ_TIMEOUT", config.get("ollama_text_read_timeout")),
        60.0,
        maximum=300.0,
    )
    try:
        safe_url = _local_ollama_url(url)
    except ValueError as exc:
        raise ValueError(str(exc).replace("OLLAMA_VISION_URL", "OLLAMA_TEXT_URL")) from exc
    return OllamaTextConfig(enabled, safe_url, model, connect_timeout, read_timeout)


class OllamaTextProvider:
    """One-attempt Ollama client; callers decide when a later request should retry."""

    def __init__(self, config: OllamaTextConfig):
        self.config = config

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.config.connect_timeout,
            read=self.config.read_timeout,
            write=self.config.connect_timeout,
            pool=self.config.connect_timeout,
        )

    async def status(self) -> LocalAIStatus:
        if not self.config.enabled:
            return LocalAIStatus(LocalAIState.DISABLED, self.config.model, "IA local desactivada.")
        try:
            async with httpx.AsyncClient(base_url=self.config.url, timeout=self._timeout()) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                payload = response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            return LocalAIStatus(LocalAIState.OFFLINE, self.config.model, "Ollama no está disponible.")
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            return LocalAIStatus(LocalAIState.ERROR, self.config.model, "Ollama respondió con un error.")

        names = tuple(sorted({
            str(item.get("name") or item.get("model") or "").strip()
            for item in payload.get("models", [])
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        }))
        if self.config.model not in names:
            return LocalAIStatus(
                LocalAIState.MODEL_MISSING,
                self.config.model,
                f"El modelo local configurado '{self.config.model}' no está instalado.",
                names,
            )
        return LocalAIStatus(LocalAIState.ONLINE, self.config.model, "Ollama disponible.", names)

    async def generate(self, prompt: str) -> LocalAIResponse:
        prompt = str(prompt or "").strip()
        if not prompt:
            status = LocalAIStatus(LocalAIState.ERROR, self.config.model, "Falta el texto para la IA local.")
            return LocalAIResponse(False, "", status)
        status = await self.status()
        if not status.available:
            return LocalAIResponse(False, "", status)
        payload: dict[str, Any] = {
            "model": self.config.model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            async with httpx.AsyncClient(base_url=self.config.url, timeout=self._timeout()) as client:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
            text = str((body.get("message") or {}).get("content") or "").strip()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            offline = LocalAIStatus(LocalAIState.OFFLINE, self.config.model, "Ollama dejó de estar disponible.")
            return LocalAIResponse(False, "", offline)
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            failed = LocalAIStatus(LocalAIState.ERROR, self.config.model, "Ollama no pudo generar la respuesta.")
            return LocalAIResponse(False, "", failed)
        if not text:
            failed = LocalAIStatus(LocalAIState.ERROR, self.config.model, "Ollama devolvió una respuesta vacía.")
            return LocalAIResponse(False, "", failed)
        return LocalAIResponse(True, text, status)

    async def capabilities(self) -> dict[str, Any]:
        status = await self.status()
        return {
            "provider": "ollama",
            "local_only": True,
            "text_generation": status.available,
            "configured_model": self.config.model,
            "state": status.state.value,
            "available_models": list(status.available_models),
            "offline_features": ["local_text"] if status.available else [],
        }
