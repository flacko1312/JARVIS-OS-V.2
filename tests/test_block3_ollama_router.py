"""Block 3 — Ollama vision config, Fallback Local, Router core, Schedule Safety.

Existing tests in test_screen_processor.py cover _direct_vision_answer,
_local_vision_answer, and _request_ollama_vision_answer. This file covers
vision_model.py config, schedule_safety.py, router/core.py handlers, and
router/classifier.py edge cases not covered in Block 1.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from router.classifier import classify
from router.models import Domain, RouteResult


def _run(coro):
    """Run an async coroutine from sync test code (Python 3.14+ safe)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# A — VISION MODEL CONFIG (core/vision_model.py)
# ---------------------------------------------------------------------------

class TestVisionModelConfig(unittest.TestCase):

    def test_default_vision_model(self):
        from core.vision_model import DEFAULT_VISION_MODEL
        self.assertEqual(DEFAULT_VISION_MODEL, "gemini-3.8-flash")

    def test_default_fallback_model(self):
        from core.vision_model import DEFAULT_VISION_FALLBACK_MODEL
        self.assertEqual(DEFAULT_VISION_FALLBACK_MODEL, "gemini-3.6-flash")

    def test_default_ollama_model(self):
        from core.vision_model import DEFAULT_OLLAMA_VISION_MODEL
        self.assertEqual(DEFAULT_OLLAMA_VISION_MODEL, "qwen3-vl:4b-instruct")

    def test_config_file_overrides_default(self):
        from core.vision_model import configured_vision_model
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "api_keys.json"
            config.write_text(json.dumps({"vision_model": "custom-model"}))
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_VISION_MODEL", None)
                result = configured_vision_model(config)
        self.assertEqual(result, "custom-model")

    def test_env_overrides_config(self):
        from core.vision_model import configured_vision_model
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "api_keys.json"
            config.write_text(json.dumps({"vision_model": "config-model"}))
            with patch.dict(os.environ, {"GEMINI_VISION_MODEL": "env-model"}):
                result = configured_vision_model(config)
        self.assertEqual(result, "env-model")

    def test_missing_config_uses_default(self):
        from core.vision_model import configured_vision_model, DEFAULT_VISION_MODEL
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_VISION_MODEL", None)
            result = configured_vision_model(Path("/nonexistent/config.json"))
        self.assertEqual(result, DEFAULT_VISION_MODEL)


class TestOllamaVisionConfig(unittest.TestCase):

    def test_defaults(self):
        from core.vision_model import configured_ollama_vision
        with patch.dict(os.environ, {}, clear=False):
            for key in ("OLLAMA_VISION_ENABLED", "OLLAMA_VISION_URL", "OLLAMA_VISION_MODEL"):
                os.environ.pop(key, None)
            config = configured_ollama_vision(Path("/nonexistent/config.json"))
        self.assertTrue(config.enabled)
        self.assertEqual(config.url, "http://127.0.0.1:11434")
        self.assertEqual(config.model, "qwen3-vl:4b-instruct")

    def test_disabled(self):
        from core.vision_model import configured_ollama_vision
        with patch.dict(os.environ, {"OLLAMA_VISION_ENABLED": "false"}):
            config = configured_ollama_vision(Path("/nonexistent.json"))
        self.assertFalse(config.enabled)

    def test_remote_url_rejected(self):
        from core.vision_model import configured_ollama_vision
        with patch.dict(os.environ, {"OLLAMA_VISION_URL": "http://192.168.1.10:11434"}):
            with self.assertRaises(ValueError):
                configured_ollama_vision(Path("/nonexistent.json"))

    def test_credentialed_url_rejected(self):
        from core.vision_model import configured_ollama_vision
        with patch.dict(os.environ, {"OLLAMA_VISION_URL": "http://user:pass@127.0.0.1:11434"}):
            with self.assertRaises(ValueError):
                configured_ollama_vision(Path("/nonexistent.json"))

    def test_custom_url_and_model(self):
        from core.vision_model import configured_ollama_vision
        with patch.dict(os.environ, {
            "OLLAMA_VISION_URL": "http://localhost:11435",
            "OLLAMA_VISION_MODEL": "llava:7b",
        }):
            config = configured_ollama_vision(Path("/nonexistent.json"))
        self.assertEqual(config.url, "http://localhost:11435")
        self.assertEqual(config.model, "llava:7b")

    def test_trailing_slash_stripped(self):
        from core.vision_model import configured_ollama_vision
        with patch.dict(os.environ, {"OLLAMA_VISION_URL": "http://127.0.0.1:11434/"}):
            config = configured_ollama_vision(Path("/nonexistent.json"))
        self.assertFalse(config.url.endswith("/"))

    def test_enabled_parsing_variants(self):
        from core.vision_model import _enabled
        self.assertTrue(_enabled("1"))
        self.assertTrue(_enabled("true"))
        self.assertTrue(_enabled("yes"))
        self.assertTrue(_enabled("on"))
        self.assertTrue(_enabled(None, default=True))
        self.assertFalse(_enabled("0"))
        self.assertFalse(_enabled("false"))
        self.assertFalse(_enabled("no"))
        self.assertFalse(_enabled("off"))


