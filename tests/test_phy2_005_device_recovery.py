"""Deterministic microphone hot-recovery coverage for PHY2-005."""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

import main


def async_test(function):
    def run():
        return asyncio.run(function())
    return run


class UI:
    def __init__(self):
        self.muted = True
        self.states = []
        self.logs = []
        self.on_text_command = None
        self.on_conversation_toggle = None

    def set_state(self, state):
        self.states.append(state)

    def write_log(self, text):
        self.logs.append(text)


def jarvis():
    instance = main.JarvisLive(UI(), cloud_safe=True, api_key="test", external_audio=False)
    instance._conversation_requested.set()
    instance.out_queue = asyncio.Queue()
    instance.audio_in_queue = asyncio.Queue()
    instance._turn_done_event = asyncio.Event()
    return instance


class InputStream:
    def __init__(self, owner, callback, *, active=False, stop_after_check=False):
        self.owner = owner
        self.callback = callback
        self._active = active
        self.stop_after_check = stop_after_check
        self.closed = False

    def __enter__(self):
        block = SimpleNamespace(
            tobytes=lambda: np.zeros(main.CHUNK_SIZE, dtype=np.int16).tobytes(),
        )
        for _ in range(3):
            self.callback(block, main.CHUNK_SIZE, None, None)
        return self

    def __exit__(self, *_args):
        self.closed = True
        return False

    @property
    def active(self):
        if self.stop_after_check:
            self.owner._conversation_requested.clear()
        return self._active


def recovering_factory(owner, modes, calls):
    modes = deque(modes)

    def factory(**kwargs):
        calls.append(kwargs)
        active, stop = modes.popleft()
        return InputStream(owner, kwargs["callback"], active=active, stop_after_check=stop)

    return factory


@async_test
async def test_microphone_loss_recreates_stream_and_recovers_without_f8(caplog=None):
    owner = jarvis()
    calls = []
    owner._audio_input_stream_factory = recovering_factory(
        owner, [(False, False), (True, True)], calls,
    )
    devices = iter(((3, "Primary mic"), (3, "Primary mic")))
    owner._audio_input_device_resolver = lambda: next(devices)
    owner._wait_for_audio_recovery = AsyncMock()
    owner.start_conversation = MagicMock(side_effect=AssertionError("F8 path must not run"))

    await owner._listen_audio()

    assert len(calls) == 2
    assert calls[0]["device"] == calls[1]["device"] == 3
    owner.start_conversation.assert_not_called()
    owner._wait_for_audio_recovery.assert_awaited_once_with(0.5)
    assert owner._audio_input_device_id == 3
    assert any("no disponible" in message for message in owner.ui.logs)
    assert any("recuperado automáticamente" in message for message in owner.ui.logs)


@async_test
async def test_stalled_callbacks_are_treated_as_device_loss():
    owner = jarvis()
    calls = []

    class SilentStream(InputStream):
        def __enter__(self):
            return self

    modes = deque(("silent", "recovered"))

    def factory(**kwargs):
        calls.append(kwargs)
        mode = modes.popleft()
        if mode == "silent":
            return SilentStream(owner, kwargs["callback"], active=True)
        return InputStream(owner, kwargs["callback"], active=True, stop_after_check=True)

    owner._audio_input_stream_factory = factory
    owner._audio_input_device_resolver = lambda: (4, "USB mic")
    owner._wait_for_audio_recovery = AsyncMock()
    with patch.object(main, "LIVE_INPUT_CALLBACK_STALE_SECONDS", 0.01):
        await owner._listen_audio()
    assert len(calls) == 2


def test_microphone_recovery_backoff_is_bounded():
    delays = [main._audio_device_recovery_delay(index) for index in range(1, 12)]
    assert delays[:6] == [0.5, 1.0, 2.0, 4.0, 8.0, 10.0]
    assert max(delays) == main.AUDIO_DEVICE_RECOVERY_MAX_DELAY_SECONDS == 10.0


@async_test
async def test_default_input_replacement_is_adopted_safely():
    owner = jarvis()
    calls = []
    owner._audio_input_stream_factory = recovering_factory(
        owner, [(False, False), (True, True)], calls,
    )
    devices = iter(((2, "Removed microphone"), (7, "New Windows default")))
    owner._audio_input_device_resolver = lambda: next(devices)
    owner._wait_for_audio_recovery = AsyncMock()
    await owner._listen_audio()
    assert [call["device"] for call in calls] == [2, 7]
    assert owner._audio_input_device_id == 7


@async_test
async def test_duplicate_microphone_worker_is_ignored():
    owner = jarvis()
    entered = asyncio.Event()

    async def hold_worker():
        entered.set()
        while owner._conversation_requested.is_set():
            await asyncio.sleep(0.01)

    owner._listen_audio_with_recovery = hold_worker
    first = asyncio.create_task(owner._listen_audio())
    await entered.wait()
    await owner._listen_audio()
    assert owner._audio_input_worker_lock.locked()
    owner._conversation_requested.clear()
    await first
    assert not owner._audio_input_worker_lock.locked()


