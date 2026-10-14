import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from actions import file_processor, screen_processor, youtube_video


class SpanishLanguagePolicyTests(unittest.TestCase):
    def test_base_rule_defaults_to_spanish_and_allows_explicit_override(self):
        self.assertIn(
            "El idioma de interacción del usuario es español",
            main.LANGUAGE_RULE,
        )
        self.assertIn(
            "salvo que el usuario solicite explícitamente otro idioma",
            main.LANGUAGE_RULE,
        )
        self.assertIn("respuestas posteriores a herramientas", main.LANGUAGE_RULE)

    def test_loaded_prompt_starts_with_the_language_contract(self):
        prompt = main._load_system_prompt()
        self.assertTrue(prompt.startswith(main.LANGUAGE_RULE))
        self.assertIn("errores, confirmaciones", prompt)

    def test_live_config_reasserts_spanish_after_tool_continuity(self):
        jarvis = object.__new__(main.JarvisLive)
        jarvis.voice_name = main.DEFAULT_VOICE_NAME
        jarvis.tool_declarations = []
        with patch.object(main, "load_memory", return_value={}), patch.object(
            main, "_load_system_prompt", return_value="PROMPT PRINCIPAL"
        ):
            config = jarvis._build_config(
                local_continuity=(
                    "[RESULTADO DE HERRAMIENTA] The operation completed successfully."
                )
            )
        instruction = config.system_instruction
        self.assertGreater(
            instruction.rfind(main.LANGUAGE_RULE),
            instruction.find("The operation completed successfully."),
        )

    def test_secondary_models_receive_the_same_default(self):
        self.assertIn("Responde siempre en español", screen_processor._SYSTEM_PROMPT)
        source = Path(youtube_video.__file__).read_text(encoding="utf-8")
        self.assertIn("Responde siempre en español", source)

    def test_file_ai_prepends_spanish_rule(self):
        captured = {}

        class Models:
            def generate_content(self, **kwargs):
                captured.update(kwargs)
                return type("Response", (), {"text": "Resultado"})()

        client = type("Client", (), {"models": Models()})()
        with patch.object(file_processor, "_gemini_client", return_value=client), patch.object(
            file_processor, "configured_text_model", return_value="test-model"
        ):
            result = file_processor._generate_content(["Explain this file."])
        self.assertEqual(result, "Resultado")
        self.assertTrue(captured["contents"][0].startswith("El idioma de interacción"))


if __name__ == "__main__":
    unittest.main()
