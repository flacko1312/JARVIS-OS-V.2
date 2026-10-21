import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from main import JarvisLive, _classify_void_turn


class ImmediateLoop:
    def call_soon_threadsafe(self, callback, *args):
        callback(*args)


class AcceptedGate:
    accepted = False

    def process(self, data, playback_active=False):
        self.accepted = True
        return SimpleNamespace(
            accepted=True,
            candidate=False,
            rejected_reason=None,
            speech_duration_ms=200,
            rms=0.02,
            noise_floor=0.004,
            echo_similarity=0.1,
            forward_frames=[b"voice"],
        )


def make_jarvis():
    jarvis = object.__new__(JarvisLive)
    jarvis._speaking_lock = threading.Lock()
    jarvis._is_speaking = True
    jarvis._barge_in_gate = AcceptedGate()
    jarvis._barge_in_candidate_logged = False
    jarvis._barge_in_last_reject_log = 0.0
    jarvis._local_barge_in_active = False
    jarvis._tentative_barge_in_active = False
    jarvis._tentative_barge_in_requested = False
    jarvis._tentative_audio_buffer = []
    jarvis._tentative_provider_interrupted = False
    jarvis._suppress_interrupted_output = False
    jarvis._turn_interrupted = False
    jarvis._last_barge_in_accepted_t = 0.0
    jarvis._active_turn_id = "turn-1"
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis.out_queue = asyncio.Queue()
    jarvis.set_speaking = MagicMock(
        side_effect=lambda value: setattr(jarvis, "_is_speaking", value)
    )
    jarvis._enqueue_microphone_audio = MagicMock()
    jarvis._log_barge_in = MagicMock()
    jarvis._remember_conversation_text = MagicMock()
    jarvis._execute_tool_batch = AsyncMock()
    return jarvis


def test_false_local_barge_in_preserves_and_restores_audio():
    jarvis = make_jarvis()
    chunks = [b"a", b"b", b"c"]
    for chunk in chunks:
        jarvis.audio_in_queue.put_nowait(chunk)

    jarvis._process_microphone_audio(b"possible voice", ImmediateLoop())

    assert jarvis._tentative_barge_in_active is True
    assert jarvis._turn_interrupted is False
    assert jarvis._suppress_interrupted_output is False
    assert jarvis._tentative_audio_buffer == chunks
    assert jarvis.audio_in_queue.empty()

    restored, recovery = jarvis._rollback_tentative_interruption("turn-1")
    assert restored == len(chunks)
    assert recovery is False
    assert [jarvis.audio_in_queue.get_nowait() for _ in chunks] == chunks


def test_real_local_barge_in_commits_on_semantic_input():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_audio_buffer = [b"old-1", b"old-2"]
    discarded = jarvis._commit_tentative_interruption("turn-1")
    assert discarded == 2
    assert jarvis._tentative_audio_buffer == []
    assert jarvis._turn_interrupted is True
    assert jarvis._suppress_interrupted_output is True
    assert jarvis._local_barge_in_active is True


def test_real_barge_in_does_not_suppress_new_reply_if_provider_already_cut():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_provider_interrupted = True
    jarvis._tentative_audio_buffer = [b"old"]
    jarvis._commit_tentative_interruption("turn-1")
    assert jarvis._turn_interrupted is True
    assert jarvis._suppress_interrupted_output is False


def test_false_interruption_does_not_write_memory():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_audio_buffer = [b"old"]
    jarvis._rollback_tentative_interruption("turn-1")
    jarvis._remember_conversation_text.assert_not_called()


def test_false_interruption_does_not_execute_tools():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._rollback_tentative_interruption("turn-1")
    jarvis._execute_tool_batch.assert_not_awaited()


def test_false_interruption_does_not_create_user_transcript():
    jarvis = make_jarvis()
    jarvis._current_input_transcript = "pregunta original"
    jarvis._tentative_barge_in_active = True
    jarvis._rollback_tentative_interruption("turn-1")
    assert jarvis._current_input_transcript == "pregunta original"


