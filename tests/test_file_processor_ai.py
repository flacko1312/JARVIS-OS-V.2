import json
import os
import tempfile
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from actions import file_processor
from core import text_model


class TextModelSelectionTests(unittest.TestCase):
    def test_default_is_supported_and_not_retired(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("GEMINI_TEXT_MODEL", None)
            selected = text_model.configured_text_model(
                Path(directory) / "missing.json"
            )

        self.assertEqual(selected, "gemini-3.8-flash")
        self.assertNotEqual(selected, "gemini-2.5-flash")

    def test_config_override_wins_over_default(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("GEMINI_TEXT_MODEL", None)
            config = Path(directory) / "api_keys.json"
            config.write_text(
                json.dumps({"text_model": "configured-text-model"}),
                encoding="utf-8",
            )
            selected = text_model.configured_text_model(config)

        self.assertEqual(selected, "configured-text-model")

    def test_environment_override_wins_over_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "api_keys.json"
            config.write_text(
                json.dumps({"text_model": "configured-text-model"}),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ, {"GEMINI_TEXT_MODEL": "environment-text-model"}
            ):
                selected = text_model.configured_text_model(config)

        self.assertEqual(selected, "environment-text-model")


class FileProcessorAiTests(unittest.TestCase):
    def _markdown_file(self, directory: str) -> Path:
        path = Path(directory) / "audit.md"
        path.write_text("# Audit\n\nVerified visible content.", encoding="utf-8")
        return path

    def test_extract_text_does_not_invoke_gemini(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._markdown_file(directory)
            with patch.object(file_processor, "_gemini_client") as client:
                result = file_processor.file_processor(
                    {"action": "extract_text", "file_path": str(path)}
                )
            self.assertEqual(result, "Text extracted. Saved: audit_extracted.txt")
            self.assertIn(
                "Verified visible content",
                (Path(directory) / "audit_extracted.txt").read_text(
                    encoding="utf-8"
                ),
            )
            client.assert_not_called()

    def test_explain_uses_resolved_model_and_disables_afc(self):
        generate_content = MagicMock(
            return_value=SimpleNamespace(text="Real provider explanation.")
        )
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self._markdown_file(directory)
            with patch.object(
                file_processor,
                "configured_text_model",
                return_value="resolved-supported-model",
            ), patch.object(file_processor, "_gemini_client", return_value=client):
                result = file_processor.file_processor(
                    {"action": "explain", "file_path": str(path), "save": False}
                )

        self.assertEqual(result, "Real provider explanation.")
        kwargs = generate_content.call_args.kwargs
        self.assertEqual(kwargs["model"], "resolved-supported-model")
        self.assertTrue(kwargs["config"].automatic_function_calling.disable)
        self.assertIn("Explain this document", kwargs["contents"][0])

    def test_generate_content_keeps_client_alive_during_request(self):
        class Models:
            def __init__(self, owner):
                self._owner = weakref.ref(owner)

            def generate_content(self, **_kwargs):
                if self._owner() is None:
                    raise RuntimeError("client closed")
                return SimpleNamespace(text="Client stayed alive.")

        class Client:
            @property
            def models(self):
                return Models(self)

        with patch.object(file_processor, "_gemini_client", return_value=Client()):
            result = file_processor._generate_content("Explain this.", model="test-model")

        self.assertEqual(result, "Client stayed alive.")

    def test_provider_failure_is_explicit_and_does_not_fabricate(self):
        generate_content = MagicMock(side_effect=RuntimeError("provider offline"))
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self._markdown_file(directory)
            with patch.object(file_processor, "_gemini_client", return_value=client):
                result = file_processor.file_processor(
                    {"action": "explain", "file_path": str(path), "save": False}
                )

        self.assertEqual(result, "AI processing failed: provider offline")
        self.assertNotIn("Verified visible content", result)


if __name__ == "__main__":
    unittest.main()