class TestFallbackModelConfig(unittest.TestCase):

    def test_default_fallback(self):
        from core.vision_model import configured_vision_fallback_model, DEFAULT_VISION_FALLBACK_MODEL
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_VISION_FALLBACK_MODEL", None)
            result = configured_vision_fallback_model(Path("/nonexistent.json"))
        self.assertEqual(result, DEFAULT_VISION_FALLBACK_MODEL)

    def test_env_override(self):
        from core.vision_model import configured_vision_fallback_model
        with patch.dict(os.environ, {"GEMINI_VISION_FALLBACK_MODEL": "custom-fallback"}):
            result = configured_vision_fallback_model(Path("/nonexistent.json"))
        self.assertEqual(result, "custom-fallback")


# ---------------------------------------------------------------------------
# B — SCHEDULE SAFETY (core/schedule_safety.py)
# ---------------------------------------------------------------------------

class TestScheduleSemantics(unittest.TestCase):

    def test_immediate(self):
        from core.schedule_safety import schedule_semantics
        self.assertEqual(schedule_semantics("enciende la luz"), "immediate")
        self.assertEqual(schedule_semantics("abre Spotify"), "immediate")

    def test_recurring_spanish(self):
        from core.schedule_safety import schedule_semantics
        self.assertEqual(schedule_semantics("todos los dias enciende la luz"), "recurring")
        self.assertEqual(schedule_semantics("cada manana prende la lampara"), "recurring")
        self.assertEqual(schedule_semantics("automatiza el riego"), "recurring")

    def test_recurring_english(self):
        from core.schedule_safety import schedule_semantics
        self.assertEqual(schedule_semantics("every day turn on the light"), "recurring")
        self.assertEqual(schedule_semantics("automate the watering"), "recurring")

    def test_one_shot_spanish(self):
        from core.schedule_safety import schedule_semantics
        self.assertEqual(schedule_semantics("recuerdame a las 3"), "one_shot")
        self.assertEqual(schedule_semantics("manana a las 8 enciende la luz"), "one_shot")
        self.assertEqual(schedule_semantics("dentro de 30 minutos apaga"), "one_shot")

    def test_one_shot_english(self):
        from core.schedule_safety import schedule_semantics
        self.assertEqual(schedule_semantics("remind me at 3"), "one_shot")
        self.assertEqual(schedule_semantics("in 30 minutes turn off"), "one_shot")

    def test_iso_date_is_one_shot(self):
        from core.schedule_safety import schedule_semantics
        self.assertEqual(schedule_semantics("2026-10-15 haz algo"), "one_shot")


class TestDailyTimeFromText(unittest.TestCase):

    def test_24h_format(self):
        from core.schedule_safety import daily_time_from_text
        self.assertEqual(daily_time_from_text("a las 14:30"), (14, 30))
        self.assertEqual(daily_time_from_text("prende a las 8:00 de la manana"), (8, 0))

    def test_am_pm(self):
        from core.schedule_safety import daily_time_from_text
        self.assertEqual(daily_time_from_text("at 3pm"), (15, 0))
        self.assertEqual(daily_time_from_text("at 11am"), (11, 0))

    def test_spanish_spoken_time(self):
        from core.schedule_safety import daily_time_from_text
        self.assertEqual(daily_time_from_text("a las tres de la tarde"), (15, 0))
        self.assertEqual(daily_time_from_text("a las ocho de la manana"), (8, 0))

    def test_ambiguous_returns_none(self):
        from core.schedule_safety import daily_time_from_text
        self.assertIsNone(daily_time_from_text("a las 5"))

    def test_no_time_returns_none(self):
        from core.schedule_safety import daily_time_from_text
        self.assertIsNone(daily_time_from_text("enciende la luz"))


