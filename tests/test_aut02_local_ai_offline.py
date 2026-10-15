"""AUT-02 local text provider and connectivity-state tests."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from core.local_ai import (
    LocalAIResponse,
    LocalAIState,
    LocalAIStatus,
    OllamaTextConfig,
    OllamaTextProvider,
    configured_ollama_text,
)
from core.provider_status import Availability, ProviderStatusRegistry
from router.core import JarvisRouter
from router.models import Domain, RouteResult


def _response(method: str, url: str, status: int, payload: dict) -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request(method, url))


class ConfigTests(unittest.TestCase):
    def test_defaults_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"OLLAMA_TEXT_MODEL": "llama-test", "OLLAMA_TEXT_URL": "http://localhost:11434/"},
            clear=False,
        ):
            config = configured_ollama_text(Path(directory) / "missing.json")
        self.assertEqual(config.model, "llama-test")
        self.assertEqual(config.url, "http://localhost:11434")

    def test_remote_and_credentialed_urls_are_rejected(self):
        for url in ("http://192.168.1.2:11434", "http://user:pass@127.0.0.1:11434"):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {"OLLAMA_TEXT_URL": url}, clear=False
            ):
                with self.assertRaisesRegex(ValueError, "loopback"):
                    configured_ollama_text(Path(directory) / "missing.json")


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = OllamaTextProvider(OllamaTextConfig(True, "http://127.0.0.1:11434", "qwen-test"))

    async def test_status_online_and_capabilities(self):
        client = AsyncMock()
        client.get.return_value = _response("GET", "http://127.0.0.1:11434/api/tags", 200, {
            "models": [{"name": "qwen-test"}]
        })
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch("core.local_ai.httpx.AsyncClient", return_value=context):
            status = await self.provider.status()
        self.assertEqual(status.state, LocalAIState.ONLINE)

    async def test_stopped_ollama_is_explicit_offline(self):
        context = AsyncMock()
        context.__aenter__.side_effect = httpx.ConnectError("offline")
        with patch("core.local_ai.httpx.AsyncClient", return_value=context):
            status = await self.provider.status()
        self.assertEqual(status.state, LocalAIState.OFFLINE)

    async def test_missing_model_is_distinct(self):
        client = AsyncMock()
        client.get.return_value = _response("GET", "http://127.0.0.1:11434/api/tags", 200, {
            "models": [{"name": "other"}]
        })
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch("core.local_ai.httpx.AsyncClient", return_value=context):
            status = await self.provider.status()
        self.assertEqual(status.state, LocalAIState.MODEL_MISSING)
        self.assertIn("no está instalado", status.message)

    async def test_generate_has_one_status_check_and_one_chat_request(self):
        client = AsyncMock()
        client.get.return_value = _response("GET", "http://127.0.0.1:11434/api/tags", 200, {
            "models": [{"name": "qwen-test"}]
        })
        client.post.return_value = _response("POST", "http://127.0.0.1:11434/api/chat", 200, {
            "message": {"content": "respuesta local"}
        })
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch("core.local_ai.httpx.AsyncClient", return_value=context):
            result = await self.provider.generate("hola")
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "respuesta local")
        self.assertEqual(client.get.await_count, 1)
        self.assertEqual(client.post.await_count, 1)


class RouterIntegrationTests(unittest.TestCase):
    def test_local_ai_result_is_returned_without_lilith(self):
        provider = MagicMock()
        provider.generate = AsyncMock(return_value=LocalAIResponse(
            True,
            "respuesta local",
            LocalAIStatus(LocalAIState.ONLINE, "qwen-test", "ok"),
        ))
        monitor = MagicMock()
        monitor.status.is_available = False
        router = JarvisRouter(MagicMock(), monitor, local_ai=provider)
        result = asyncio.run(router.execute(RouteResult(
            Domain.LOCAL_AI, "local_ai", 0.92, {"raw_input": "usa ollama para responder"}
        )))
        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "respuesta local")


class RegistryTransitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_distinct_states_and_recovery_are_retained(self):
        provider = MagicMock()
        provider.status = AsyncMock(side_effect=[
            LocalAIStatus(LocalAIState.MODEL_MISSING, "qwen", "missing"),
            LocalAIStatus(LocalAIState.ONLINE, "qwen", "online"),
        ])
        internet = AsyncMock(side_effect=[Availability.UNAVAILABLE, Availability.AVAILABLE])
        gemini = AsyncMock(side_effect=[Availability.TEMPORARY_FAILURE, Availability.AVAILABLE])
        lilith = AsyncMock(side_effect=[Availability.UNAVAILABLE, Availability.AVAILABLE])
        registry = ProviderStatusRegistry(
            provider,
            internet_probe=internet,
            gemini_probe=gemini,
            lilith_probe=lilith,
        )
        first = await registry.refresh()
        second = await registry.refresh()
        self.assertEqual(first.ollama, Availability.MODEL_MISSING)
        self.assertEqual(first.gemini, Availability.TEMPORARY_FAILURE)
        self.assertEqual(second.offline_capabilities, ("local_text",))
        self.assertIn(("ollama", "model_missing", "available"), registry.transitions)


if __name__ == "__main__":
    unittest.main()
