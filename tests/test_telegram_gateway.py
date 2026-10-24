from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telegram_gateway.auth import ChatAuthorizer
from telegram_gateway.config import ConfigurationError, Settings
from telegram_gateway.formatter import TELEGRAM_TEXT_LIMIT, split_message, telegram_html_chunks
from telegram_gateway.jarvis_client import JarvisTextClient
from telegram_gateway.jarvis_client import JarvisUnavailable
from telegram_gateway.main import Gateway, GatewayStopped
from telegram_gateway.sessions import OffsetStore, SessionStore
from telegram_gateway.telegram_client import TelegramClient


class FakeTelegram:
    def __init__(self):
        self.messages = []
        self.actions = []

    def send_text(self, chat_id, text, parse_mode=None):
        self.messages.append((chat_id, text, parse_mode))

    def send_chat_action(self, chat_id, action="typing"):
        self.actions.append((chat_id, action))


class FakeJarvis:
    def __init__(self):
        self.calls = []

    def ask(self, text, session_id):
        self.calls.append((text, session_id))
        return "respuesta"


class TelegramGatewayTests(unittest.TestCase):
    def settings(self, state_dir: Path) -> Settings:
        return Settings(
            bot_token="123:fake-token",
            allowed_chat_ids=frozenset({42}),
            poll_timeout=30,
            request_timeout=10,
            socket_path=state_dir / "jarvis.sock",
            state_dir=state_dir,
            log_level="INFO",
        )

    def test_authorizer_fails_closed(self):
        auth = ChatAuthorizer(frozenset({42}))
        self.assertTrue(auth.is_allowed(42))
        self.assertFalse(auth.is_allowed(43))
        self.assertFalse(auth.is_allowed(None))
        self.assertFalse(auth.is_allowed(True))

    def test_signal_stop_interrupts_blocking_poll_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway = Gateway(self.settings(Path(directory)), telegram=FakeTelegram())
            with self.assertRaises(GatewayStopped):
                gateway.stop(15, None)
            self.assertFalse(gateway._running)

    def test_unauthorized_update_never_reaches_jarvis(self):
        with tempfile.TemporaryDirectory() as directory:
            telegram = FakeTelegram()
            gateway = Gateway(self.settings(Path(directory)), telegram=telegram)
            jarvis = FakeJarvis()
            gateway.jarvis = jarvis
            gateway.handle_update({"message": {"chat": {"id": 99}, "text": "Hola"}})
            self.assertEqual(jarvis.calls, [])
            self.assertEqual(telegram.messages, [])

    def test_authorized_multiturn_reuses_persistent_session(self):
        with tempfile.TemporaryDirectory() as directory:
            telegram = FakeTelegram()
            gateway = Gateway(self.settings(Path(directory)), telegram=telegram)
            jarvis = FakeJarvis()
            gateway.jarvis = jarvis
            gateway.handle_update({"message": {"chat": {"id": 42}, "text": "lobos"}})
            gateway.handle_update({"message": {"chat": {"id": 42}, "text": "¿y cuál es mayor?"}})
            self.assertEqual(len(jarvis.calls), 2)
            self.assertEqual(jarvis.calls[0][1], jarvis.calls[1][1])
            self.assertEqual(len(telegram.messages), 2)
            self.assertEqual(telegram.messages[0][2], "HTML")

    def test_non_text_is_rejected_without_jarvis(self):
        with tempfile.TemporaryDirectory() as directory:
            telegram = FakeTelegram()
            gateway = Gateway(self.settings(Path(directory)), telegram=telegram)
            jarvis = FakeJarvis()
            gateway.jarvis = jarvis
            gateway.handle_update({"message": {"chat": {"id": 42}, "voice": {}}})
            self.assertFalse(jarvis.calls)
            self.assertIn("únicamente mensajes de texto", telegram.messages[0][1])

    def test_jarvis_failure_returns_readable_error_and_gateway_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            telegram = FakeTelegram()
            gateway = Gateway(self.settings(Path(directory)), telegram=telegram)
            gateway.jarvis = SimpleNamespace(
                ask=lambda *_args: (_ for _ in ()).throw(JarvisUnavailable("temporalmente caído"))
            )
            gateway.handle_update({"message": {"chat": {"id": 42}, "text": "Hola"}})
            self.assertIn("temporalmente no disponible", telegram.messages[0][1])

    def test_message_split_respects_telegram_limit(self):
        original = ("párrafo con https://example.com/fuente\n" * 400).strip()
        chunks = split_message(original)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= TELEGRAM_TEXT_LIMIT for chunk in chunks))
        self.assertEqual(" ".join(chunks).split(), original.split())

    def test_html_rendering_is_safe_and_bounded(self):
        original = "# Estado\n- **Docker**: `activo`\n<script>alert(1)</script>\n" + "<&>" * 2500
        chunks = telegram_html_chunks(original)
        self.assertTrue(all(0 < len(chunk) <= TELEGRAM_TEXT_LIMIT for chunk in chunks))
        rendered = "\n".join(chunks)
        self.assertIn("<b>Estado</b>", rendered)
        self.assertIn("<b>Docker</b>", rendered)
        self.assertIn("<code>activo</code>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_status_command_routes_to_natural_language_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            telegram = FakeTelegram()
            gateway = Gateway(self.settings(Path(directory)), telegram=telegram)
            jarvis = FakeJarvis()
            gateway.jarvis = jarvis
            gateway.handle_update({"message": {"chat": {"id": 42}, "text": "/estado"}})
            self.assertIn("diagnóstico general", jarvis.calls[0][0])

    def test_start_and_help_are_local_and_do_not_call_jarvis(self):
        with tempfile.TemporaryDirectory() as directory:
            telegram = FakeTelegram()
            gateway = Gateway(self.settings(Path(directory)), telegram=telegram)
            jarvis = FakeJarvis()
            gateway.jarvis = jarvis
            gateway.handle_update({"message": {"chat": {"id": 42}, "text": "/start"}})
            gateway.handle_update({"message": {"chat": {"id": 42}, "text": "/help"}})
            self.assertFalse(jarvis.calls)
            self.assertIn("Lilith / JARVIS", telegram.messages[0][1])
            self.assertIn("Comandos mínimos", telegram.messages[1][1])

    def test_session_and_offset_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = SessionStore(root / "sessions.json")
            first = sessions.for_chat(42)
            self.assertEqual(first, SessionStore(root / "sessions.json").for_chat(42))
            offsets = OffsetStore(root / "offset")
            offsets.save(123)
            self.assertEqual(OffsetStore(root / "offset").load(), 123)
            self.assertEqual((root / "sessions.json").stat().st_mode & 0o777, 0o600)

    def test_configuration_requires_token_and_numeric_allowlist(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                Settings.from_env()
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_ALLOWED_CHAT_IDS": "42,43",
        }, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.allowed_chat_ids, frozenset({42, 43}))