class TestNormalizedTurnText(unittest.TestCase):

    def test_accent_removal(self):
        from core.schedule_safety import normalized_turn_text
        result = normalized_turn_text("Apágala mañana")
        self.assertEqual(result, "apagala manana")

    def test_whitespace_normalization(self):
        from core.schedule_safety import normalized_turn_text
        result = normalized_turn_text("  hola   mundo  ")
        self.assertEqual(result, "hola mundo")


class TestNormalizeTimezone(unittest.TestCase):

    def test_default_madrid(self):
        from core.schedule_safety import normalize_timezone
        self.assertEqual(normalize_timezone(None), "Europe/Madrid")
        self.assertEqual(normalize_timezone(""), "Europe/Madrid")

    def test_local_aliases(self):
        from core.schedule_safety import normalize_timezone
        self.assertEqual(normalize_timezone("madrid"), "Europe/Madrid")
        self.assertEqual(normalize_timezone("hora local"), "Europe/Madrid")

    def test_valid_iana(self):
        from core.schedule_safety import normalize_timezone
        self.assertEqual(normalize_timezone("America/New_York"), "America/New_York")

    def test_invalid_returns_none(self):
        from core.schedule_safety import normalize_timezone
        self.assertIsNone(normalize_timezone("Mars/Olympus"))


# ---------------------------------------------------------------------------
# C — ROUTER CLASSIFIER edge cases
# ---------------------------------------------------------------------------

class TestClassifierEdgeCases(unittest.TestCase):

    def test_empty_input_fallback(self):
        result = classify("")
        self.assertEqual(result.domain, Domain.CONVERSATION)
        self.assertTrue(result.params.get("fallback"))

    def test_mixed_language(self):
        result = classify("busca en google machine learning")
        self.assertEqual(result.domain, Domain.WEB)

    def test_home_entities(self):
        result = classify("enciende la luz del salon")
        self.assertEqual(result.domain, Domain.HOME)

    def test_memory_store(self):
        result = classify("recuerda que mi cumpleanos es el 15 de octubre")
        self.assertEqual(result.domain, Domain.MEMORY)

    def test_local_ai(self):
        result = classify("usa ollama para resumir esto")
        self.assertEqual(result.domain, Domain.LOCAL_AI)

    def test_development(self):
        result = classify("con codex arregla el bug en main.py")
        self.assertEqual(result.domain, Domain.DEVELOPMENT)

    def test_knowledge(self):
        result = classify("investiga sobre inteligencia artificial")
        self.assertEqual(result.domain, Domain.KNOWLEDGE)

    def test_vision(self):
        result = classify("que ves en la pantalla")
        self.assertEqual(result.domain, Domain.VISION)

    def test_files(self):
        result = classify("muestra archivos del escritorio")
        self.assertEqual(result.domain, Domain.FILES)

    def test_conversation_greeting(self):
        result = classify("hola buenos dias")
        self.assertEqual(result.domain, Domain.CONVERSATION)

    def test_raw_input_preserved(self):
        result = classify("enciende la lampara")
        self.assertEqual(result.params["raw_input"], "enciende la lampara")


# ---------------------------------------------------------------------------
# D — ROUTER CORE (router/core.py)
# ---------------------------------------------------------------------------

class TestParseHomeCommand(unittest.TestCase):

    def test_turn_on(self):
        from router.core import _parse_home_command
        service, ref = _parse_home_command("enciende la luz del salon")
        self.assertEqual(service, "turn_on")
        self.assertIn("luz", ref)

    def test_turn_off(self):
        from router.core import _parse_home_command
        service, ref = _parse_home_command("apaga la lampara")
        self.assertEqual(service, "turn_off")
        self.assertIn("lampara", ref)

    def test_no_command(self):
        from router.core import _parse_home_command
        service, ref = _parse_home_command("que temperatura tiene la casa")
        self.assertIsNone(service)

    def test_filler_removed(self):
        from router.core import _parse_home_command
        service, ref = _parse_home_command("enciende la luz por favor ahora")
        self.assertEqual(service, "turn_on")
        self.assertNotIn("por favor", ref)
        self.assertNotIn("ahora", ref)


