"""Configuración del cliente LILITH, cargada desde variables de entorno."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LilithConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 10.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> LilithConfig:
        base_url = os.environ.get("LILITH_API_URL", "").rstrip("/")
        if not base_url:
            raise ValueError("LILITH_API_URL no está configurada")
        api_key = os.environ.get("LILITH_API_KEY", "")
        if not api_key:
            raise ValueError("LILITH_API_KEY no está configurada")
        timeout = float(os.environ.get("LILITH_TIMEOUT_SECONDS", "10"))
        max_retries = int(os.environ.get("LILITH_MAX_RETRIES", "2"))
        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout,
            max_retries=max_retries,
        )
