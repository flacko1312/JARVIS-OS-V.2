"""Routing matrix for the autonomous router-completion pass."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from router.classifier import classify
from router.core import JarvisRouter
from router.models import Domain, RouteResult
from runtime import JarvisRuntime


class ClassifierMatrixTests(unittest.TestCase):
    def test_explicit_domain_matrix(self):
        cases = {
            "Lee mis correos": Domain.GMAIL,
            "Escribe un correo a ana@example.test": Domain.GMAIL,
            "Busca en Gmail el mensaje de prueba": Domain.GMAIL,
            "Pon música": Domain.MULTIMEDIA,
            "Pausa la música": Domain.MULTIMEDIA,
            "Sube el volumen": Domain.MULTIMEDIA,
            "Recuérdame mañana llamar al médico": Domain.REMINDERS,
            "Cancela el recordatorio de prueba": Domain.REMINDERS,
            "Crea una presentación sobre seguridad": Domain.PRESENTATIONS,
            "Edita el PowerPoint trimestral": Domain.PRESENTATIONS,
            "Respóndeme usando la IA local": Domain.LOCAL_AI,
            "Usa Ollama para resumir esto": Domain.LOCAL_AI,
            "Arregla mi aplicación Spotify": Domain.DEVELOPMENT,
            "Abre Spotify": Domain.WINDOWS,
            "¿Qué es Spotify?": Domain.CONVERSATION,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify(text).domain, expected)

    def test_local_ai_is_not_a_lilith_domain(self):
        result = classify("Respóndeme usando la IA local")
        self.assertFalse(result.requires_lilith)

    def test_risky_mixed_intent_is_marked_ambiguous(self):
        result = classify("Abre el archivo y lee mis correos")
        self.assertTrue(result.params.get("ambiguous"))
        self.assertIn("files", result.params.get("rival_domains", []))


class HandlerRegistrationTests(unittest.TestCase):
    def setUp(self):
        monitor = MagicMock()
        monitor.status.is_available = False
        self.router = JarvisRouter(MagicMock(), monitor)

    def test_new_domains_are_local_gemini_passthroughs(self):
        for domain in (
            Domain.GMAIL,
            Domain.MULTIMEDIA,
            Domain.REMINDERS,
            Domain.PRESENTATIONS,
        ):
            with self.subTest(domain=domain.value):
                result = RouteResult(domain, domain.value, 0.94, {"raw_input": "test"})
                response = asyncio.run(self.router.execute(result))
                self.assertTrue(response["ok"])
                self.assertTrue(response["pass_to_conversation"])
                self.assertNotIn("offline", response)


class RuntimeAmbiguityTests(unittest.TestCase):
    def test_ambiguous_action_requests_clarification_before_dispatch(self):
        runtime = JarvisRuntime.__new__(JarvisRuntime)
        runtime._router = SimpleNamespace(
            classify=lambda _text: RouteResult(
                Domain.GMAIL,
                "gmail",
                0.94,
                {
                    "raw_input": "abre el archivo y lee mis correos",
                    "ambiguous": True,
                    "rival_domains": ["files"],
                },
            ),
        )
        result = asyncio.run(runtime.process_input("abre el archivo y lee mis correos"))
        self.assertTrue(result["handled"])
        self.assertFalse(result["pass_to_conversation"])
        self.assertIn("exactamente", result["message"])
        self.assertTrue(result["data"]["needs_clarification"])
        self.assertEqual(result["data"]["choices"], ["gmail", "files"])


if __name__ == "__main__":
    unittest.main()
