"""Outbound WebSocket adapter connector for AURORA Windows → LILITH Core.

Phase 2 + Phase 4: connection, hello/welcome, catalog publication, heartbeat,
and four Windows read-only capabilities.

Deploy this file to C:\\JARVIS\\lilith_client\\adapter_connector.py

Environment variables consumed:
  ADAPTER_CONNECTION_ENABLED     (default: false) — master on/off switch
  ADAPTER_INVOKE_READONLY_ENABLED (default: false) — gate for Phase 4 handlers
  LILITH_API_URL                  — e.g. http://192.168.1.51:8000
  ADAPTER_TOKEN                   — shared secret from Core .env

AURORA continues to operate normally if LILITH is unreachable.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger("aurora.adapter_connector")

HEARTBEAT_INTERVAL = 15.0
BACKOFF_SCHEDULE = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)
JITTER_FACTOR = 0.5
ADAPTER_ID = "adapter.aurora.windows"
PROTOCOL_VERSION = "1.0.0"
MAX_RESULT_BYTES = 128 * 1024

# Phase 4 Windows allowlist — must match core/adapters/windows_readonly.py
_WINDOWS_PILOT_CAPABILITIES: dict[str, tuple[str, float]] = {
    "windows.system.metrics.read": ("system.read", 5.0),
    "windows.application.list": ("application.read", 8.0),
    "windows.window.list": ("window.read", 8.0),
    "windows.audio.device.list": ("catalog.read", 5.0),
}


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _is_enabled() -> bool:
    return os.environ.get("ADAPTER_CONNECTION_ENABLED", "false").lower() == "true"


def _invoke_readonly_enabled() -> bool:
    return os.environ.get("ADAPTER_INVOKE_READONLY_ENABLED", "false").lower() == "true"


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


# ---------------------------------------------------------------------------
# Availability predicates (queried at catalog-build time)
# ---------------------------------------------------------------------------

def _has_interactive_session() -> bool:
    """True when Windows reports an active interactive console session."""
    try:
        import ctypes
        # 0xFFFFFFFF means no active console session
        return ctypes.windll.kernel32.WTSGetActiveConsoleSessionId() != 0xFFFFFFFF
    except Exception:
        # Unknown session state must never expose windows as available.
        return False


def _has_audio_hardware() -> bool:
    """True when at least one audio device is detectable."""
    try:
        import sounddevice as sd
        return len(sd.query_devices()) > 0
    except Exception:
        pass
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            return pa.get_device_count() > 0
        finally:
            pa.terminate()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Catalog builder
# ---------------------------------------------------------------------------

def _build_windows_catalog() -> list[dict[str, Any]]:
    """Publish 6 Phase-2 legacy entries + 4 Phase-4 canonical entries."""
    schema_v = "1.0"
    empty_input: dict[str, Any] = {
        "type": "object", "properties": {}, "additionalProperties": False,
    }

    caps: list[dict[str, Any]] = []

    # --- 6 legacy Phase-2 AURORA entries (non-canonical IDs, presence-only) ---
    for cap_id, desc, scopes, timeout in [
        ("system.health",    "Report overall system health status",        ("system.read",),     5.0),
        ("system.metrics",   "Retrieve CPU, memory, and disk metrics",     ("system.read",),    10.0),
        ("process.list",     "List running processes with basic info",      ("process.read",),   15.0),
        ("service.status",   "Query status of Windows services",           ("service.read",),   10.0),
        ("application.list", "List installed or running applications",     ("application.read",), 15.0),
        ("audio.device.list","List audio input and output devices",        ("catalog.read",),    5.0),
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
            "schema_version": schema_v,
        })

    # Preserve exact six-item Phase 2 catalog while Phase 4 is disabled.
    if not _invoke_readonly_enabled():
        return caps

    interactive = _has_interactive_session()
    audio_ok = _has_audio_hardware()

    # --- 4 canonical Phase-4 entries (invocable when flags enabled) ---

    # windows.system.metrics.read — no predicate
    caps.append({
        "capability_id": "windows.system.metrics.read",
        "version": PROTOCOL_VERSION,
        "platform": "windows",
        "description": "Windows CPU, memory, and disk metrics via psutil",
        "risk_class": "READ_ONLY",
        "operation_class": "READ_ONLY",
        "required_scopes": ["system.read"],
        "timeout_seconds": 5.0,
        "schema_version": schema_v,
        "availability": "AVAILABLE",
        "input_schema": empty_input,
    })

    # windows.application.list — requires interactive_session
    caps.append({
        "capability_id": "windows.application.list",
        "version": PROTOCOL_VERSION,
        "platform": "windows",
        "description": "List running application names (basename only, no arguments)",
        "risk_class": "READ_ONLY",
        "operation_class": "READ_ONLY",
        "required_scopes": ["application.read"],
        "timeout_seconds": 8.0,
        "schema_version": schema_v,
        "availability": "AVAILABLE",
        "interactive_session": interactive,
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    })

    # windows.window.list — requires interactive_session
    caps.append({
        "capability_id": "windows.window.list",
        "version": PROTOCOL_VERSION,
        "platform": "windows",
        "description": "List visible window titles (excludes AURORA/JARVIS titles)",
        "risk_class": "READ_ONLY",
        "operation_class": "READ_ONLY",
        "required_scopes": ["window.read"],
        "timeout_seconds": 8.0,
        "schema_version": schema_v,
        "availability": "AVAILABLE",
        "interactive_session": interactive,
        "input_schema": empty_input,
    })

    # windows.audio.device.list — requires hardware_available
    caps.append({
        "capability_id": "windows.audio.device.list",
        "version": PROTOCOL_VERSION,
        "platform": "windows",
        "description": "List audio device names and directions (no GUIDs, no driver details)",
        "risk_class": "READ_ONLY",
        "operation_class": "READ_ONLY",
        "required_scopes": ["catalog.read"],
        "timeout_seconds": 5.0,
        "schema_version": schema_v,
        "availability": "AVAILABLE",
        "hardware_available": audio_ok,
        "input_schema": empty_input,
    })

    return caps


# ---------------------------------------------------------------------------
# Phase-4 Windows handlers (run via asyncio.to_thread — blocking I/O safe)
# ---------------------------------------------------------------------------

def _handle_system_metrics(parameters: dict[str, Any]) -> Any:
    if parameters:
        raise ValueError("system metrics accepts no parameters")
    import psutil
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory": {
            "total_mb": vm.total // (1024 * 1024),
            "available_mb": vm.available // (1024 * 1024),
            "percent": vm.percent,
        },
        "disk_c": {
            "total_gb": disk.total // (1024 ** 3),
            "free_gb": disk.free // (1024 ** 3),
            "percent": disk.percent,
        },
    }


def _handle_application_list(parameters: dict[str, Any]) -> Any:
    unknown = set(parameters) - {"limit"}
    if unknown:
        raise ValueError("unsupported application parameters")
    limit = parameters.get("limit", 50)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    import os as _os
    import psutil
    seen: set[str] = set()
    result = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info.get("name") or ""
            basename = _os.path.basename(name)[:100]
            if basename and basename not in seen:
                seen.add(basename)
                result.append({"name": basename, "pid": proc.info["pid"]})
                if len(result) >= limit:
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"applications": result}


def _handle_window_list(parameters: dict[str, Any]) -> Any:
    if parameters:
        raise ValueError("window.list accepts no parameters")
    import ctypes
    import ctypes.wintypes

    # Return executable labels, not private window/document/browser-tab titles.
    # The Core API may serve clients beyond this Windows desktop.
    labels: list[str] = []
    import psutil

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM,
    )

    def _enum_cb(hwnd: int, _lparam: int) -> bool:
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        if ctypes.windll.user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        pid = ctypes.wintypes.DWORD(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return True
        try:
            name = psutil.Process(pid.value).name()[:80]
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return True
        if "AURORA" in name.upper() or "JARVIS" in name.upper():
            return True
        if len(labels) < 100:
            labels.append(name)
        return True

    cb = EnumWindowsProc(_enum_cb)
    ctypes.windll.user32.EnumWindows(cb, 0)
    return {"windows": labels, "titles_redacted": True}


def _handle_audio_device_list(parameters: dict[str, Any]) -> Any:
    if parameters:
        raise ValueError("audio.device.list accepts no parameters")

    result: list[dict[str, Any]] = []

    try:
        import sounddevice as sd
        for device in sd.query_devices():
            direction = []
            if (device.get("max_input_channels") or 0) > 0:
                direction.append("input")
            if (device.get("max_output_channels") or 0) > 0:
                direction.append("output")
            result.append({"name": str(device["name"])[:100], "direction": direction})
        return {"devices": result[:50]}
    except Exception:
        pass

    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                direction = []
                if (info.get("maxInputChannels") or 0) > 0:
                    direction.append("input")
                if (info.get("maxOutputChannels") or 0) > 0:
                    direction.append("output")
                result.append({"name": str(info["name"])[:100], "direction": direction})
        finally:
            pa.terminate()
        return {"devices": result[:50]}
    except Exception:
        pass

    return {"devices": [], "error": "no_audio_library"}


def _execute_windows_capability(capability_id: str, parameters: dict[str, Any]) -> Any:
    """Dispatch table for all four Phase-4 Windows handlers."""
    if capability_id == "windows.system.metrics.read":
        return _handle_system_metrics(parameters)
    if capability_id == "windows.application.list":
        return _handle_application_list(parameters)
    if capability_id == "windows.window.list":
        return _handle_window_list(parameters)
    if capability_id == "windows.audio.device.list":
        return _handle_audio_device_list(parameters)
    raise ValueError("capability is not allowlisted")


# ---------------------------------------------------------------------------
# Adapter connector
# ---------------------------------------------------------------------------

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
        self._send_lock = asyncio.Lock()
        self._stats: dict[str, Any] = {
            "started_at": None,
            "connected_at": None,
            "heartbeats_sent": 0,
            "heartbeats_acked": 0,
            "reconnects": 0,
            "errors": 0,
            "last_error": None,
            "catalog_published": False,
            "catalog_hash": None,
            "invocations_completed": 0,
            "invocations_failed": 0,
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
                    await self._connected_loop(ws)

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

    async def _handshake(self, ws: Any, token: str) -> None:
        hello = {
            "type": "hello",
            "adapter_id": ADAPTER_ID,
            "protocol_version": PROTOCOL_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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

    async def _publish_catalog(self, ws: Any) -> None:
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

    async def _connected_loop(self, ws: Any) -> None:
        """Exactly ONE receiver task + ONE heartbeat task. Never concurrent recv()."""
        heartbeat = asyncio.create_task(self._heartbeat_loop(ws))
        receiver = asyncio.create_task(self._receiver_loop(ws))
        tasks = {heartbeat, receiver}
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    exc = task.exception()
                    if exc is not None:
                        raise exc
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _heartbeat_loop(self, ws: Any) -> None:
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
            async with self._send_lock:
                await ws.send(json.dumps(hb))
            self._stats["heartbeats_sent"] += 1

    async def _receiver_loop(self, ws: Any) -> None:
        while not self._stop_event.is_set():
            raw = await ws.recv()
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESULT_BYTES:
                raise ConnectionError("invalid or oversized Core message")
            message = json.loads(raw)
            message_type = message.get("type")

            if message_type == "heartbeat_ack":
                self._stats["heartbeats_acked"] += 1
            elif message_type == "invoke":
                response = await self._handle_invoke(message)
                async with self._send_lock:
                    await ws.send(json.dumps(response, separators=(",", ":"), default=str))
            elif message_type == "goodbye":
                return
            elif message_type == "error":
                logger.warning(
                    "adapter_connector Core error code=%s",
                    message.get("code", "unknown"),
                )

    async def _handle_invoke(self, message: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        request_id = message.get("request_id")
        correlation_id = message.get("correlation_id")
        capability_id = str(message.get("capability_id", ""))

        def failure(code: str, text: str, *, retryable: bool = False) -> dict[str, Any]:
            self._stats["invocations_failed"] += 1
            return {
                "type": "result",
                "request_id": request_id,
                "correlation_id": correlation_id,
                "capability_id": capability_id or "invalid.capability",
                "ok": False,
                "error_code": code,
                "error_message": text,
                "retryable": retryable,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

        if not _invoke_readonly_enabled():
            return failure("invoke_disabled", "read-only invocation is disabled")
        try:
            UUID(str(request_id))
            UUID(str(correlation_id))
        except (ValueError, TypeError):
            return failure("invalid_request", "invalid request identifiers")
        if message.get("adapter_id") != ADAPTER_ID:
            return failure("invalid_request", "adapter_id mismatch")
        spec = _WINDOWS_PILOT_CAPABILITIES.get(capability_id)
        if spec is None:
            return failure("capability_not_found", "capability is not allowlisted")
        required_scope, timeout = spec
        if message.get("required_scope") != required_scope:
            return failure("forbidden_scope", "required scope mismatch")
        # Availability can change after the catalog was published.
        if capability_id in {"windows.application.list", "windows.window.list"}:
            if not _has_interactive_session():
                return failure("capability_unavailable", "interactive session unavailable")
        if capability_id == "windows.audio.device.list" and not _has_audio_hardware():
            return failure("capability_unavailable", "audio hardware unavailable")
        parameters = message.get("parameters")
        if not isinstance(parameters, dict):
            return failure("schema_mismatch", "parameters must be an object")
        try:
            deadline = datetime.fromisoformat(str(message.get("deadline")))
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
            if deadline.tzinfo is None or remaining <= 0:
                return failure("timeout", "request deadline expired", retryable=True)
        except (ValueError, TypeError):
            return failure("invalid_request", "invalid deadline")

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_execute_windows_capability, capability_id, parameters),
                timeout=min(timeout, remaining),
            )
        except asyncio.TimeoutError:
            return failure("timeout", "capability execution timed out", retryable=True)
        except ValueError as exc:
            return failure("schema_mismatch", str(exc))
        except Exception as exc:
            logger.warning(
                "adapter invocation failed capability=%s type=%s",
                capability_id, type(exc).__name__,
            )
            return failure("execution_failed", "capability execution failed")

        response = {
            "type": "result",
            "request_id": request_id,
            "correlation_id": correlation_id,
            "capability_id": capability_id,
            "ok": True,
            "result": result,
            "retryable": False,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        if len(json.dumps(response, default=str).encode("utf-8")) > MAX_RESULT_BYTES:
            return failure("result_too_large", "capability result exceeds size limit")
        self._stats["invocations_completed"] += 1
        return response

    async def _send_goodbye(self, ws: Any) -> None:
        try:
            goodbye = {
                "type": "goodbye",
                "reason": "clean_shutdown",
                "message": "adapter shutting down",
            }
            await ws.send(json.dumps(goodbye))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_connector: AdapterConnector | None = None


def get_connector() -> AdapterConnector:
    global _connector
    if _connector is None:
        _connector = AdapterConnector()
    return _connector