@async_test
async def test_standby_cancels_pending_recovery_wait():
    owner = jarvis()
    entered = asyncio.Event()

    def unavailable(**_kwargs):
        entered.set()
        raise OSError("device unavailable")

    owner._audio_input_stream_factory = unavailable
    owner._audio_input_device_resolver = lambda: (1, "Unavailable mic")
    task = asyncio.create_task(owner._listen_audio())
    await entered.wait()
    owner.stop_conversation()
    await asyncio.wait_for(task, 1)
    assert not owner._audio_input_worker_lock.locked()


@async_test
async def test_shutdown_cancels_pending_recovery_wait():
    owner = jarvis()
    entered = asyncio.Event()

    def unavailable(**_kwargs):
        entered.set()
        raise OSError("device unavailable")

    owner._audio_input_stream_factory = unavailable
    owner._audio_input_device_resolver = lambda: (1, "Unavailable mic")
    task = asyncio.create_task(owner._listen_audio())
    await entered.wait()
    owner.request_shutdown()
    await asyncio.wait_for(task, 1)
    assert owner._shutdown_requested.is_set()
    assert not owner._audio_input_worker_lock.locked()


@async_test
async def test_repeated_disappearance_uses_one_worker_and_bounded_retries():
    owner = jarvis()
    calls = []
    owner._audio_input_stream_factory = recovering_factory(
        owner, [(False, False), (False, False), (True, True)], calls,
    )
    owner._audio_input_device_resolver = lambda: (5, "Flapping mic")
    owner._wait_for_audio_recovery = AsyncMock()
    await owner._listen_audio()
    assert len(calls) == 3
    assert owner._wait_for_audio_recovery.await_args_list[0].args == (0.5,)
    assert owner._wait_for_audio_recovery.await_args_list[1].args == (1.0,)


@async_test
async def test_recovery_discards_stale_microphone_queue_only_once():
    owner = jarvis()
    owner.out_queue.put_nowait({"data": b"old-audio", "mime_type": "audio/pcm"})
    calls = []
    owner._audio_input_stream_factory = recovering_factory(
        owner, [(False, False), (True, True)], calls,
    )
    owner._audio_input_device_resolver = lambda: (8, "Mic")
    owner._wait_for_audio_recovery = AsyncMock()
    await owner._listen_audio()
    assert owner.out_queue.empty()


@async_test
async def test_conversation_context_is_unchanged_by_microphone_recovery():
    owner = jarvis()
    owner._remember_conversation_text("user", "contexto PHY2-005")
    identity = owner._conversation_id
    continuity = list(owner._conversation_continuity)
    calls = []
    owner._audio_input_stream_factory = recovering_factory(
        owner, [(False, False), (True, True)], calls,
    )
    owner._audio_input_device_resolver = lambda: (9, "Mic")
    owner._wait_for_audio_recovery = AsyncMock()
    await owner._listen_audio()
    assert owner._conversation_id == identity
    assert owner._conversation_continuity == continuity


@async_test
async def test_output_stream_survives_backend_loss_and_restoration_without_reopen():
    owner = jarvis()
    writes = []

    class Output:
        def start(self): return None
        def write(self, chunk):
            writes.append(chunk)
            if len(writes) == 2:
                owner._conversation_requested.clear()
        def stop(self): return None
        def close(self): return None

    output = Output()
    owner._audio_output_device_resolver = lambda: (4, "M197WD", True)
    owner._audio_output_stream_factory = MagicMock(return_value=output)
    owner.audio_in_queue.put_nowait(b"before-device-toggle")
    owner.audio_in_queue.put_nowait(b"after-device-restore")
    await owner._play_audio()
    assert writes == [b"before-device-toggle", b"after-device-restore"]
    owner._audio_output_stream_factory.assert_called_once()
    assert owner._audio_output_device_id == 4


@async_test
async def test_output_returns_to_preferred_device_when_it_reappears():
    owner = jarvis()
    writes = []
    opened = []
    resolutions = deque((
        (5, "Fallback TV", False),
        (5, "Fallback TV", False),
        (4, "M197WD", True),
    ))

    class Output:
        def __init__(self, device):
            self.device = device
        def start(self): return None
        def write(self, chunk):
            writes.append((self.device, chunk))
            if len(writes) == 2:
                owner._conversation_requested.clear()
        def stop(self): return None
        def close(self): return None

    def factory(**kwargs):
        opened.append(kwargs["device"])
        return Output(kwargs["device"])

    owner._audio_output_device_resolver = lambda: resolutions.popleft()
    owner._audio_output_stream_factory = factory
    owner.audio_in_queue.put_nowait(b"fallback")
    owner.audio_in_queue.put_nowait(b"preferred0")
    with patch.object(main, "AUDIO_OUTPUT_RECHECK_SECONDS", 0.0):
        await owner._play_audio()

    assert opened == [5, 4]
    assert writes == [(5, b"fallback"), (4, b"preferred0")]
    assert owner._audio_output_device_id == 4


def test_output_worker_ownership_remains_single_live_taskgroup_contract():
    owner = jarvis()
    assert owner._live_runner_lock.acquire(blocking=False)
    try:
        assert not owner._live_runner_lock.acquire(blocking=False)
    finally:
        owner._live_runner_lock.release()
