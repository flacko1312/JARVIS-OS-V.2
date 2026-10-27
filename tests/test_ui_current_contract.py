"""Executable checks for the UI contract that exists in the current product.

The historical first-run/tour specification remains in test_ui_regressions.py
as design evidence, but it does not describe code that ever shipped in ui.py.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import ui


class _NoSecrets:
    def get(self, _key):
        return None


class CurrentUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(cls.temp_dir.name)
        cls.patchers = [
            patch.object(ui, "UI_SETTINGS_FILE", temp_path / "ui_settings.json"),
            patch.object(ui, "LAYOUT_SETTINGS_FILE", temp_path / "layout_settings.json"),
            patch.object(ui, "API_FILE", temp_path / "api_keys.json"),
            patch.object(ui, "get_secret_store", return_value=_NoSecrets()),
            patch.object(ui.MainWindow, "_setup_system_tray", lambda self: None),
            patch.object(ui.MainWindow, "_update_metrics", lambda self: None),
            patch.object(ui.MainWindow, "_restore_detached_panels", lambda self: None),
            patch.object(ui.MainWindow, "_start_layout_autosave", lambda self: None),
            patch.object(ui.MainWindow, "_start_auto_graphics_detection", lambda self: None),
        ]
        for patcher in cls.patchers:
            patcher.start()
        ui.UI_SETTINGS_FILE.write_text(
            json.dumps({"intro_completed": True, "intro_every_launch": False}),
            encoding="utf-8",
        )
        cls.window = ui.MainWindow("face.png")
        cls.window.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.hide()
        cls.window.deleteLater()
        cls.app.processEvents()
        for patcher in reversed(cls.patchers):
            patcher.stop()
        cls.temp_dir.cleanup()

    def test_every_theme_has_a_complete_valid_palette(self):
        required = set(ui.ThemeManager._COLOR_KEYS)
        for name, theme in ui.ThemeManager._THEMES.items():
            self.assertFalse(required - set(theme), name)
            for key in required:
                self.assertRegex(theme[key], r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")

    def test_theme_change_updates_existing_widget_styles(self):
        ui.ThemeManager.set_theme("arc_reactor")
        ui.ThemeManager.set_theme("stealth_red")
        self.app.processEvents()
        self.assertEqual(ui.C.BG, "#080203")
        self.assertIn("#080203", self.window.centralWidget().styleSheet().lower())

    def test_quit_button_is_visible_and_accessible(self):
        button = self.window._quit_btn
        self.assertEqual(button.objectName(), "JarvisQuitButton")
        self.assertEqual(button.accessibleName(), "Quit AURORA")
        self.assertEqual(button.toolTip(), "Cerrar AURORA")
        self.assertFalse(button.isHidden())

    def test_conversation_button_starts_in_standby_and_toggles_callback(self):
        button = self.window._conversation_btn
        self.window._apply_state("STANDBY")
        self.assertEqual(button.text(), "▶ INICIAR CONVERSACIÓN")
        callback = Mock()
        self.window.on_conversation_toggle = callback
        button.click()
        callback.assert_called_once_with()
        self.window._apply_state("LISTENING")
        self.assertEqual(button.text(), "■ TERMINAR CONVERSACIÓN")
        self.assertIn("F8", button.toolTip())

    def test_dock_mute_state_reuses_command_rail_style(self):
        original = self.window._muted
        try:
            self.window._muted = True
            self.window._style_mute_btn()
            self.assertIn("SILENCIADO", self.window._mute_btn.text())
            self.assertEqual(self.window._mute_btn.accessibleName(), "Microphone muted")
            self.assertIn("border-radius: 5px", self.window._mute_btn.styleSheet())
            self.assertNotIn("border-radius: 17px", self.window._mute_btn.styleSheet())
        finally:
            self.window._muted = original
            self.window._style_mute_btn()

    def test_audio_button_opens_compact_selector_with_real_callbacks(self):
        snapshot = {
            "inputs": [
                {"device_id": "windows-default", "display_name": "Dispositivo predeterminado de Windows"},
                {"device_id": "input-realtek", "display_name": "Microphone (Realtek Audio)"},
            ],
            "outputs": [
                {"device_id": "windows-default", "display_name": "Dispositivo predeterminado de Windows"},
                {"device_id": "output-m197wd", "display_name": "M197WD (AMD High Definition Audio)"},
            ],
            "selected_input": "input-realtek",
            "selected_output": "output-m197wd",
        }
        self.window.on_audio_devices_request = Mock(return_value=snapshot)
        self.window.on_audio_input_select = Mock(return_value={"name": "Microphone (Realtek Audio)"})
        self.window.on_audio_output_select = Mock(return_value={"name": "M197WD"})
        self.window._audio_btn.click()
        self.app.processEvents()
        overlay = self.window._audio_overlay
        self.assertIsNotNone(overlay)
        self.assertTrue(overlay.isVisible())
        self.assertEqual(overlay.input_combo.currentData(), "input-realtek")
        self.assertEqual(overlay.output_combo.currentData(), "output-m197wd")
        self.assertNotIn("0", overlay.input_combo.currentText())
        self.window._close_audio_overlay()

    def test_audio_selector_applies_selection_immediately(self):
        snapshot = {
            "inputs": [
                {"device_id": "windows-default", "display_name": "Predeterminado"},
                {"device_id": "input-usb", "display_name": "USB Headset"},
            ],
            "outputs": [{"device_id": "windows-default", "display_name": "Predeterminado"}],
            "selected_input": "windows-default",
            "selected_output": "windows-default",
        }
        select_input = Mock(return_value={"name": "USB Headset"})
        self.window.on_audio_devices_request = Mock(return_value=snapshot)
        self.window.on_audio_input_select = select_input
        self.window.on_audio_output_select = Mock(return_value={"name": "Predeterminado"})
        self.window._show_audio_select()
        self.window._audio_overlay.input_combo.setCurrentIndex(1)
        self.app.processEvents()
        select_input.assert_called_once_with("input-usb")
        self.assertIn("USB Headset", self.window._audio_overlay.status_label.text())
        self.window._close_audio_overlay()

    def test_quit_command_uses_shared_shutdown_path(self):
        with (
            patch.object(self.window, "_request_quit") as request_quit,
            patch.object(ui.QTimer, "singleShot", side_effect=lambda _delay, callback: callback()),
        ):
            self.assertTrue(self.window._handle_ui_command("quit JARVIS"))
        request_quit.assert_called_once_with()

    def test_splitter_uses_evaluated_stylesheet(self):
        sheet = self.window._splitter.styleSheet()
        self.assertNotIn('f"""', sheet)
        self.assertNotIn("{C.", sheet)
        self.assertIn("QSplitter::handle", sheet)
