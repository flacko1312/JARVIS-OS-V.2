"""Monitor de disponibilidad de LILITH.

Verifica periódicamente si LILITH responde y expone el estado
de conexión para que el Router y otros módulos de JARVIS puedan
degradar funcionalidad de forma controlada.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from lilith_client.client import LilithClient

logger = logging.getLogger("jarvis.lilith_monitor")


class ConnectionState(Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass
class LilithStatus:
    state: ConnectionState = ConnectionState.UNKNOWN
    last_check: float = 0.0
    last_online: float = 0.0
    services: dict[str, bool] = field(default_factory=dict)
    version: str = ""
    consecutive_failures: int = 0

    @property
    def is_available(self) -> bool:
        return self.state in (ConnectionState.ONLINE, ConnectionState.DEGRADED)

    @property
    def seconds_since_check(self) -> float:
        if self.last_check == 0:
            return float("inf")
        return time.monotonic() - self.last_check

    @property
    def seconds_since_online(self) -> float:
        if self.last_online == 0:
            return float("inf")
        return time.monotonic() - self.last_online


class LilithMonitor:
    """Background monitor que verifica periódicamente la disponibilidad de LILITH."""

    def __init__(
        self,
        client: LilithClient,
        *,
        interval: float = 30.0,
        offline_interval: float = 10.0,
    ):
        self._client = client
        self._interval = interval
        self._offline_interval = offline_interval
        self._status = LilithStatus()
        self._task: asyncio.Task[None] | None = None
        self._callbacks: list[Any] = []

    @property
    def status(self) -> LilithStatus:
        return self._status

    def on_state_change(self, callback) -> None:
        self._callbacks.append(callback)

    async def start(self) -> None:
        if self._task is not None:
            return
        await self._check_once()
        self._task = asyncio.create_task(self._loop())
        logger.info("LilithMonitor iniciado (intervalo=%ss)", self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("LilithMonitor detenido")

    async def check_now(self) -> LilithStatus:
        await self._check_once()
        return self._status

    async def _loop(self) -> None:
        while True:
            interval = (
                self._offline_interval
                if self._status.state == ConnectionState.OFFLINE
                else self._interval
            )
            await asyncio.sleep(interval)
            await self._check_once()

    async def _check_once(self) -> None:
        old_state = self._status.state
        now = time.monotonic()

        try:
            data = await self._client.health()
            self._status.last_check = now
            self._status.services = data.get("services", {})
            self._status.version = data.get("version", "")
            self._status.consecutive_failures = 0

            lilith_status = data.get("status", "unknown")
            if lilith_status == "online":
                self._status.state = ConnectionState.ONLINE
                self._status.last_online = now
            elif lilith_status == "degraded":
                self._status.state = ConnectionState.DEGRADED
                self._status.last_online = now
            else:
                self._status.state = ConnectionState.DEGRADED

        except Exception as exc:
            self._status.last_check = now
            self._status.consecutive_failures += 1
            self._status.state = ConnectionState.OFFLINE
            logger.warning(
                "LILITH no disponible (intento %d): %s",
                self._status.consecutive_failures,
                exc,
            )

        if self._status.state != old_state:
            logger.info(
                "LILITH estado: %s → %s",
                old_state.value,
                self._status.state.value,
            )
            for cb in self._callbacks:
                try:
                    result = cb(old_state, self._status.state)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Error en callback de estado LILITH")
