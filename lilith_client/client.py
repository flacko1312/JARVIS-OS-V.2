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
    def _detail(resp: httpx.Response) -> dict:
        """Structured error detail ({code, message, retryable}) if the body has one."""
        try:
            detail = resp.json().get("detail", {}) if resp.content else {}
        except ValueError:
            return {}
        return detail if isinstance(detail, dict) else {"message": str(detail)}

    @staticmethod
    def _handle_response(resp: httpx.Response) -> dict:
        # JL-H005: keep LILITH's structured error code (e.g. entity_unavailable) so the
        # caller can report the real reason instead of a generic "HTTP 502".
        detail = LilithClient._detail(resp)
        code = detail.get("code")
        if resp.status_code == 401:
            raise LilithAuthError()
        if resp.status_code == 403:
            raise LilithForbiddenError(detail.get("message", "Acceso denegado"), code=code or "forbidden")
        if resp.status_code == 404:
            exc = LilithNotFoundError(detail.get("message", "No encontrado"))
            if code:
                exc.code = code
            raise exc
        if resp.status_code >= 500:
            exc = LilithServerError(detail.get("message") or f"HTTP {resp.status_code}")
            if code:
                exc.code = code
            exc.retryable = bool(detail.get("retryable", True))
            raise exc
        if resp.status_code >= 400:
            from lilith_client.errors import LilithError
            raise LilithError(
                detail.get("message", f"HTTP {resp.status_code}"),
                code=code or "bad_request", retryable=bool(detail.get("retryable", False)),
            )

        body = resp.json()
        if not body.get("ok", False):
            from lilith_client.errors import LilithError
            raise LilithError(
                body.get("message", "Error desconocido"),
                code=body.get("code", "unknown"), retryable=body.get("retryable", False),
            )

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

    # ── 6. Home Resolve (JL-H005) ───────────────────────────────────────

    async def home_resolve(self, query: str) -> dict:
        """Resolve a natural device reference to an entity_id (read-only).

        Returns ``{"status": resolved|ambiguous|unknown|not_allowed, ...}``. LILITH owns
        the entities and the authorization; this never executes anything.
        """
        return await self._request("POST", f"{_INTEGRATION}/home/resolve", json={"query": query})
