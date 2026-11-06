"""Un callback fallido nunca debe dejar sin respuesta al peer autenticado."""
import asyncio
import pytest
from core.multiroom_transport import MultiroomClient, MultiroomServer, TransportError

KEY = b"K" * 32


def test_callback_exception_rejected_and_server_recovers():
    async def scenario():
        calls = 0
        async def handler(payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("private callback detail")
            return {"ok": True, "ack": payload["sequence"]}
        server = MultiroomServer(KEY, on_message=handler)
        host, port = await server.start()
        try:
            with pytest.raises(TransportError):
                await MultiroomClient(KEY, retries=0).send(host, port, {"sequence": 1})
            assert server.rejected == 1
            assert await MultiroomClient(KEY, retries=0).send(host, port, {"sequence": 2}) == {"ok": True, "ack": 2}
        finally:
            await server.close()
    asyncio.run(scenario())


def test_callback_nonserializable_response_is_rejected():
    async def scenario():
        async def handler(_payload):
            return {"ok": True, "bad": object()}
        server = MultiroomServer(KEY, on_message=handler)
        host, port = await server.start()
        try:
            with pytest.raises(TransportError):
                await MultiroomClient(KEY, retries=0).send(host, port, {"sequence": 1})
            assert server.rejected == 1
        finally:
            await server.close()
    asyncio.run(scenario())
