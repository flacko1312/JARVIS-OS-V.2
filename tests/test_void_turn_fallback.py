import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main
from main import JarvisLive, _classify_void_turn


def classify(**overrides):
    values = {
        "input_text": "<noise>",
        "output_text": "",
        "audio_chunks": 0,
        "tool_call_seen": False,
        "replay_rejected": False,
        "interrupted": False,
    }
    values.update(overrides)
    return _classify_void_turn(**values)


def test_real_noise_without_semantic_output_is_discarded():
    assert classify(audio_chunks=0) == "true_noise"


def test_punctuation_input_never_uses_noise_fallback():
    assert classify(
        input_text=".",
        output_text="Respuesta a un punto.",
        audio_chunks=20,
    ) == "true_noise"


def test_noise_with_audio_does_not_require_output_transcription():
    assert classify(output_text="", audio_chunks=20) == "uncertain_speech"


def test_false_noise_with_semantic_output_uses_safe_fallback():
    assert classify(
        output_text="París es la capital de Francia.",
        audio_chunks=33,
    ) == "uncertain_speech"


def test_normal_semantic_input_keeps_normal_path():
    assert classify(
        input_text="¿Cuál es la capital de Francia?",
        output_text="París.",
        audio_chunks=1,
    ) is None


def test_noise_with_tool_call_never_qualifies_for_fallback():
    assert classify(
        output_text="He encendido la luz.",
        audio_chunks=20,
        tool_call_seen=True,
    ) == "unsafe_tool"


def test_noise_replay_is_discarded():
    assert classify(
        output_text="Respuesta repetida.",
        audio_chunks=20,
        replay_rejected=True,
    ) == "replay"


def test_noise_interrupted_turn_is_discarded():
    assert classify(
        output_text="Respuesta parcial.",
        audio_chunks=20,
        interrupted=True,
    ) == "interrupted"


def test_noise_is_never_semantic_user_memory():
    assert not main._is_semantic_transcript(main._strip_noise_tags("<noise>"))


def test_local_clarification_queues_audio_without_memory_write(tmp_path):
    pcm_path = tmp_path / "clarification.pcm"
    pcm_path.write_bytes(b"\x01\x00" * 128)
    jarvis = object.__new__(JarvisLive)
    jarvis.ui = SimpleNamespace(muted=False)
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis._remember_conversation_text = MagicMock()

    with patch.object(main, "_VOID_TURN_CLARIFICATION_PCM", pcm_path):
        assert jarvis._queue_void_turn_clarification() is True

    assert jarvis.audio_in_queue.qsize() == 1
    assert jarvis.audio_in_queue.get_nowait() == pcm_path.read_bytes()
    jarvis._remember_conversation_text.assert_not_called()


def test_missing_local_clarification_fails_closed(tmp_path):
    jarvis = object.__new__(JarvisLive)
    jarvis.ui = SimpleNamespace(muted=False)
    jarvis.audio_in_queue = asyncio.Queue()
    with patch.object(
        main,
        "_VOID_TURN_CLARIFICATION_PCM",
        tmp_path / "missing.pcm",
    ):
        assert jarvis._queue_void_turn_clarification() is False
    assert jarvis.audio_in_queue.empty()
