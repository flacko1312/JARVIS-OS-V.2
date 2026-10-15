"""Focused deterministic coverage for PHY2-004 Live audio recovery/barge-in."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

import main


def async_test(function):
    def run():
        return asyncio.run(function())
    return run


class UI:
    def __init__(self):
        self.muted = False
        self.states: list[str] = []
        self.logs: list[str] = []
        self.on_text_command = None
        self.on_conversation_toggle = None

    def set_state(self, state):
        self.states.append(state)

    def write_log(self, text):
        self.logs.append(text)

    def clear_subtitle(self):
        return None

    def show_subtitle(self, _text):
        return None


def make_jarvis(*, external_audio: bool = True):
    return main.JarvisLive(UI(), cloud_safe=True, api_key="test", external_audio=external_audio)


def server_response(*, interrupted=False, audio=None, turn_complete=False, go_away=None):
    parts = [SimpleNamespace(inline_data=SimpleNamespace(data=audio))] if audio else []
    return SimpleNamespace(
        session_resumption_update=None,
        go_away=go_away,
        server_content=SimpleNamespace(
            interrupted=interrupted,
            model_turn=SimpleNamespace(parts=parts),
            output_transcription=None,
            input_transcription=None,
            turn_complete=turn_complete,
        ),
        tool_call=None,
    )


@async_test
async def test_receive_disconnect_during_active_playback_keeps_diagnostic_category():
    jarvis = make_jarvis()
    jarvis._conversation_requested.set()
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis.audio_in_queue.put_nowait(b"pending")
    jarvis._turn_done_event = asyncio.Event()
    jarvis.set_speaking(True)

    class Session:
        async def receive(self):
            raise ConnectionResetError("connection reset by peer")
            yield

    jarvis.session = Session()
    with pytest.raises(main.RecoverableLiveDisconnect) as caught:
        await jarvis._receive_audio()
    diagnostic = main._live_disconnect_diagnostics(caught.value)
    assert diagnostic["category"] == "network"
    assert diagnostic["exception"] == "RecoverableLiveDisconnect"


@async_test
async def test_provider_goaway_waits_for_turn_and_playback_before_reconnect():
    jarvis = make_jarvis()
    jarvis._conversation_requested.set()
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis._turn_done_event = asyncio.Event()
    jarvis._wait_for_playback_drain = AsyncMock(return_value=True)

    class Session:
        async def receive(self):
            yield server_response(
                audio=b"audio", go_away=SimpleNamespace(time_left="2s"), turn_complete=False,
            )
            yield server_response(turn_complete=True)

    jarvis.session = Session()
    with pytest.raises(main.RecoverableLiveDisconnect) as caught:
        await jarvis._receive_audio()
    assert caught.value.category == "provider_goaway"
    assert "playback_drained=True" in str(caught.value)
    jarvis._wait_for_playback_drain.assert_awaited_once()


@async_test
async def test_reconnect_uses_latest_resumption_handle():
    jarvis = make_jarvis()
    jarvis._conversation_requested.set()
    jarvis._wait_before_reconnect = AsyncMock()
    configs = []

    class First:
        async def receive(self):
            yield SimpleNamespace(
                session_resumption_update=SimpleNamespace(resumable=True, new_handle="latest"),
                go_away=SimpleNamespace(time_left="1s"), server_content=None, tool_call=None,
            )

        async def close(self): return None
        async def send_realtime_input(self, **_kwargs): return None

    class Second(First):
        async def receive(self):
            jarvis.stop_conversation()
            if False: yield None

    class Context:
        def __init__(self, session): self.session = session
        async def __aenter__(self): return self.session
        async def __aexit__(self, *_args): return False

    def connect(**kwargs):
        configs.append(kwargs["config"])
        return Context(First() if len(configs) == 1 else Second())

    client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
    with patch.object(main.genai, "Client", return_value=client), patch.object(
        main, "pick_live_model", return_value="models/test-live",
    ):
        await jarvis._run_live()
    assert len(configs) == 2
    assert configs[1].session_resumption.handle == "latest"


@async_test
async def test_resumption_unavailable_preserves_local_continuity():
    jarvis = make_jarvis()
    jarvis._logical_conversation_started = True
    jarvis._resume_from_local_continuity = True
    jarvis._remember_conversation_text("user", "contexto local intacto")
    config = jarvis._build_config(
        resumption_handle=None, local_continuity=jarvis._local_continuity_prompt(),
    )
    assert config.session_resumption.handle is None
    assert "contexto local intacto" in config.system_instruction


@async_test
async def test_single_live_runner_prevents_duplicate_reconnect_owner():
    jarvis = make_jarvis()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def loop():
        entered.set()
        await release.wait()

    jarvis._run_live_session_loop = loop
    owner = asyncio.create_task(jarvis._run_live())
    await entered.wait()
    await jarvis._run_live()
    assert jarvis._live_runner_lock.locked()
    release.set()
    await owner
    assert not jarvis._live_runner_lock.locked()


def test_reconnect_backoff_is_bounded():
    delays = [main._live_reconnect_delay(index) for index in range(1, 12)]
    assert delays[:6] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    assert max(delays) == 30.0
    assert main.MAX_LIVE_RECONNECT_ATTEMPTS == 5


def test_disconnect_cleanup_flushes_old_playback_and_input_queues():
    jarvis = make_jarvis()
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis.out_queue = asyncio.Queue()
    for value in (b"a", b"b", b"c"):
        jarvis.audio_in_queue.put_nowait(value)
    jarvis.out_queue.put_nowait({"data": b"mic"})
    assert jarvis._drain_queue(jarvis.audio_in_queue) == 3
    assert jarvis._drain_queue(jarvis.out_queue) == 1
    assert jarvis.audio_in_queue.empty() and jarvis.out_queue.empty()


@async_test
async def test_microphone_audio_is_forwarded_while_model_is_speaking():
    jarvis = make_jarvis(external_audio=False)
    jarvis._conversation_requested.set()
    jarvis.out_queue = asyncio.Queue()
    jarvis.set_speaking(True)
    samples = np.arange(main.CHUNK_SIZE) / main.SEND_SAMPLE_RATE
    voice = 0.08 * (
        np.sin(2 * np.pi * 180 * samples)
        + 0.5 * np.sin(2 * np.pi * 360 * samples)
        + 0.25 * np.sin(2 * np.pi * 720 * samples)
    )
    pcm = (voice * 32767).astype(np.int16).tobytes()

    class Input:
        def __init__(self, **kwargs): self.callback = kwargs["callback"]
        def __enter__(self):
            block = SimpleNamespace(tobytes=lambda: pcm)
            for _ in range(3):
                self.callback(block, main.CHUNK_SIZE, None, None)
            return self
        def __exit__(self, *_args): return False

    with patch.object(main.sd, "InputStream", Input):
        task = asyncio.create_task(jarvis._listen_audio())
        forwarded = await asyncio.wait_for(jarvis.out_queue.get(), 1)
        jarvis._conversation_requested.clear()
        await asyncio.wait_for(task, 1)
    assert forwarded["data"] == pcm


@async_test
async def test_provider_interruption_flushes_output_and_returns_to_listening():
    jarvis = make_jarvis()
    jarvis._conversation_requested.set()
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis.audio_in_queue.put_nowait(b"old-1")
    jarvis.audio_in_queue.put_nowait(b"old-2")
    jarvis._turn_done_event = asyncio.Event()
    jarvis.set_speaking(True)

    class Session:
        async def receive(self):
            yield server_response(interrupted=True)
            jarvis._conversation_requested.clear()

    jarvis.session = Session()
    await jarvis._receive_audio()
    assert jarvis.audio_in_queue.empty()
    assert jarvis._is_speaking is False
    assert jarvis.ui.states[-1] == "LISTENING"


def test_repeated_interruption_is_idempotent_and_creates_no_tasks():
    jarvis = make_jarvis()
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis.audio_in_queue.put_nowait(b"old")
    with patch.object(asyncio, "create_task") as create_task:
        assert jarvis._interrupt_live_playback("provider_interruption") == 1
        assert jarvis._interrupt_live_playback("provider_interruption") == 0
    create_task.assert_not_called()


def test_live_config_requests_native_start_of_activity_interruption():
    config = make_jarvis()._build_config(resumption_handle=None)
    assert (
        config.realtime_input_config.activity_handling
        == main.types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    )


@async_test
async def test_intentional_standby_is_not_a_recoverable_disconnect():
    jarvis = make_jarvis()
    jarvis._conversation_requested.set()
    jarvis.audio_in_queue = asyncio.Queue()
    jarvis._turn_done_event = asyncio.Event()

    class Session:
        async def receive(self):
            jarvis.stop_conversation()
            raise ConnectionResetError("close caused by requested standby")
            yield

    jarvis.session = Session()
    assert await jarvis._receive_audio() is None


def test_sanitized_disconnect_diagnostics_expose_close_type_not_payload():
    error = main.RecoverableLiveDisconnect(
        "provider closed normally\nsecret-audio-is-never-included",
        category="provider_close", close_code=1000,
    )
    diagnostic = main._live_disconnect_diagnostics(error)
    assert diagnostic["category"] == "provider_close"
    assert diagnostic["exception"] == "RecoverableLiveDisconnect"
    assert diagnostic["close_code"] == 1000
    assert diagnostic["detail"] == "provider closed normally secret=[REDACTED]"
    assert "never-included" not in diagnostic["detail"]

