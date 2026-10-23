"""Block 5 — HUD, States, Avatar audit tests.

Covers: ui_locale.py (translation layer), core/graphics_capability.py
(GPU classification, quality scoring), and ui.py pure helpers
(graphics profiles, quality normalization, voice options, color constants).
PyQt6 widget tests require a running QApplication and are marked physical.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# A — UI LOCALE (ui_locale.py)
# ---------------------------------------------------------------------------

class TestTranslation(unittest.TestCase):

    def test_known_key(self):
        from ui_locale import t
        self.assertEqual(t("ONLINE"), "EN LÍNEA")

    def test_unknown_key_fallback(self):
        from ui_locale import t
        self.assertEqual(t("NONEXISTENT_KEY_XYZ"), "NONEXISTENT_KEY_XYZ")

    def test_all_values_are_strings(self):
        from ui_locale import UI_TEXT
        for key, val in UI_TEXT.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(val, str)

    def test_no_empty_translations(self):
        from ui_locale import UI_TEXT
        for key, val in UI_TEXT.items():
            self.assertTrue(val.strip(), f"Empty translation for '{key}'")


class TestStateDisplay(unittest.TestCase):

    def test_known_states(self):
        from ui_locale import state_display
        self.assertEqual(state_display("IDLE"), "EN ESPERA")
        self.assertEqual(state_display("LISTENING"), "ESCUCHANDO")
        self.assertEqual(state_display("THINKING"), "PENSANDO")
        self.assertEqual(state_display("EXECUTING"), "EJECUTANDO")
        self.assertEqual(state_display("SPEAKING"), "HABLANDO")
        self.assertEqual(state_display("ERROR"), "ERROR")
        self.assertEqual(state_display("ONLINE"), "EN LÍNEA")

    def test_unknown_state_fallback(self):
        from ui_locale import state_display
        self.assertEqual(state_display("UNKNOWN_STATE"), "UNKNOWN_STATE")

    def test_all_states_covered(self):
        from ui_locale import STATE_DISPLAY
        expected = {"IDLE", "STANDBY", "LISTENING", "THINKING", "EXECUTING",
                    "SPEAKING", "MUTED", "ERROR", "CONNECTING", "RECONNECTING",
                    "STOPPING", "PROCESSING", "ONLINE", "OFFLINE"}
        self.assertEqual(set(STATE_DISPLAY.keys()), expected)


class TestStatusAbbrev(unittest.TestCase):

    def test_known_abbreviations(self):
        from ui_locale import status_abbrev
        self.assertEqual(status_abbrev("PRIMARY"), "PRIM")
        self.assertEqual(status_abbrev("ONLINE"), "ENLN")
        self.assertEqual(status_abbrev("ACTIVE"), "ACTV")
        self.assertEqual(status_abbrev("IDLE"), "INAC")

    def test_unknown_truncates(self):
        from ui_locale import status_abbrev
        self.assertEqual(status_abbrev("LONGSTATUS"), "LONG")

    def test_short_input(self):
        from ui_locale import status_abbrev
        result = status_abbrev("AB")
        self.assertEqual(result, "AB")


# ---------------------------------------------------------------------------
# B — GRAPHICS CAPABILITY (core/graphics_capability.py)
# ---------------------------------------------------------------------------

class TestClassifyGpu(unittest.TestCase):

    def test_nvidia(self):
        from core.graphics_capability import _classify_gpu
        self.assertEqual(_classify_gpu("NVIDIA GeForce RTX 3080"), "discrete")

    def test_intel_integrated(self):
        from core.graphics_capability import _classify_gpu
        self.assertEqual(_classify_gpu("Intel UHD Graphics 630"), "integrated")

    def test_apple_silicon(self):
        from core.graphics_capability import _classify_gpu
        self.assertEqual(_classify_gpu("Apple M2 Pro"), "apple_silicon")

    def test_software_renderer(self):
        from core.graphics_capability import _classify_gpu
        self.assertEqual(_classify_gpu("llvmpipe"), "software")
        self.assertEqual(_classify_gpu("Microsoft Basic Display Adapter"), "software")

    def test_empty(self):
        from core.graphics_capability import _classify_gpu
        self.assertEqual(_classify_gpu(""), "unknown")
        self.assertEqual(_classify_gpu(None), "unknown")

    def test_amd_discrete(self):
        from core.graphics_capability import _classify_gpu
        self.assertEqual(_classify_gpu("Radeon RX 7900"), "discrete")

    def test_intel_arc(self):
        from core.graphics_capability import _classify_gpu
        self.assertEqual(_classify_gpu("Intel Arc A770"), "discrete")


class TestScoreGraphicsCapability(unittest.TestCase):

    def test_low_end(self):
        from core.graphics_capability import score_graphics_capability
        cap = score_graphics_capability(
            system="Windows", physical_cores=2, logical_cores=4,
            ram_gb=4.0, gpu_name="llvmpipe", vram_mb=None,
        )
        self.assertEqual(cap.quality, "low")
        self.assertEqual(cap.gpu_class, "software")

    def test_high_end(self):
        from core.graphics_capability import score_graphics_capability
        cap = score_graphics_capability(
            system="Windows", physical_cores=16, logical_cores=32,
            ram_gb=64.0, gpu_name="NVIDIA GeForce RTX 4090", vram_mb=24576,
        )
        self.assertEqual(cap.quality, "high")
        self.assertEqual(cap.gpu_class, "discrete")

    def test_medium(self):
        from core.graphics_capability import score_graphics_capability
        cap = score_graphics_capability(
            system="Windows", physical_cores=6, logical_cores=12,
            ram_gb=16.0, gpu_name="Intel UHD 630", vram_mb=None,
        )
        self.assertEqual(cap.quality, "medium")

    def test_fingerprint_deterministic(self):
        from core.graphics_capability import score_graphics_capability
        kwargs = dict(system="Linux", physical_cores=8, logical_cores=16,
                      ram_gb=32.0, gpu_name="RTX 3070", vram_mb=8192)
        a = score_graphics_capability(**kwargs)
        b = score_graphics_capability(**kwargs)
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_to_dict(self):
        from core.graphics_capability import score_graphics_capability
        cap = score_graphics_capability(
            system="Darwin", physical_cores=8, logical_cores=8,
            ram_gb=16.0, gpu_name="Apple M2", vram_mb=None,
        )
        d = cap.to_dict()
        self.assertIn("quality", d)
        self.assertIn("fingerprint", d)

    def test_none_values_handled(self):
        from core.graphics_capability import score_graphics_capability
        cap = score_graphics_capability(
            system="", physical_cores=0, logical_cores=0,
            ram_gb=0, gpu_name=None, vram_mb=None,
        )
        self.assertIn(cap.quality, ("low", "medium", "high"))

    def test_vram_in_reason(self):
        from core.graphics_capability import score_graphics_capability
        cap = score_graphics_capability(
            system="Windows", physical_cores=8, logical_cores=16,
            ram_gb=32.0, gpu_name="RTX 4080", vram_mb=16384,
        )
        self.assertIn("VRAM", cap.reason)


# ---------------------------------------------------------------------------
# C — UI HELPERS (ui.py — no QApplication needed)
# ---------------------------------------------------------------------------

class TestNormalizeGraphicsQuality(unittest.TestCase):

    def test_valid_values(self):
        from ui import _normalize_graphics_quality
        self.assertEqual(_normalize_graphics_quality("low"), "low")
        self.assertEqual(_normalize_graphics_quality("medium"), "medium")
        self.assertEqual(_normalize_graphics_quality("high"), "high")

    def test_aliases(self):
        from ui import _normalize_graphics_quality
        self.assertEqual(_normalize_graphics_quality("med"), "medium")
        self.assertEqual(_normalize_graphics_quality("max"), "high")
        self.assertEqual(_normalize_graphics_quality("performance"), "low")
        self.assertEqual(_normalize_graphics_quality("ultra"), "high")
        self.assertEqual(_normalize_graphics_quality("battery"), "low")

    def test_case_insensitive(self):
        from ui import _normalize_graphics_quality
        self.assertEqual(_normalize_graphics_quality("HIGH"), "high")
        self.assertEqual(_normalize_graphics_quality("Medium"), "medium")

    def test_none_defaults_medium(self):
        from ui import _normalize_graphics_quality
        self.assertEqual(_normalize_graphics_quality(None), "medium")

    def test_invalid_raises(self):
        from ui import _normalize_graphics_quality
        with self.assertRaises(ValueError):
            _normalize_graphics_quality("extreme")


class TestGraphicsProfiles(unittest.TestCase):

    def test_profiles_exist(self):
        from ui import GRAPHICS_PROFILES
        self.assertIn("low", GRAPHICS_PROFILES)
        self.assertIn("medium", GRAPHICS_PROFILES)
        self.assertIn("high", GRAPHICS_PROFILES)

    def test_fps_ordering(self):
        from ui import GRAPHICS_PROFILES
        self.assertGreater(
            GRAPHICS_PROFILES["low"]["frame_ms"],
            GRAPHICS_PROFILES["medium"]["frame_ms"],
        )
        self.assertGreater(
            GRAPHICS_PROFILES["medium"]["frame_ms"],
            GRAPHICS_PROFILES["high"]["frame_ms"],
        )

    def test_required_keys(self):
        from ui import GRAPHICS_PROFILES
        required = {"frame_ms", "render_stride", "wave_stride", "noise_count",
                    "scanline_step", "antialias", "activity_nodes", "metrics_ms"}
        for profile in GRAPHICS_PROFILES.values():
            self.assertTrue(required.issubset(profile.keys()))


class TestVoiceOptions(unittest.TestCase):

    def test_voices_exist(self):
        from ui import VOICE_OPTIONS
        self.assertGreater(len(VOICE_OPTIONS), 0)
        for label, value in VOICE_OPTIONS:
            self.assertTrue(label)
            self.assertTrue(value)

    def test_bidirectional_maps(self):
        from ui import VOICE_VALUE_TO_LABEL, VOICE_LABEL_TO_VALUE
        self.assertEqual(VOICE_VALUE_TO_LABEL["charon"], "Charon")
        self.assertEqual(VOICE_LABEL_TO_VALUE["charon"], "charon")

    def test_all_voices_in_maps(self):
        from ui import VOICE_OPTIONS, VOICE_VALUE_TO_LABEL, VOICE_LABEL_TO_VALUE
        for label, value in VOICE_OPTIONS:
            self.assertIn(value, VOICE_VALUE_TO_LABEL)
            self.assertIn(label.lower(), VOICE_LABEL_TO_VALUE)


class TestColorConstants(unittest.TestCase):

    def test_colors_are_hex(self):
        from ui import C
        import re
        hex_re = re.compile(r"^#[0-9a-fA-F]{6,8}$")
        for attr in ("BG", "PRI", "ACC", "TEXT", "WHITE", "RED", "GREEN", "PURPLE"):
            val = getattr(C, attr)
            self.assertTrue(hex_re.match(val), f"C.{attr} = '{val}' is not valid hex")


class TestReadUISettings(unittest.TestCase):

    def test_missing_file(self):
        from ui import _read_ui_settings
        with patch("ui.UI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            result = _read_ui_settings()
        self.assertEqual(result, {})

    def test_valid_file(self):
        from ui import _read_ui_settings
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"graphics_quality": "high"}, f)
        try:
            with patch("ui.UI_SETTINGS_FILE", Path(f.name)):
                result = _read_ui_settings()
            self.assertEqual(result["graphics_quality"], "high")
        finally:
            os.unlink(f.name)

    def test_corrupt_file(self):
        from ui import _read_ui_settings
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not json{{{")
        try:
            with patch("ui.UI_SETTINGS_FILE", Path(f.name)):
                result = _read_ui_settings()
            self.assertEqual(result, {})
        finally:
            os.unlink(f.name)


# ---------------------------------------------------------------------------
# D — PHYSICAL TESTS (require QApplication / display)
# ---------------------------------------------------------------------------

class TestHUDPhysical(unittest.TestCase):

    @unittest.skip("PHYSICAL TEST REQUIRED — needs QApplication + display")
    def test_main_window_launches(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs QApplication + display")
    def test_theme_cycling(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs QApplication + display")
    def test_compact_mode_toggle(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs QApplication + display")
    def test_state_transitions(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs QApplication + display")
    def test_avatar_animation(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs QApplication + display")
    def test_system_tray(self):
        pass


if __name__ == "__main__":
    unittest.main()
