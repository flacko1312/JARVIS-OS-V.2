"""Tests for actions.broadcast_control — TTS announcement broadcasting."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from actions.broadcast_control import (
    _action_announce,
    _action_status,
    _try_lilith_broadcast,
    broadcast_control,
)


class TestActionAnnounce:
    def test_empty_message(self):
        result = _action_announce("", player=None)
        assert "especifica" in result.lower()

    def test_speak_via_player(self):
        player = MagicMock()
        player.speak.return_value = None
        result = _action_announce("Hola hogar", player=player)
        player.speak.assert_called_once_with("Hola hogar")
        assert "Hola hogar" in result

    def test_player_exception_returns_error(self):
        player = MagicMock()
        player.speak.side_effect = RuntimeError("TTS down")
        result = _action_announce("Test", player=player)
        assert "error" in result.lower()

    def test_no_player_uses_tts_engine(self):
        tts_speak = MagicMock()
        with patch.dict("sys.modules", {"actions.tts_engine": MagicMock(speak=tts_speak)}):
            result = _action_announce("Mensaje test", player=None)
        assert isinstance(result, str)

    def test_no_player_no_tts_fallback_espeak(self):
        with patch.dict("sys.modules", {"actions.tts_engine": None}), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _action_announce("Espeak test", player=None)
        assert isinstance(result, str)


class TestTryLilithBroadcast:
    def test_no_env_vars_returns_empty(self, monkeypatch):
        monkeypatch.delenv("LILITH_API_URL", raising=False)
        monkeypatch.delenv("LILITH_API_KEY", raising=False)
        result = _try_lilith_broadcast("test")
        assert result == ""

    def test_success(self, monkeypatch):
        monkeypatch.setenv("LILITH_API_URL", "http://localhost:8080")
        monkeypatch.setenv("LILITH_API_KEY", "testkey")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _try_lilith_broadcast("test")
        assert "LILITH" in result

    def test_connection_error_returns_empty(self, monkeypatch):
        monkeypatch.setenv("LILITH_API_URL", "http://localhost:9999")
        monkeypatch.setenv("LILITH_API_KEY", "key")
        with patch("urllib.request.urlopen", side_effect=Exception("refused")):
            result = _try_lilith_broadcast("test")
        assert result == ""


class TestActionStatus:
    def test_with_player(self):
        player = MagicMock()
        result = _action_status(player)
        assert "tts local" in result.lower()
        assert "disponible" in result.lower()

    def test_without_player_no_lilith(self, monkeypatch):
        monkeypatch.delenv("LILITH_API_URL", raising=False)
        result = _action_status(None)
        assert isinstance(result, str)
        assert "lilith" in result.lower()


class TestBroadcastControlEntryPoint:
    def test_announce_action(self):
        player = MagicMock()
        result = broadcast_control({"action": "announce", "message": "Atención"}, player=player)
        player.speak.assert_called_once_with("Atención")
        assert "Atención" in result

    def test_say_alias(self):
        player = MagicMock()
        result = broadcast_control({"action": "say", "message": "Hola"}, player=player)
        player.speak.assert_called_once()

    def test_broadcast_action_local(self):
        player = MagicMock()
        with patch("actions.broadcast_control._try_lilith_broadcast", return_value=""):
            result = broadcast_control({"action": "broadcast", "text": "Todo el hogar"}, player=player)
        player.speak.assert_called_once_with("Todo el hogar")
        assert "Todo el hogar" in result

    def test_broadcast_with_lilith(self):
        player = MagicMock()
        with patch("actions.broadcast_control._try_lilith_broadcast", return_value=" Broadcast enviado a LILITH."):
            result = broadcast_control({"action": "broadcast", "message": "Aviso"}, player=player)
        assert "LILITH" in result

    def test_status_action(self):
        player = MagicMock()
        result = broadcast_control({"action": "status"}, player=player)
        assert isinstance(result, str)

    def test_unknown_action(self):
        result = broadcast_control({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_none_params(self):
        result = broadcast_control(None)
        assert isinstance(result, str)

    def test_default_action_announce(self):
        player = MagicMock()
        result = broadcast_control({"message": "Defecto"}, player=player)
        player.speak.assert_called_once_with("Defecto")

    def test_text_param_alias(self):
        player = MagicMock()
        result = broadcast_control({"action": "announce", "text": "Via text"}, player=player)
        player.speak.assert_called_once_with("Via text")

    def test_anuncio_hogar_alias(self):
        player = MagicMock()
        with patch("actions.broadcast_control._try_lilith_broadcast", return_value=""):
            result = broadcast_control({"action": "anuncio_hogar", "message": "Cena lista"}, player=player)
        player.speak.assert_called_once_with("Cena lista")
