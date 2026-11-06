"""Transporte TCP seguro para coordinación multiroom.

Transporta únicamente frames de control JSON (prepare/ready/start/ack), no
audio. Está desacoplado de JARVIS y no se inicia automáticamente; las pruebas
usan loopback y una clave efímera en memoria. En producción requiere
provisionamiento de claves y despliegue coordinado en Windows/Ubuntu.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Awaitable, Callable, Mapping


class TransportError(RuntimeError):
    pass


def _canonical(payload: Mapping[str, object]) -> bytes:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _frame(payload: Mapping[str, object], key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise TransportError("transport key too short")
    signature = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    return (json.dumps({"payload": dict(payload), "signature": signature}, separators=(",", ":")) + "\n").encode()


def _verify(frame: bytes, key: bytes) -> dict:
    try:
        envelope = json.loads(frame.decode())
        payload = envelope["payload"]
        signature = envelope["signature"]
        if not isinstance(payload, dict) or not isinstance(signature, str):
            raise ValueError
        expected = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError
        return payload
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise TransportError("invalid or unauthenticated frame") from exc


class MultiroomServer:
    def __init__(self, key: bytes, *, on_message: Callable[[dict], Awaitable[dict]] | None = None) -> None:
        if not isinstance(key, bytes) or len(key) < 32:
            raise TransportError("transport key too short")
        self._key = key
        self._on_message = on_message
        self._server: asyncio.AbstractServer | None = None
        self.address: tuple[str, int] | None = None
        self.rejected = 0

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> tuple[str, int]:
        if self._server is not None:
            raise TransportError("server already started")
        self._server = await asyncio.start_server(self._handle, host, port)
        sock = self._server.sockets[0].getsockname()
        self.address = (str(sock[0]), int(sock[1]))
        return self.address

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=3)
            if not raw or len(raw) > 16_384:
                raise TransportError("invalid frame size")
            payload = _verify(raw, self._key)
            response = await self._on_message(payload) if self._on_message else {"ok": True}
            if not isinstance(response, dict):
                response = {"ok": True}
            writer.write(_frame(response, self._key))
            await writer.drain()
        except (asyncio.TimeoutError, TransportError, ConnectionError):
            self.rejected += 1
            writer.write(_frame({"ok": False, "error": "rejected"}, self._key))
            try:
                await writer.drain()
            except ConnectionError:
                pass
        finally:
            writer.close()
            await writer.wait_closed()


class MultiroomClient:
    def __init__(self, key: bytes, *, retries: int = 1) -> None:
        if not isinstance(key, bytes) or len(key) < 32:
            raise TransportError("transport key too short")
        if type(retries) is not int or retries < 0 or retries > 3:
            raise TransportError("invalid retry count")
        self._key = key
        self._retries = retries

    async def send(self, host: str, port: int, payload: Mapping[str, object]) -> dict:
        last_error: Exception | None = None
        for _attempt in range(self._retries + 1):
            reader = writer = None
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
                writer.write(_frame(payload, self._key))
                await writer.drain()
                raw = await asyncio.wait_for(reader.readline(), timeout=3)
                response = _verify(raw, self._key)
                if response.get("ok") is False:
                    raise TransportError("peer rejected frame")
                return response
            except (OSError, asyncio.TimeoutError, TransportError) as exc:
                last_error = exc
            finally:
                if writer is not None:
                    writer.close()
                    await writer.wait_closed()
        raise TransportError("multiroom transport unavailable") from last_error
