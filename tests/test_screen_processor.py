import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import requests
from google.genai import errors as genai_errors

from actions import screen_processor
from core import vision_model


class VisionModelSelectionTests(unittest.TestCase):
    def test_default_vision_model_is_current(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("GEMINI_VISION_MODEL", None)
            model = vision_model.configured_vision_model(
                Path(directory) / "missing.json"
            )

        self.assertEqual(model, "gemini-3.8-flash")
        self.assertNotEqual(model, "gemini-2.5-flash")

    def test_environment_override_wins_over_configured_vision_model(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "api_keys.json"
            config.write_text(
                json.dumps({"vision_model": "configured-vision-model"}),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"GEMINI_VISION_MODEL": "environment-vision-model"},
            ):
                selected = vision_model.configured_vision_model(config)

        self.assertEqual(selected, "environment-vision-model")

    def test_configured_vision_model_wins_over_default(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("GEMINI_VISION_MODEL", None)
            config = Path(directory) / "api_keys.json"
            config.write_text(
                json.dumps({"vision_model": "configured-vision-model"}),
                encoding="utf-8",
            )
            selected = vision_model.configured_vision_model(config)

        self.assertEqual(selected, "configured-vision-model")

    def test_fallback_model_is_configurable(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "api_keys.json"
            config.write_text(
                json.dumps({"vision_fallback_model": "configured-fallback"}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_VISION_FALLBACK_MODEL", None)
                selected = vision_model.configured_vision_fallback_model(config)

        self.assertEqual(selected, "configured-fallback")

    def test_local_vision_defaults_are_enabled_and_loopback_only(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=False
        ):
            for name in (
                "OLLAMA_VISION_ENABLED",
                "OLLAMA_VISION_URL",
                "OLLAMA_VISION_MODEL",
            ):
                os.environ.pop(name, None)
            selected = vision_model.configured_ollama_vision(
                Path(directory) / "missing.json"
            )

        self.assertTrue(selected.enabled)
        self.assertEqual(selected.url, "http://127.0.0.1:11434")
        self.assertEqual(selected.model, "qwen3-vl:4b-instruct")

    def test_local_vision_environment_override_wins(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "OLLAMA_VISION_ENABLED": "1",
                "OLLAMA_VISION_URL": "http://localhost:11435/",
                "OLLAMA_VISION_MODEL": "configured-local-model",
            },
        ):
            selected = vision_model.configured_ollama_vision(
                Path(directory) / "missing.json"
            )

        self.assertEqual(selected.url, "http://localhost:11435")
        self.assertEqual(selected.model, "configured-local-model")

    def test_local_vision_rejects_remote_or_credentialed_url(self):
        for url in (
            "http://192.168.1.10:11434",
            "http://user:secret@127.0.0.1:11434",
        ):
            with self.subTest(url=url), patch.dict(
                os.environ, {"OLLAMA_VISION_URL": url}
            ):
                with self.assertRaisesRegex(ValueError, "loopback"):
                    vision_model.configured_ollama_vision(Path("missing.json"))

    def test_direct_analysis_uses_resolved_model_and_disables_afc(self):
        generate_content = MagicMock(
            return_value=SimpleNamespace(text="Visible settings window.")
        )
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )

        with patch.object(screen_processor, "_get_api_key", return_value="test-key"), \
             patch.object(screen_processor.genai, "Client", return_value=client) as factory, \
             patch.object(
                 screen_processor,
                 "configured_vision_model",
                 return_value="intended-vision-model",
             ), \
             patch.object(
                 screen_processor,
                 "configured_vision_fallback_model",
                 return_value="fallback-vision-model",
             ) as fallback_resolver, \
             patch.object(screen_processor, "_local_vision_answer") as local:
            result = screen_processor._direct_vision_answer(
                b"image", "image/jpeg", "What is visible?"
            )

        self.assertEqual(result, "Visible settings window.")
        kwargs = generate_content.call_args.kwargs
        self.assertEqual(kwargs["model"], "intended-vision-model")
        self.assertTrue(kwargs["config"].automatic_function_calling.disable)
        retry = factory.call_args.kwargs["http_options"].retry_options
        self.assertEqual(retry.attempts, 2)
        self.assertEqual(retry.http_status_codes, [503])
        fallback_resolver.assert_called_once()
        local.assert_not_called()

    def _api_error(self, code: int):
        cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
        return cls(code, {"message": "test failure", "status": "TEST"})

    def _run_direct_with_side_effects(self, side_effects):
        generate_content = MagicMock(side_effect=side_effects)
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
        with patch.object(screen_processor, "_get_api_key", return_value="test-key"), \
             patch.object(screen_processor.genai, "Client", return_value=client), \
             patch.object(
                 screen_processor,
                 "configured_vision_model",
                 return_value="primary-model",
             ), \
             patch.object(
                 screen_processor,
                 "configured_vision_fallback_model",
                 return_value="fallback-model",
             ):
            result = screen_processor._direct_vision_answer(
                b"image", "image/jpeg", "What is visible?"
            )
        return result, generate_content

    def test_primary_success_does_not_use_fallback(self):
        with patch.object(screen_processor, "_local_vision_answer") as local:
            result, generate_content = self._run_direct_with_side_effects(
                [SimpleNamespace(text="Primary answer")]
            )

        self.assertEqual(result, "Primary answer")
        self.assertEqual(generate_content.call_count, 1)
        self.assertEqual(
            generate_content.call_args.kwargs["model"], "primary-model"
        )
        local.assert_not_called()

    def test_primary_503_uses_fallback_and_returns_real_answer(self):
        with patch.object(screen_processor, "_local_vision_answer") as local:
            result, generate_content = self._run_direct_with_side_effects(
                [self._api_error(503), SimpleNamespace(text="Fallback answer")]
            )

        self.assertEqual(result, "Fallback answer")
        self.assertEqual(
            [call.kwargs["model"] for call in generate_content.call_args_list],
            ["primary-model", "fallback-model"],
        )
        local.assert_not_called()

    def test_both_gemini_503_failures_use_same_bytes_for_local_answer(self):
        with patch.object(
            screen_processor,
            "_local_vision_answer",
            return_value="Real local answer",
        ) as local:
            result, generate_content = self._run_direct_with_side_effects(
                [self._api_error(503), self._api_error(503)]
            )

        self.assertEqual(result, "Real local answer")
        self.assertEqual(generate_content.call_count, 2)
        local.assert_called_once()
        self.assertEqual(local.call_args.args[0], b"image")
        self.assertEqual(local.call_args.args[1], "What is visible?")

    def test_gemini_network_failure_uses_local_answer_without_second_capture(self):
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
        with patch.object(
            screen_processor,
            "_local_vision_answer",
            return_value="Local network fallback",
        ) as local:
            result, generate_content = self._run_direct_with_side_effects(
                [httpx.ConnectError("offline", request=request)]
            )

        self.assertEqual(result, "Local network fallback")
        self.assertEqual(generate_content.call_count, 1)
        local.assert_called_once()

    def test_permanent_4xx_does_not_retry_or_fallback(self):
        generate_content = MagicMock(side_effect=self._api_error(404))
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
        with patch.object(screen_processor, "_get_api_key", return_value="test-key"), \
             patch.object(screen_processor.genai, "Client", return_value=client), \
             patch.object(
                 screen_processor,
                 "configured_vision_model",
                 return_value="invalid-primary",
             ), \
             patch.object(
                 screen_processor,
                 "configured_vision_fallback_model",
                 return_value="fallback-model",
             ), \
             patch.object(screen_processor, "_local_vision_answer") as local:
            with self.assertRaisesRegex(RuntimeError, "configuration failed.*404"):
                screen_processor._direct_vision_answer(
                    b"image", "image/jpeg", "What is visible?"
                )

        self.assertEqual(generate_content.call_count, 1)
        local.assert_not_called()

    def test_429_is_reported_without_fallback(self):
        generate_content = MagicMock(side_effect=self._api_error(429))
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
        with patch.object(screen_processor, "_get_api_key", return_value="test-key"), \
             patch.object(screen_processor.genai, "Client", return_value=client), \
             patch.object(
                 screen_processor,
                 "configured_vision_model",
                 return_value="primary-model",
             ), \
             patch.object(
                 screen_processor,
                 "configured_vision_fallback_model",
                 return_value="fallback-model",
             ), \
             patch.object(screen_processor, "_local_vision_answer") as local:
            with self.assertRaisesRegex(RuntimeError, "quota.*429"):
                screen_processor._direct_vision_answer(
                    b"image", "image/jpeg", "What is visible?"
                )

        self.assertEqual(generate_content.call_count, 1)
        local.assert_not_called()

    def test_ollama_request_uses_existing_image_and_original_question(self):
        image = b"already-captured-compressed-image"
        config = vision_model.OllamaVisionConfig(
            enabled=True,
            url="http://127.0.0.1:11434",
            model="qwen3-vl:4b-instruct",
        )
        response = MagicMock()
        response.json.return_value = {
            "message": {"content": "A real local visual answer."}
        }

        with patch.object(
            screen_processor.requests, "post", return_value=response
        ) as post:
            result = screen_processor._request_ollama_vision_answer(
                config, image, "What is visible?"
            )

        self.assertEqual(result, "A real local visual answer.")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "qwen3-vl:4b-instruct")
        self.assertEqual(base64.b64decode(payload["messages"][0]["images"][0]), image)
        self.assertIn("What is visible?", payload["messages"][0]["content"])
        self.assertIn("Do not invent", payload["messages"][0]["content"])
        self.assertEqual(post.call_args.kwargs["timeout"], (3.0, 90.0))

    def test_all_providers_fail_with_explicit_error_not_fake_answer(self):
        config = vision_model.OllamaVisionConfig(
            enabled=True,
            url="http://127.0.0.1:11434",
            model="qwen3-vl:4b-instruct",
        )
        with patch.object(
            screen_processor,
            "configured_ollama_vision",
            return_value=config,
        ), patch.object(
            screen_processor.requests,
            "post",
            side_effect=requests.ConnectionError("offline"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "local Ollama vision failed: ConnectionError"
            ):
                screen_processor._local_vision_answer(
                    b"image", "What is visible?", self._api_error(503)
                )

    def test_disabled_local_vision_fails_explicitly_without_request(self):
        config = vision_model.OllamaVisionConfig(
            enabled=False,
            url="http://127.0.0.1:11434",
            model="qwen3-vl:4b-instruct",
        )
        with patch.object(
            screen_processor,
            "configured_ollama_vision",
            return_value=config,
        ), patch.object(screen_processor.requests, "post") as post:
            with self.assertRaisesRegex(RuntimeError, "local Ollama vision is disabled"):
                screen_processor._local_vision_answer(
                    b"image", "What is visible?", self._api_error(503)
                )

        post.assert_not_called()


class ScreenProcessRegressionTests(unittest.TestCase):
    def _run_capture_path(self, angle: str):
        capture_name = "_capture_camera" if angle == "camera" else "_capture_screen"
        with patch.object(screen_processor, "_last_capture_time", 0.0), \
             patch.object(
                 screen_processor,
                 capture_name,
                 return_value=(f"{angle}-bytes".encode(), "image/jpeg"),
             ) as capture, \
             patch.object(
                 screen_processor,
                 "_direct_vision_answer",
                 return_value=f"{angle} answer",
             ) as analyze:
            result = screen_processor.screen_process(
                {"angle": angle, "text": "Analyze this."}
            )

        capture.assert_called_once_with()
        analyze.assert_called_once_with(
            f"{angle}-bytes".encode(), "image/jpeg", "Analyze this."
        )
        self.assertEqual(result, f"{angle} answer")

    def test_screen_and_camera_use_the_same_intended_analysis_path(self):
        for angle in ("screen", "camera"):
            with self.subTest(angle=angle):
                self._run_capture_path(angle)

    def test_capture_failure_remains_explicit(self):
        speak = MagicMock(return_value=True)
        with patch.object(screen_processor, "_last_capture_time", 0.0), \
             patch.object(
                 screen_processor,
                 "_capture_screen",
                 side_effect=RuntimeError("permission denied"),
             ), \
             patch.object(screen_processor, "_direct_vision_answer") as analyze:
            result = screen_processor.screen_process(
                {"angle": "screen", "text": "Analyze this."}, speak=speak
            )

        self.assertEqual(result, "Screen capture failed: permission denied")
        speak.assert_called_once_with(result)
        analyze.assert_not_called()

    def test_analysis_failure_is_explicit_and_never_fakes_an_answer(self):
        speak = MagicMock(return_value=True)
        with patch.object(screen_processor, "_last_capture_time", 0.0), \
             patch.object(
                 screen_processor,
                 "_capture_screen",
                 return_value=(b"image", "image/jpeg"),
             ), \
             patch.object(
                 screen_processor,
                 "_direct_vision_answer",
                 side_effect=RuntimeError("model unavailable"),
             ):
            result = screen_processor.screen_process(
                {"angle": "screen", "text": "Analyze this."}, speak=speak
            )

        self.assertEqual(result, "Screen analysis failed: model unavailable")
        self.assertNotIn("visible", result.lower())
        speak.assert_called_once_with(result)


if __name__ == "__main__":
    unittest.main()
