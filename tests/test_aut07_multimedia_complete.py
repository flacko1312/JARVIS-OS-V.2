import platform
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from actions import media_control


@pytest.mark.parametrize("value,expected", [(0, 0), ("42", 42), (100, 100)])
def test_volume_percent_accepts_bounds(value, expected):
    assert media_control._volume_percent(value) == expected


@pytest.mark.parametrize("value", [-1, 101, "loud"])
def test_volume_percent_rejects_invalid(value):
    with pytest.raises(ValueError):
        media_control._volume_percent(value)


@pytest.mark.skipif(platform.system() != "Windows", reason="pycaw is Windows-only")
def test_windows_set_volume_uses_endpoint_scalar():
    endpoint = MagicMock()
    speaker = SimpleNamespace(EndpointVolume=endpoint)
    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers", return_value=speaker):
        assert media_control._windows_volume("set_volume", 35) == "System volume set to 35%."
    endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.35, None)


@pytest.mark.parametrize(
    "action,current,expected",
    [("mute", False, True), ("unmute", True, False), ("toggle_mute", False, True)],
)
@pytest.mark.skipif(platform.system() != "Windows", reason="pycaw is Windows-only")
def test_windows_mute_actions(action, current, expected):
    endpoint = MagicMock()
    endpoint.GetMute.return_value = current
    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers", return_value=SimpleNamespace(EndpointVolume=endpoint)):
        media_control._windows_volume(action)
    endpoint.SetMute.assert_called_once_with(expected, None)


def test_volume_up_uses_system_volume_path():
    with patch.object(media_control, "_system_volume", return_value="ok") as volume:
        assert media_control.media_control({"action": "volume_up"}) == "ok"
    volume.assert_called_once_with("volume_up", None)


def test_set_volume_requires_valid_percentage():
    assert "between 0 and 100" in media_control.media_control({"action": "set_volume", "volume": 101})


def test_queue_capability_is_explicitly_unsupported():
    result = media_control.media_control({"action": "queue", "query": "song"})
    assert "unsupported" in result.lower()
    assert "will not guess" in result


def test_linux_pactl_exact_volume():
    completed = SimpleNamespace(returncode=0, stderr="", stdout="")
    with (
        patch.object(media_control, "_SYSTEM", "Linux"),
        patch.object(media_control.shutil, "which", return_value="/usr/bin/pactl"),
        patch.object(media_control, "_run", return_value=completed) as run,
    ):
        result = media_control._system_volume("set_volume", 55)
    assert "completed" in result
    run.assert_called_once_with(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "55%"])
