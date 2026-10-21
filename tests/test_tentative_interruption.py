import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import main as main_module
from core.audio_barge_in import BargeInDecision
from main import (
    JarvisLive,
    _TENTATIVE_LOCAL_WINDOW_S,
    _TENTATIVE_MAX_TIMEOUT_S,
    _classify_void_turn,
)


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


class TrackingGate:
    accepted = False

    def __init__(self, decision):
        self.decision = decision
        self.playback_active_values = []

    def process(self, data, playback_active=False):
        self.playback_active_values.append(playback_active)
        return self.decision


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
    jarvis._tentative_started_at = 0.0
    jarvis._tentative_local_speech_frames = 0
    jarvis._tentative_local_speech_continued = False
    jarvis._tentative_added_audio_bytes = 0
    jarvis._tentative_local_timer = None
    jarvis._tentative_max_timer = None
    jarvis._false_barge_in_turn_id = None
    jarvis._false_interruption_recovery_task = None
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


def _decision(*, candidate=False, accepted=False, rejected_reason=None, speech_ms=0):
    return BargeInDecision(
        candidate=candidate,
        accepted=accepted,
        rejected_reason=rejected_reason,
        speech_duration_ms=speech_ms,
        rms=0.03,
        noise_floor=0.004,
        echo_similarity=0.1,
    )


def test_false_barge_in_rolls_back_without_turn_complete():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_started_at = main_module.time.monotonic()
    jarvis._tentative_audio_buffer = [b"old"]

    jarvis._finish_tentative_local_window()

    assert jarvis._tentative_barge_in_active is False
    assert jarvis.audio_in_queue.get_nowait() == b"old"
    assert jarvis._false_barge_in_turn_id == "turn-1"


def test_false_barge_in_rolls_back_inside_short_window():
    async def scenario():
        jarvis = make_jarvis()
        jarvis._begin_tentative_interruption()
        await asyncio.sleep(_TENTATIVE_LOCAL_WINDOW_S + 0.12)
        assert jarvis._tentative_barge_in_active is False
        assert jarvis._tentative_age_ms() == 0

    assert 0.3 <= _TENTATIVE_LOCAL_WINDOW_S <= 0.8
    asyncio.run(scenario())


def test_sustained_local_speech_prevents_window_rollback():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_started_at = main_module.time.monotonic()
    jarvis._observe_tentative_barge_in(
        _decision(accepted=True, speech_ms=192)
    )

    jarvis._finish_tentative_local_window()

    assert jarvis._tentative_barge_in_active is True
    assert jarvis._tentative_local_speech_continued is True
    assert jarvis._tentative_local_speech_frames == 1


def test_tentative_frames_reuse_existing_gate_for_local_confirmation():
    jarvis = make_jarvis()
    gate = TrackingGate(_decision(candidate=True, speech_ms=64))
    jarvis._barge_in_gate = gate
    jarvis._is_speaking = False
    jarvis._tentative_barge_in_active = True

    jarvis._process_microphone_audio(b"continued voice", ImmediateLoop())

    assert gate.playback_active_values == [True]
    assert jarvis._tentative_local_speech_frames == 1


def test_sustained_local_speech_then_semantic_input_commits():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_started_at = main_module.time.monotonic()
    jarvis._tentative_audio_buffer = [b"old"]
    jarvis._observe_tentative_barge_in(
        _decision(accepted=True, speech_ms=192)
    )

    discarded = jarvis._commit_tentative_interruption("turn-1")

    assert discarded == 1
    assert jarvis._turn_interrupted is True
    assert jarvis._local_barge_in_active is True


def test_probable_speech_without_transcript_rolls_back_at_max_timeout():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_started_at = main_module.time.monotonic()
    jarvis._tentative_audio_buffer = [b"old"]
    jarvis._observe_tentative_barge_in(
        _decision(accepted=True, speech_ms=192)
    )

    jarvis._finish_tentative_max_timeout()

    assert _TENTATIVE_MAX_TIMEOUT_S <= 3.0
    assert jarvis._tentative_barge_in_active is False
    assert jarvis.audio_in_queue.get_nowait() == b"old"


def test_turn_complete_remains_rollback_fallback():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_audio_buffer = [b"old"]

    restored, recovery = jarvis._rollback_tentative_interruption("turn-1")

    assert restored == 1
    assert recovery is False


def test_provider_interrupted_before_semantic_input_has_no_race():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_provider_interrupted = True
    jarvis._tentative_audio_buffer = [b"old"]

    jarvis._commit_tentative_interruption("turn-1")

    assert jarvis._turn_interrupted is True
    assert jarvis._suppress_interrupted_output is False


def test_semantic_input_before_provider_interruption_has_no_race():
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_audio_buffer = [b"old"]

    jarvis._commit_tentative_interruption("turn-1")
    provider_arrived_later = not jarvis._tentative_barge_in_active

    assert provider_arrived_later is True
    assert jarvis._turn_interrupted is True
    assert jarvis._tentative_audio_buffer == []


def test_tentative_buffer_growth_cap_rolls_back_without_loss(monkeypatch):
    jarvis = make_jarvis()
    jarvis._tentative_barge_in_active = True
    jarvis._tentative_started_at = main_module.time.monotonic()
    jarvis._tentative_audio_buffer = [b"old"]
    monkeypatch.setattr(main_module, "_TENTATIVE_BUFFER_GROWTH_MAX_BYTES", 4)

    jarvis._buffer_tentative_audio(b"next", "turn-1")

    assert jarvis._tentative_barge_in_active is False
    assert [jarvis.audio_in_queue.get_nowait() for _ in range(2)] == [
        b"old", b"next"
    ]


def test_false_barge_in_is_classified_as_interrupted_not_clarification():
    assert _classify_void_turn(
        input_text="<noise>",
        output_text="",
        audio_chunks=10,
        tool_call_seen=False,
        replay_rejected=False,
        interrupted=True,
    ) == "interrupted"


def test_false_barge_turn_close_preserves_quarantined_audio_path():
    source = open(
        JarvisLive._receive_audio.__code__.co_filename, encoding="utf-8"
    ).read()
    assert "if _false_barge_in_turn:" in source
    assert "for _qchunk in _audio_quarantine:" in source
    assert "self.audio_in_queue.put_nowait(_qchunk)" in source


def test_late_semantic_after_false_rollback_cannot_enable_side_effects():
    source = open(
        JarvisLive._receive_audio.__code__.co_filename, encoding="utf-8"
    ).read()
    marker_guard = (
        'getattr(\n'
        '                                        self, "_false_barge_in_turn_id", None\n'
        '                                    ) != live_turn_id'
    )
    assert marker_guard in source


def test_normal_path_has_no_tentative_timer_delay():
    jarvis = make_jarvis()
    jarvis._is_speaking = False
    jarvis._barge_in_gate = AcceptedGate()
    jarvis._barge_in_gate.accepted = True

    jarvis._process_microphone_audio(b"normal voice", ImmediateLoop())

    assert jarvis._tentative_barge_in_active is False
    assert jarvis._tentative_local_timer is None
    jarvis._enqueue_microphone_audio.assert_called_once_with(b"voice")