class TestRouterHandlers(unittest.TestCase):

    def _make_router(self):
        from router.core import JarvisRouter
        client = MagicMock()
        monitor = MagicMock()
        monitor.status.is_available = True
        return JarvisRouter(client, monitor)

    def test_classify_delegates(self):
        router = self._make_router()
        result = router.classify("hola")
        self.assertIsInstance(result, RouteResult)

    def test_conversation_handler(self):
        router = self._make_router()
        result = RouteResult(Domain.CONVERSATION, "conversation", 0.7, {"raw_input": "hola"})
        response = _run(router.execute(result))
        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "chat")

    def test_gemini_passthrough(self):
        router = self._make_router()
        result = RouteResult(Domain.WINDOWS, "windows", 0.9, {"raw_input": "abre chrome"})
        response = _run(router.execute(result))
        self.assertTrue(response["ok"])
        self.assertTrue(response.get("pass_to_conversation"))

    def test_local_ai_uses_local_provider(self):
        from core.local_ai import LocalAIResponse, LocalAIState, LocalAIStatus
        provider = MagicMock()
        provider.generate = AsyncMock(return_value=LocalAIResponse(
            True,
            "respuesta local",
            LocalAIStatus(LocalAIState.ONLINE, "qwen-test", "ok"),
        ))
        router = self._make_router()
        router._local_ai = provider
        result = RouteResult(Domain.LOCAL_AI, "local_ai", 0.8, {"raw_input": "usa ollama"})
        response = _run(router.execute(result))
        self.assertTrue(response["ok"])
        self.assertEqual(response["message"], "respuesta local")

    def test_lilith_offline(self):
        from router.core import JarvisRouter
        client = MagicMock()
        monitor = MagicMock()
        monitor.status.is_available = False
        router = JarvisRouter(client, monitor)
        result = RouteResult(Domain.HOME, "home", 0.9, {"raw_input": "enciende la luz"})
        response = _run(router.execute(result))
        self.assertFalse(response["ok"])
        self.assertTrue(response.get("offline"))

    def test_memory_store(self):
        router = self._make_router()
        router._client.store_memory = AsyncMock(return_value={"stored": True})
        result = RouteResult(Domain.MEMORY, "memory", 0.9, {"raw_input": "recuerda que mi color favorito es azul"})
        response = _run(router.execute(result))
        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "store")
        router._client.store_memory.assert_awaited_once()

    def test_memory_search(self):
        router = self._make_router()
        router._client.search_memory = AsyncMock(return_value=[])
        result = RouteResult(Domain.MEMORY, "memory", 0.9, {"raw_input": "que sabes de mi color favorito"})
        response = _run(router.execute(result))
        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "search")

    def test_home_scheduled_blocked(self):
        router = self._make_router()
        result = RouteResult(Domain.HOME, "home", 0.9, {"raw_input": "todos los dias enciende la luz a las 8"})
        response = _run(router.execute(result))
        self.assertFalse(response["ok"])
        self.assertTrue(response.get("scheduled_request"))

    def test_home_no_entity(self):
        router = self._make_router()
        result = RouteResult(Domain.HOME, "home", 0.9, {"raw_input": "que temperatura tiene la casa"})
        response = _run(router.execute(result))
        self.assertTrue(response["ok"])
        self.assertTrue(response.get("needs_clarification"))


class TestHomeErrorMessage(unittest.TestCase):

    def test_denied_code(self):
        from router.core import JarvisRouter
        from lilith_client.errors import LilithError
        exc = LilithError("denied", code="domain_not_allowed")
        msg = JarvisRouter._home_error_message(exc, "lampara")
        self.assertIn("permiso", msg)

    def test_entity_not_found(self):
        from router.core import JarvisRouter
        from lilith_client.errors import LilithError
        exc = LilithError("not found", code="entity_not_found")
        msg = JarvisRouter._home_error_message(exc, "lampara")
        self.assertIn("lampara", msg)

    def test_unknown_code(self):
        from router.core import JarvisRouter
        from lilith_client.errors import LilithError
        exc = LilithError("wat", code="unknown_xyz")
        msg = JarvisRouter._home_error_message(exc, "lampara")
        self.assertIn("unknown_xyz", msg)


if __name__ == "__main__":
    unittest.main()
