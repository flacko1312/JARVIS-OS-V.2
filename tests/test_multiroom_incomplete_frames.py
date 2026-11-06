"""Regression: TCP EOF is not an authenticated frame delimiter."""
import asyncio

import pytest

from core.multiroom_transport import MultiroomClient, MultiroomServer, TransportError, _frame

KEY = b"K" * 32


def test_server_rejects_signed_frame_without_newline():
    async def scenario():
        server = MultiroomServer(KEY)
        host, port = await server.start()
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(_frame({"sequence": 1}, KEY).rstrip(b"\n"))
            await writer.drain()
            writer.write_eof()
            response = await asyncio.wait_for(reader.readline(), 2)
            assert b'"ok":false' in response
            assert server.rejected == 1
            writer.close()
            await writer.wait_closed()
        finally:
            await server.close()
    asyncio.run(scenario())


def test_client_rejects_signed_response_without_newline():
    async def scenario():
        async def peer(reader, writer):
            await reader.readline()
            writer.write(_frame({"ok": True}, KEY).rstrip(b"\n"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_server(peer, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            with pytest.raises(TransportError):
                await MultiroomClient(KEY, retries=0).send("127.0.0.1", port, {"sequence": 1})
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(scenario())