def test_provider_cut_requests_internal_continuation():
    async def scenario():
        jarvis = make_jarvis()
        jarvis._wait_for_playback_drain = AsyncMock(return_value=True)
        jarvis._shutdown_requested = threading.Event()
        jarvis._conversation_requested = threading.Event()
        jarvis._conversation_requested.set()
        jarvis.session = SimpleNamespace(send_client_content=AsyncMock())
        jarvis._internal_continuation_active = False

        await jarvis._request_false_interruption_continuation("turn-1")

        assert jarvis._internal_continuation_active is True
        jarvis.session.send_client_content.assert_awaited_once()
        kwargs = jarvis.session.send_client_content.await_args.kwargs
        text = kwargs["turns"]["parts"][0]["text"]
        assert text.startswith("[INTERNAL FALSE INTERRUPTION RECOVERY]")
        assert "no llames herramientas" in text

    asyncio.run(scenario())


def test_internal_continuation_is_not_user_memory():
    async def scenario():
        jarvis = make_jarvis()
        jarvis._wait_for_playback_drain = AsyncMock(return_value=True)
        jarvis._shutdown_requested = threading.Event()
        jarvis._conversation_requested = threading.Event()
        jarvis._conversation_requested.set()
        jarvis.session = SimpleNamespace(send_client_content=AsyncMock())
        jarvis._internal_continuation_active = False
        await jarvis._request_false_interruption_continuation("turn-1")
        jarvis._remember_conversation_text.assert_not_called()

    asyncio.run(scenario())


def test_internal_continuation_does_not_execute_tools():
    async def scenario():
        jarvis = make_jarvis()
        jarvis._wait_for_playback_drain = AsyncMock(return_value=True)
        jarvis._shutdown_requested = threading.Event()
        jarvis._conversation_requested = threading.Event()
        jarvis._conversation_requested.set()
        jarvis.session = SimpleNamespace(send_client_content=AsyncMock())
        jarvis._internal_continuation_active = False
        await jarvis._request_false_interruption_continuation("turn-1")
        jarvis._execute_tool_batch.assert_not_awaited()

    asyncio.run(scenario())


def test_idle_noise_with_response_audio_uses_clarification():
    assert _classify_void_turn(
        input_text="<noise>",
        output_text="",
        audio_chunks=33,
        tool_call_seen=False,
        replay_rejected=False,
        interrupted=False,
    ) == "uncertain_speech"


def test_idle_noise_without_response_audio_is_true_noise():
    assert _classify_void_turn(
        input_text="<noise>",
        output_text="",
        audio_chunks=0,
        tool_call_seen=False,
        replay_rejected=False,
        interrupted=False,
    ) == "true_noise"


def test_idle_noise_with_tool_is_unsafe():
    assert _classify_void_turn(
        input_text="<noise>",
        output_text="respuesta",
        audio_chunks=33,
        tool_call_seen=True,
        replay_rejected=False,
        interrupted=False,
    ) == "unsafe_tool"


def test_normal_semantic_input_keeps_normal_path():
    assert _classify_void_turn(
        input_text="¿Cuál es la capital de Italia?",
        output_text="Roma.",
        audio_chunks=1,
        tool_call_seen=False,
        replay_rejected=False,
        interrupted=False,
    ) is None


def test_replay_fails_closed():
    assert _classify_void_turn(
        input_text="<noise>",
        output_text="respuesta repetida",
        audio_chunks=33,
        tool_call_seen=False,
        replay_rejected=True,
        interrupted=False,
    ) == "replay"


def test_normal_turn_audio_does_not_wait_for_turn_complete():
    source = (
        open(JarvisLive._receive_audio.__code__.co_filename, encoding="utf-8")
        .read()
    )
    immediate_enqueue = "if _input_validated:\n                                self.audio_in_queue.put_nowait(response_audio)"
    assert immediate_enqueue in source
