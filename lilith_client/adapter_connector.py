"""Minimal outbound WebSocket adapter connector for AURORA Windows → LILITH Core.

Phase 2 only: connection, hello/welcome, catalog publication, heartbeat.
NO invoke, NO cancel, NO audio, NO modification of any existing runtime.

When ADAPTER_CONNECTION_ENABLED is false (default), this module does nothing:
zero connections, zero tasks, zero side effects.

AURORA must continue operating normally if LILITH disappears.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("aurora.adapter_connector")

HEARTBEAT_INTERVAL = 15.0
BACKOFF_SCHEDULE = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)
JITTER_FACTOR = 0.5
ADAPTER_ID = "adapter.aurora.windows"
PROTOCOL_VERSION = "1.0.0"


def _is_enabled() -> bool:
    return os.environ.get("ADAPTER_CONNECTION_ENABLED", "false").lower() == "true"


def _get_core_ws_url() -> str:
    base = os.environ.get("LILITH_API_URL", "").rstrip("/")
    if not base:
        raise ValueError("LILITH_API_URL not configured")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/api/v1/adapters/connect"


def _get_adapter_token() -> str:
    token = os.environ.get("ADAPTER_TOKEN", "")
    if not token:
        raise ValueError("ADAPTER_TOKEN not configured")
    return token


def _compute_catalog_hash(capabilities: list[dict[str, Any]]) -> str:
    canonical = json.dumps(capabilities, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_backoff(attempt: int) -> float:
    index = min(max(attempt, 0), len(BACKOFF_SCHEDULE) - 1)
    base = BACKOFF_SCHEDULE[index]
    jitter = random.uniform(0, base * JITTER_FACTOR)
    return base + jitter


def _build_windows_catalog() -> list[dict[str, Any]]:
    """Bootstrap read-only catalog for AURORA Windows adapter."""
    _schema_v = "1.0"
    empty_input = {"type": "object", "properties": {}, "additionalProperties": False}

    caps = []
    for cap_id, desc, scopes, timeout in [
        ("system.health", "Report overall system health status",
         ("system.read",), 5.0),
        ("system.metrics", "Retrieve CPU, memory, and disk usage metrics",
         ("system.read",), 10.0),
        ("process.list", "List running processes with basic info",
         ("process.read",), 15.0),
        ("service.status", "Query status of Windows services",
         ("service.read",), 10.0),
        ("application.list", "List installed or running applications",
         ("application.read",), 15.0),
        ("audio.device.list", "List audio input and output devices",
         ("catalog.read",), 5.0),
    ]:
        caps.append({
            "capability_id": cap_id,
            "version": PROTOCOL_VERSION,
            "platform": "windows",
            "description": desc,
            "risk_class": "READ_ONLY",
            "operation_class": "READ_ONLY",
            "required_scopes": list(scopes),
            "timeout_seconds": timeout,
            "schema_version": _schema_v,
        })
    return caps


class AdapterConnector:
    """Outbound WebSocket connection from AURORA Windows to LILITH Core.

    Lifecycle: start() begins the background task, stop() shuts it down.
    If ADAPTER_CONNECTION_ENABLED is false, start() is a no-op.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._connected = False
        self._session_id: str | None = None
        self._heartbeat_seq = 0
        self._attempt = 0
        self._stats = {
            "started_at": None,
            "connected_at": None,
            "heartbeats_sent": 0,
            "heartbeats_acked": 0,
            "reconnects": 0,
            "errors": 0,
            "last_error": None,
            "catalog_published": False,
            "catalog_hash": None,
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    async def start(self) -> None:
        if not _is_enabled():
            logger.info("adapter_connector disabled (ADAPTER_CONNECTION_ENABLED=false)")
            return
        if self._task is not None:
            return
        self._stop_event.clear()
        self._stats["started_at"] = datetime.now(timezone.utc).isoformat()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("adapter_connector started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._connected = False
        logger.info("adapter_connector stopped")

    async def _run_loop(self) -> None:
        import websockets
        import websockets.exceptions

        while not self._stop_event.is_set():
            try:
                ws_url = _get_core_ws_url()
                token = _get_adapter_token()
            except ValueError as exc:
                logger.error("adapter_connector config error: %s", exc)
                self._stats["errors"] += 1
                self._stats["last_error"] = str(exc)
                await asyncio.sleep(30)
                continue

            try:
                async with websockets.connect(ws_url, open_timeout=10) as ws:
                    await self._handshake(ws, token)
                    self._connected = True
                    self._attempt = 0
                    self._stats["connected_at"] = datetime.now(timezone.utc).isoformat()

                    await self._publish_catalog(ws)
                    await self._heartbeat_loop(ws)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                self._stats["errors"] += 1
                self._stats["last_error"] = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "adapter_connector disconnected: %s (attempt=%d)",
                    exc, self._attempt,
                )

            if self._stop_event.is_set():
                break

            delay = _compute_backoff(self._attempt)
            self._attempt += 1
            self._stats["reconnects"] += 1
            logger.info("adapter_connector reconnecting in %.1fs", delay)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                break
            except asyncio.TimeoutError:
                pass

    async def _handshake(self, ws, token: str) -> None:
        now = datetime.now(timezone.utc)
        hello = {
            "type": "hello",
            "adapter_id": ADAPTER_ID,
            "protocol_version": PROTOCOL_VERSION,
            "timestamp": now.isoformat(),
            "token": token,
        }
        await ws.send(json.dumps(hello))

        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        resp = json.loads(raw)

        if resp.get("type") == "error":
            raise ConnectionError(f"hello rejected: {resp.get('message', 'unknown')}")
        if resp.get("type") != "welcome":
            raise ConnectionError(f"unexpected response: {resp.get('type')}")

        self._session_id = resp.get("session_id")
        self._heartbeat_seq = 0
        logger.info("adapter_connector handshake ok session=%s", self._session_id)

    async def _publish_catalog(self, ws) -> None:
        caps = _build_windows_catalog()
        catalog_hash = _compute_catalog_hash(caps)

        msg = {
            "type": "catalog_publish",
            "adapter_id": ADAPTER_ID,
            "schema_version": "1.0",
            "capabilities": caps,
            "catalog_hash": catalog_hash,
        }
        await ws.send(json.dumps(msg))

        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        resp = json.loads(raw)

        if resp.get("type") == "catalog_ack" and resp.get("accepted"):
            self._stats["catalog_published"] = True
            self._stats["catalog_hash"] = catalog_hash
            logger.info("adapter_connector catalog accepted hash=%s", catalog_hash[:16])
        else:
            reason = resp.get("rejection_reason", resp.get("message", "unknown"))
            logger.warning("adapter_connector catalog rejected: %s", reason)

    async def _heartbeat_loop(self, ws) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
                await self._send_goodbye(ws)
                return
            except asyncio.TimeoutError:
                pass

            self._heartbeat_seq += 1
            hb = {
                "type": "heartbeat",
                "adapter_id": ADAPTER_ID,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sequence": self._heartbeat_seq,
            }
            await ws.send(json.dumps(hb))
            self._stats["heartbeats_sent"] += 1

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                resp = json.loads(raw)
                if resp.get("type") == "heartbeat_ack":
                    self._stats["heartbeats_acked"] += 1
            except asyncio.TimeoutError:
                logger.warning("adapter_connector heartbeat_ack timeout seq=%d", self._heartbeat_seq)

    async def _send_goodbye(self, ws) -> None:
        try:
            goodbye = {
                "type": "goodbye",
                "reason": "clean_shutdown",
                "message": "adapter shutting down",
            }
            await ws.send(json.dumps(goodbye))
        except Exception:
            pass


_connector: AdapterConnector | None = None


def get_connector() -> AdapterConnector:
    global _connector
    if _connector is None:
        _connector = AdapterConnector()
    return _connector
