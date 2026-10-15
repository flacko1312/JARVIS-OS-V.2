from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import ui
from actions.tts_engine import PROVIDER_VOICES
from core.voice_config import (
    DEFAULT_GEMINI_VOICE,
    GEMINI_VOICES,
    SUPPORTED_GEMINI_VOICE_NAMES,
    normalize_gemini_voice,
)


class _Timer:
    def __init__(self, active=False):
        self.active = active
        self.started = []
        self.stopped = 0

    def isActive(self):
        return self.active

    def start(self, interval):
        self.active = True
        self.started.append(interval)

    def stop(self):
        self.active = False
        self.stopped += 1


def _window(visible=True, minimized=False, timer_active=False):
    fake = SimpleNamespace(
        _metric_tmr=_Timer(timer_active), _graphics_quality="medium",
        isVisible=lambda: visible, isMinimized=lambda: minimized,
        _update_metrics=MagicMock(),
    )
    return fake


def test_metric_polling_stops_when_hidden():
    fake = _window(visible=False, timer_active=True)
    ui.MainWindow._sync_metric_polling(fake)
    assert fake._metric_tmr.stopped == 1


def test_metric_polling_stops_when_minimized():
    fake = _window(visible=True, minimized=True, timer_active=True)
    ui.MainWindow._sync_metric_polling(fake)
    assert fake._metric_tmr.stopped == 1


def test_metric_polling_resumes_at_selected_profile_interval():
    fake = _window(visible=True, minimized=False, timer_active=False)
    ui.MainWindow._sync_metric_polling(fake)
    assert fake._metric_tmr.started == [ui.GRAPHICS_PROFILES["medium"]["metrics_ms"]]
    fake._update_metrics.assert_called_once()


def test_hidden_update_does_not_sample_metrics():
    fake = SimpleNamespace(isVisible=lambda: False, isMinimized=lambda: False)
    with patch.object(ui, "_get_metrics") as metrics:
        ui.MainWindow._update_metrics(fake)
    metrics.assert_not_called()


def test_voice_catalog_is_shared_and_normalized():
    assert ui.VOICE_OPTIONS == list(GEMINI_VOICES)
    assert PROVIDER_VOICES["gemini"] == list(GEMINI_VOICES)
    assert {value for _label, value in GEMINI_VOICES} == SUPPORTED_GEMINI_VOICE_NAMES
    assert normalize_gemini_voice(" KORE ") == "kore"
    assert normalize_gemini_voice("not-a-real-voice") == DEFAULT_GEMINI_VOICE


def test_all_themes_define_every_required_token():
    for key, theme in ui.ThemeManager._THEMES.items():
        missing = set(ui.ThemeManager._COLOR_KEYS) - set(theme)
        assert not missing, f"{key} missing theme tokens: {sorted(missing)}"
