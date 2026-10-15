"""AUT-04 centralized Gemini configuration tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.gemini_config import GeminiModelAdapter, component_model


class ModelPrecedenceTests(unittest.TestCase):
    def test_full_precedence_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({
                "dev_agent_model": "component-config",
                "text_model": "global-config",
            }), encoding="utf-8")
            with patch.dict(os.environ, {
                "GEMINI_DEV_AGENT_MODEL": "component-env",
                "GEMINI_TEXT_MODEL": "global-env",
            }, clear=False):
                self.assertEqual(component_model("dev_agent", explicit="explicit", config_path=config), "explicit")
                self.assertEqual(component_model("dev_agent", config_path=config), "component-env")
                os.environ.pop("GEMINI_DEV_AGENT_MODEL")
                self.assertEqual(component_model("dev_agent", config_path=config), "component-config")
                config.write_text(json.dumps({"text_model": "global-config"}), encoding="utf-8")
                self.assertEqual(component_model("dev_agent", config_path=config), "global-env")
                os.environ.pop("GEMINI_TEXT_MODEL")
                self.assertEqual(component_model("dev_agent", config_path=config), "global-config")
                config.write_text("{}", encoding="utf-8")
                self.assertEqual(component_model("dev_agent", default="safe-default", config_path=config), "safe-default")


class AdapterTests(unittest.TestCase):
    def test_adapter_uses_new_sdk_models_surface(self):
        client = MagicMock()
        response = object()
        client.models.generate_content.return_value = response
        adapter = GeminiModelAdapter("test-model", client)
        result = adapter.generate_content("hello", generation_config={"temperature": 0})
        self.assertIs(result, response)
        client.models.generate_content.assert_called_once_with(
            model="test-model", contents="hello", config={"temperature": 0}
        )

    def test_named_consumers_no_longer_import_legacy_sdk(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "actions/dev_agent.py",
            "actions/code_helper.py",
            "actions/presentation_maker.py",
            "actions/deep_research.py",
        ):
            with self.subTest(relative=relative):
                text = (root / relative).read_text(encoding="utf-8")
                self.assertNotIn("import google.generativeai", text)


if __name__ == "__main__":
    unittest.main()
