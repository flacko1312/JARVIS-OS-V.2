import asyncio

import pytest

from core.multiroom_transport import MultiroomClient, MultiroomServer, TransportError


KEY = b"K" * 32


def test_loopback_authenticated_ack_and_payload():
    async def scenario():
        received = []

        async def handler(payload):
            received.append(payload)
            return {"ok": True, "ack": payload["sequence"], "session": payload["session"]}

        server = MultiroomServer(KEY, on_message=handler)
        host, port = await server.start()
        try:
            response = await MultiroomClient(KEY).send(host, port, {
                "session": "s1", "kind": "prepare", "sequence": 1,
            })
            assert response == {"ok": True, "ack": 1, "session": "s1"}
            assert received[0]["kind"] == "prepare"
        finally:
            await server.close()

    asyncio.run(scenario())


def test_wrong_key_is_rejected_and_counted():
    async def scenario():
        server = MultiroomServer(KEY)
        host, port = await server.start()
        try:
            with pytest.raises(TransportError):
                await MultiroomClient(b"W" * 32, retries=0).send(host, port, {"sequence": 1})
            assert server.rejected == 1
        finally:
            await server.close()

    asyncio.run(scenario())


def test_reconnect_retries_after_unavailable_peer():
    async def scenario():
        client = MultiroomClient(KEY, retries=1)
        with pytest.raises(TransportError):
            await client.send("127.0.0.1", 1, {"sequence": 1})

    asyncio.run(scenario())


def test_invalid_key_and_retry_limits_fail_closed():
    with pytest.raises(TransportError):
        MultiroomServer(b"short")
    with pytest.raises(TransportError):
        MultiroomClient(KEY, retries=4)
