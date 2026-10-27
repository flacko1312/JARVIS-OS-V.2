from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import main
from core.audio_devices import AudioDeviceManager, DEFAULT_DEVICE_ID


class FakeSoundDevice:
    def __init__(self):
        self.devices = [
            {"name": "Microphone (Realtek Audio)", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
            {"name": "M197WD", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
            {"name": "USB Headset", "hostapi": 0, "max_input_channels": 1, "max_output_channels": 2},
        ]
        self.hostapis = [
            {"name": "Windows WASAPI", "default_input_device": 0, "default_output_device": 1},
            {"name": "Windows DirectSound", "default_input_device": -1, "default_output_device": -1},
        ]
        self.default = SimpleNamespace(device=(0, 1))
        self.unsupported = set()

    def query_devices(self, index=None, kind=None):
        if index is None:
            return list(self.devices)
        return dict(self.devices[int(index)])

    def query_hostapis(self, index=None):
        if index is None:
            return list(self.hostapis)
        return dict(self.hostapis[int(index)])

    def check_input_settings(self, *, device, **_kwargs):
        if ("input", device) in self.unsupported:
            raise ValueError("unsupported")

    def check_output_settings(self, *, device, **_kwargs):
        if ("output", device) in self.unsupported:
            raise ValueError("unsupported")


@pytest.fixture
def device_manager(tmp_path):
    backend = FakeSoundDevice()
    manager = AudioDeviceManager(backend, settings_path=tmp_path / "audio.json")
    return manager, backend


def test_enumerates_real_input_devices(device_manager):
    manager, _ = device_manager
    assert [item.name for item in manager.list_input_devices()] == [
        "Dispositivo predeterminado de Windows", "Microphone (Realtek Audio)", "USB Headset",
    ]


def test_enumerates_real_output_devices(device_manager):
    manager, _ = device_manager
    assert [item.name for item in manager.list_output_devices()] == [
        "Dispositivo predeterminado de Windows", "M197WD", "USB Headset",
    ]


def test_ui_identity_is_stable_when_numeric_indices_change(tmp_path):
    backend = FakeSoundDevice()
    manager = AudioDeviceManager(backend, settings_path=tmp_path / "audio.json")
    original = {item.name: item.device_id for item in manager.list_output_devices()}
    backend.devices.insert(0, {"name": "Webcam", "hostapi": 0, "max_input_channels": 1, "max_output_channels": 0})
    refreshed = {item.name: item.device_id for item in manager.list_output_devices()}
    assert refreshed["M197WD"] == original["M197WD"]
    assert refreshed["USB Headset"] == original["USB Headset"]


def test_selecting_input_persists_stable_identity(device_manager):
    manager, _ = device_manager
    selected = manager.list_input_devices()[1]
    assert manager.select_input(selected.device_id) == selected
    assert json.loads(manager.settings_path.read_text(encoding="utf-8"))["input"] == selected.device_id


def test_selecting_output_persists_stable_identity(device_manager):
    manager, _ = device_manager
    selected = manager.list_output_devices()[1]
    assert manager.select_output(selected.device_id) == selected
    assert json.loads(manager.settings_path.read_text(encoding="utf-8"))["output"] == selected.device_id


def test_restart_restores_both_preferences(device_manager):
    manager, backend = device_manager
    input_device = manager.list_input_devices()[2]
    output_device = manager.list_output_devices()[1]
    manager.select_input(input_device.device_id)
    manager.select_output(output_device.device_id)
    restored = AudioDeviceManager(backend, settings_path=manager.settings_path)
    assert restored.preferred_id("input") == input_device.device_id
    assert restored.preferred_id("output") == output_device.device_id


def test_missing_saved_input_falls_back_without_erasing_preference(device_manager):
    manager, backend = device_manager
    selected = manager.list_input_devices()[2]
    manager.select_input(selected.device_id)
    backend.devices.pop(2)
    index, name = manager.resolve_input()
    assert (index, name) == (0, "Microphone (Realtek Audio)")
    assert manager.preferred_id("input") == selected.device_id


def test_saved_input_is_recovered_when_device_returns(device_manager):
    manager, backend = device_manager
    selected = manager.list_input_devices()[2]
    manager.select_input(selected.device_id)
    removed = backend.devices.pop(2)
    assert manager.resolve_input()[0] == 0
    backend.devices.append(removed)
    assert manager.resolve_input() == (2, "USB Headset")


def test_incompatible_output_falls_back_safely(device_manager):
    manager, backend = device_manager
    selected = manager.list_output_devices()[2]
    manager.select_output(selected.device_id)
    backend.unsupported.add(("output", 2))
    assert manager.resolve_output() == (1, "M197WD", False)


def test_select_default_windows_device(device_manager):
    manager, _ = device_manager
    manager.select_input(DEFAULT_DEVICE_ID)
    manager.select_output(DEFAULT_DEVICE_ID)
    assert manager.resolve_input() == (0, "Microphone (Realtek Audio)")
    assert manager.resolve_output() == (1, "M197WD", False)


class UI:
    def __init__(self):
        self.muted = False
        self.logs = []
        self.on_text_command = None
        self.on_conversation_toggle = None

    def set_state(self, _state): pass
    def write_log(self, text): self.logs.append(text)


def make_jarvis():
    owner = main.JarvisLive(UI(), cloud_safe=True, api_key="test", external_audio=False)
    owner._conversation_requested.set()
    owner.out_queue = asyncio.Queue()
    owner.audio_in_queue = asyncio.Queue()
    owner._turn_done_event = asyncio.Event()
    return owner


def test_engine_selection_requests_immediate_input_and_output_switch(device_manager):
    owner = make_jarvis()
    manager, _ = device_manager
    owner._audio_device_manager = manager
    owner.select_audio_input(manager.list_input_devices()[1].device_id)
    owner.select_audio_output(manager.list_output_devices()[1].device_id)
    assert owner._audio_input_switch_requested.is_set()
    assert owner._audio_output_switch_requested.is_set()


def test_f4_mute_state_is_not_changed_by_device_selection(device_manager):
    owner = make_jarvis()
    manager, _ = device_manager
    owner._audio_device_manager = manager
    owner.ui.muted = True
    owner.select_audio_input(manager.list_input_devices()[1].device_id)
    assert owner.ui.muted is True


def test_f8_conversation_state_is_not_changed_by_device_selection(device_manager):
    owner = make_jarvis()
    manager, _ = device_manager
    owner._audio_device_manager = manager
    before = owner.conversation_state
    owner.select_audio_output(manager.list_output_devices()[1].device_id)
    assert owner.conversation_state == before
    assert owner._conversation_requested.is_set()


def test_manual_input_switch_closes_old_stream_before_opening_new():
    async def scenario():
        owner = make_jarvis()
        lifecycle = []
        open_count = 0

        class Stream:
            active = True
            def __init__(self, number): self.number = number
            def __enter__(self):
                lifecycle.append(("open", self.number))
                return self
            def __exit__(self, *_args):
                lifecycle.append(("close", self.number))

        def factory(**_kwargs):
            nonlocal open_count
            open_count += 1
            if open_count == 1:
                owner._audio_input_switch_requested.set()
            else:
                async def stop_soon():
                    await asyncio.sleep(0.12)
                    owner._conversation_requested.clear()
                asyncio.create_task(stop_soon())
            return Stream(open_count)

        owner._audio_input_stream_factory = factory
        owner._audio_input_device_resolver = lambda: (open_count, f"Mic {open_count}")
        await owner._listen_audio()
        assert lifecycle[:3] == [("open", 1), ("close", 1), ("open", 2)]
        assert max(sum(1 if action == "open" else -1 for action, _ in lifecycle[:i + 1]) for i in range(len(lifecycle))) == 1

    asyncio.run(scenario())


def test_running_input_returns_to_saved_device_when_it_reappears(monkeypatch):
    async def scenario():
        owner = make_jarvis()
        lifecycle = []
        resolutions = iter(((0, "Windows default"), (2, "USB mic"), (2, "USB mic")))

        class Stream:
            active = True
            def __init__(self, device): self.device = device
            def __enter__(self):
                lifecycle.append(("open", self.device))
                if self.device == 2:
                    async def stop_soon():
                        await asyncio.sleep(0.12)
                        owner._conversation_requested.clear()
                    asyncio.create_task(stop_soon())
                return self
            def __exit__(self, *_args): lifecycle.append(("close", self.device))

        owner._audio_input_device_resolver = lambda: next(resolutions)
        owner._audio_input_stream_factory = lambda **kwargs: Stream(kwargs["device"])
        monkeypatch.setattr(main, "AUDIO_INPUT_RECHECK_SECONDS", 0.0)
        await owner._listen_audio()
        assert lifecycle[:3] == [("open", 0), ("close", 0), ("open", 2)]

    asyncio.run(scenario())


def test_output_switch_closes_previous_app_stream_without_touching_windows_default():
    async def scenario():
        owner = make_jarvis()
        lifecycle = []
        devices = [(1, "Speakers", True), (2, "Headphones", True)]

        class Stream:
            def __init__(self, device): self.device = device
            def start(self): lifecycle.append(("start", self.device))
            def stop(self): lifecycle.append(("stop", self.device))
            def close(self): lifecycle.append(("close", self.device))
            def write(self, chunk):
                lifecycle.append(("write", self.device, chunk))
                if chunk == b"one\x00":
                    devices.pop(0)
                    owner._audio_output_switch_requested.set()
                else:
                    owner._conversation_requested.clear()

        owner._audio_output_device_resolver = lambda: devices[0]
        owner._audio_output_stream_factory = lambda **kwargs: Stream(kwargs["device"])
        owner.audio_in_queue.put_nowait(b"one\x00")
        owner.audio_in_queue.put_nowait(b"two\x00")
        await owner._play_audio()
        assert lifecycle.index(("close", 1)) < lifecycle.index(("start", 2))
        assert ("write", 2, b"two\x00") in lifecycle

    asyncio.run(scenario())


def test_refresh_snapshot_never_exposes_numeric_indices(device_manager):
    manager, _ = device_manager
    snapshot = manager.refresh_devices()
    assert all("index" in item for item in snapshot["inputs"])
    # The transport may carry an index internally, but UI labels and stable IDs do not use it.
    assert all(not str(item["display_name"]).isdigit() for item in snapshot["inputs"] + snapshot["outputs"])
    assert all(
        item["device_id"] == DEFAULT_DEVICE_ID
        or (item["device_id"].startswith(("input-", "output-")) and len(item["device_id"].split("-", 1)[1]) == 20)
        for item in snapshot["inputs"] + snapshot["outputs"]
    )


def test_windows_catalog_hides_legacy_backend_duplicates(device_manager):
    manager, backend = device_manager
    backend.devices.extend([
        {"name": "Asignador de sonido Microsoft - Input", "hostapi": 1, "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Microphone (Realtek Audio)", "hostapi": 1, "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Asignador de sonido Microsoft - Output", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2},
        {"name": "M197WD", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2},
    ])

    assert [item.name for item in manager.list_input_devices()] == [
        "Dispositivo predeterminado de Windows", "Microphone (Realtek Audio)", "USB Headset",
    ]
    assert [item.name for item in manager.list_output_devices()] == [
        "Dispositivo predeterminado de Windows", "M197WD", "USB Headset",
    ]


def test_windows_default_comes_from_wasapi_not_legacy_global_default(device_manager):
    manager, backend = device_manager
    backend.devices.extend([
        {"name": "Legacy input mapper", "hostapi": 1, "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Legacy output mapper", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2},
    ])
    backend.default.device = (3, 4)

    assert manager.resolve_input() == (0, "Microphone (Realtek Audio)")
    assert manager.resolve_output() == (1, "M197WD", False)