class TelegramProfileTests(unittest.TestCase):
    def test_profile_configuration_is_minimal_and_canonical(self):
        client = TelegramClient("123:fake")
        calls = []

        def fake_call(method, values, timeout):
            calls.append((method, values, timeout))
            return {"ok": True, "result": True}

        client._call = fake_call
        client.configure_profile()
        self.assertEqual(
            [call[0] for call in calls],
            ["setMyName", "setMyDescription", "setMyShortDescription", "setMyCommands"],
        )
        commands = calls[-1][1]["commands"]
        self.assertIn('"start"', commands)
        self.assertIn('"help"', commands)
        self.assertIn('"estado"', commands)
        self.assertNotIn("token", commands.lower())


class TextGatewayServerTests(unittest.TestCase):
    def test_unix_socket_forwards_to_existing_jarvis(self):
        import text_gateway_server

        loop = asyncio.new_event_loop()

        class ExistingJarvis:
            _loop = loop

            async def ask_text(self, text, channel, timeout):
                return f"{channel}:{text}"

        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.sock"
            result = text_gateway_server.start(ExistingJarvis(), path)
            self.assertTrue(result["started"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            try:
                answer = JarvisTextClient(path, timeout=2).ask("hola", "telegram:42:test")
                self.assertEqual(answer, "telegram:hola")
            finally:
                result["server"].shutdown()
                result["server"].server_close()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


class ReadOnlyInfrastructureTests(unittest.TestCase):
    def test_new_tools_are_permissioned_read_only(self):
        from core.headless_permissions import PermissionLevel, check_permission

        for name in ("disk_status", "docker_status", "infrastructure_status", "service_logs"):
            self.assertEqual(check_permission(name).level, PermissionLevel.READ_ONLY)

    def test_real_disk_and_docker_probes_have_bounded_structures(self):
        from core.headless_tools import disk_status, docker_status, infrastructure_status

        disks = disk_status()
        self.assertIsInstance(disks, list)
        self.assertTrue(disks)
        docker = docker_status()
        self.assertIn("available", docker)
        self.assertIsInstance(infrastructure_status("postgresql"), dict)
        self.assertIn("error", infrastructure_status("not-real"))

    def test_service_logs_reject_unknown_component(self):
        from core.headless_tools import service_logs

        self.assertIn("not in the allowed", service_logs("../../etc/passwd"))


class GroundingSourceTests(unittest.TestCase):
    def test_extracts_only_real_grounding_urls(self):
        from actions.web_search import _grounding_sources

        candidate = SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[
            SimpleNamespace(web=SimpleNamespace(title="Docker Docs", uri="https://docs.docker.com/")),
            SimpleNamespace(web=SimpleNamespace(title="Duplicate", uri="https://docs.docker.com/")),
            SimpleNamespace(web=SimpleNamespace(title="Bad", uri="javascript:alert(1)")),
        ]))
        self.assertEqual(
            _grounding_sources(candidate),
            [{"title": "Docker Docs", "url": "https://docs.docker.com/"}],
        )

    def test_telegram_response_appends_verified_tool_urls(self):
        from main import JarvisLive

        jarvis = object.__new__(JarvisLive)
        jarvis._pending_web_search_result = (
            "1. Docker Docs\n   Official release notes\n   https://docs.docker.com/engine/release-notes/29/"
        )
        rendered = jarvis._append_verified_web_sources("Docker 29 es la versión actual.")
        self.assertIn("Fuentes:", rendered)
        self.assertIn("https://docs.docker.com/engine/release-notes/29/", rendered)
        self.assertTrue(JarvisLive._needs_verified_web("Busca la última versión de Docker"))
        self.assertFalse(JarvisLive._needs_verified_web("¿Qué es una dirección IP?"))
        self.assertFalse(JarvisLive._needs_verified_web("Mira los últimos errores de JARVIS"))

    def test_local_log_query_uses_bounded_read_only_tool(self):
        from main import JarvisLive

        with patch("core.headless_tools.service_logs", return_value="línea de error") as logs:
            context = JarvisLive._telegram_local_read_context("Mira los últimos errores de JARVIS")
        logs.assert_called_once_with("jarvis", lines=50)
        self.assertIn("Origen de logs: jarvis", context)


if __name__ == "__main__":
    unittest.main()
