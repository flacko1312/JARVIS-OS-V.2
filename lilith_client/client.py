"""Cliente HTTP asíncrono para la API de integración LILITH."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from lilith_client.config import LilithConfig
from lilith_client.errors import (
    LilithAuthError,
    LilithConnectionError,
    LilithForbiddenError,
    LilithNotFoundError,
    LilithServerError,
    LilithTimeoutError,
)

logger = logging.getLogger("jarvis.lilith_client")

_INTEGRATION = "/api/v1/integration"


class LilithClient:
    """Punto único de comunicación JARVIS → LILITH."""

    def __init__(self, config: LilithConfig | None = None):
        self._cfg = config or LilithConfig.from_env()
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._cfg.base_url,
                headers={
                    "Authorization": f"Bearer {self._cfg.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self._cfg.timeout_seconds),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> LilithClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ── Request internals ───────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
    ) -> dict:
        client = await self._ensure_client()
        last_exc: Exception | None = None
        attempts = 1 + self._cfg.max_retries

        for attempt in range(attempts):
            try:
                resp = await client.request(method, path, json=json)
                return self._handle_response(resp)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(min(2 ** attempt, 5))
                    continue
                raise LilithConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(min(2 ** attempt, 5))
                    continue
                raise LilithTimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise LilithConnectionError(str(exc)) from exc

        raise LilithConnectionError(str(last_exc))

    @staticmethod
    def _handle_response(resp: httpx.Response) -> dict:
        if resp.status_code == 401:
            raise LilithAuthError()
        if resp.status_code == 403:
            detail = resp.json().get("detail", {}) if resp.content else {}
            code = detail.get("code", "forbidden") if isinstance(detail, dict) else "forbidden"
            msg = detail.get("message", "Acceso denegado") if isinstance(detail, dict) else str(detail)
            raise LilithForbiddenError(msg, code=code)
        if resp.status_code == 404:
            detail = resp.json().get("detail", {}) if resp.content else {}
            msg = detail.get("message", "No encontrado") if isinstance(detail, dict) else str(detail)
            raise LilithNotFoundError(msg)
        if resp.status_code >= 500:
            raise LilithServerError(f"HTTP {resp.status_code}")

        body = resp.json()
        if not body.get("ok", False):
            detail = body
            code = detail.get("code", "unknown")
            msg = detail.get("message", "Error desconocido")
            retryable = detail.get("retryable", False)
            from lilith_client.errors import LilithError
            raise LilithError(msg, code=code, retryable=retryable)

        return body.get("data", body)

    # ── 1. Health ───────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Estado de LILITH. No requiere autenticación."""
        return await self._request("GET", f"{_INTEGRATION}/health")

    async def is_available(self) -> bool:
        """Comprueba si LILITH responde. Nunca lanza excepción."""
        try:
            status = await self.health()
            return status.get("status") in ("online", "degraded")
        except Exception:
            return False

    # ── 2. Memory Search ────────────────────────────────────────────────

    async def search_memory(
        self,
        query: str,
        *,
        limit: int = 5,
        session: str | None = None,
    ) -> list[dict]:
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if session:
            payload["session"] = session
        data = await self._request("POST", f"{_INTEGRATION}/memory/search", json=payload)
        return data.get("results", [])

    # ── 3. Memory Store ─────────────────────────────────────────────────

    async def store_memory(
        self,
        key: str,
        value: str,
        *,
        category: str = "jarvis_fact",
        confidence: float = 0.8,
        metadata: dict | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "key": key,
            "value": value,
            "category": category,
            "confidence": confidence,
        }
        if metadata:
            payload["metadata"] = metadata
        return await self._request("POST", f"{_INTEGRATION}/memory/store", json=payload)

    # ── 4. Home Entity ──────────────────────────────────────────────────

    async def home_entity(self, entity_id: str) -> dict:
        return await self._request("GET", f"{_INTEGRATION}/home/entity/{entity_id}")

    # ── 5. Home Action ──────────────────────────────────────────────────

    async def home_action(
        self,
        entity_id: str,
        action: str,
        *,
        parameters: dict | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"entity_id": entity_id, "action": action}
        if parameters:
            payload["parameters"] = parameters
        return await self._request("POST", f"{_INTEGRATION}/home/action", json=payload)
