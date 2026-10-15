import unittest
from unittest.mock import patch

from actions import safe_text_entry as ste


def editor(**overrides):
    value = {
        "process_id": 120,
        "process_name": "Notepad.exe",
        "control_type": ste.WINDOWS_DOCUMENT_CONTROL_TYPE,
        "class_name": "RichEditD2DPT",
        "name": "Editor de texto",
        "automation_id": "TextArea",
        "enabled": True,
        "keyboard_focusable": True,
        "has_keyboard_focus": True,
        "native_handle": 501,
        "root_handle": 500,
        "runtime_id": (42, 501, 3),
        "read_only": None,
        "text_value": "",
        "supports_text": True,
    }
    value.update(overrides)
    return value


def jarvis_focus():
    return {
        "process_id": 900,
        "process_name": "jarvis.exe",
        "control_type": 50000,
        "class_name": "QtWidget",
        "enabled": True,
        "keyboard_focusable": True,
        "has_keyboard_focus": True,
        "native_handle": 901,
        "root_handle": 900,
        "runtime_id": (9, 0, 1),
    }


class WindowsFocusStabilityTests(unittest.TestCase):
    def setUp(self):
        ste._WINDOWS_TARGET_CACHE = None

    def _seed(self, info=None, tick=10):
        with patch.object(ste, "_windows_last_input_tick", return_value=tick):
            ste._cache_windows_target(info or editor(), "generic")

    def test_first_insertion_validates_current_editor(self):
        with (
            patch.object(ste, "_windows_focused_element_info", return_value=editor()),
            patch.object(ste, "_windows_last_input_tick", return_value=10),
        ):
            result, info = ste._resolve_windows_target("generic")
        self.assertTrue(result.ok)
        self.assertEqual(info["process_name"], "Notepad.exe")

    def test_second_consecutive_command_reacquires_without_click(self):
        self._seed()
        with (
            patch.object(ste.os, "getpid", return_value=900),
            patch.object(ste, "_windows_last_input_tick", return_value=10),
            patch.object(ste, "_windows_window_exists", return_value=True),
            patch.object(ste, "_windows_activate_window", return_value=True) as activate,
            patch.object(ste, "_windows_focused_element_info", side_effect=[jarvis_focus(), editor()]),
            patch.object(ste.time, "sleep"),
        ):
            result, _ = ste._resolve_windows_target("generic")
        self.assertTrue(result.ok)
        activate.assert_called_once_with(500)

    def test_runtime_id_change_is_same_stable_editor(self):
        self.assertEqual(
            ste._windows_target_id(editor(runtime_id=(1, 2, 3))),
            ste._windows_target_id(editor(runtime_id=(8, 9, 10))),
        )

    def test_temporary_jarvis_focus_does_not_invalidate(self):
        self._seed()
        with (
            patch.object(ste.os, "getpid", return_value=900),
            patch.object(ste, "_windows_last_input_tick", return_value=10),
            patch.object(ste, "_windows_window_exists", return_value=True),
            patch.object(ste, "_windows_activate_window", return_value=True),
            patch.object(ste, "_windows_focused_element_info", side_effect=[jarvis_focus(), editor()]),
            patch.object(ste.time, "sleep"),
        ):
            result, _ = ste._resolve_windows_target("generic")
        self.assertTrue(result.ok)
        self.assertIsNotNone(ste._WINDOWS_TARGET_CACHE)

    def test_real_user_click_on_jarvis_invalidates(self):
        self._seed()
        with (
            patch.object(ste.os, "getpid", return_value=900),
            patch.object(ste, "_windows_last_input_tick", return_value=11),
            patch.object(ste, "_windows_focused_element_info", return_value=jarvis_focus()),
        ):
            result, _ = ste._resolve_windows_target("generic")
        self.assertFalse(result.ok)
        self.assertIsNone(ste._WINDOWS_TARGET_CACHE)

    def test_other_application_foreground_invalidates_without_reuse(self):
        self._seed()
        other = editor(process_id=777, process_name="chrome.exe", control_type=50000)
        with patch.object(ste, "_windows_focused_element_info", return_value=other):
            result, _ = ste._resolve_windows_target("generic")
        self.assertFalse(result.ok)
        self.assertIsNone(ste._WINDOWS_TARGET_CACHE)

    def test_destroyed_target_is_not_reused(self):
        self._seed()
        with (
            patch.object(ste.os, "getpid", return_value=900),
            patch.object(ste, "_windows_last_input_tick", return_value=10),
            patch.object(ste, "_windows_window_exists", return_value=False),
            patch.object(ste, "_windows_focused_element_info", return_value=jarvis_focus()),
        ):
            result, _ = ste._resolve_windows_target("generic")
        self.assertFalse(result.ok)
        self.assertIsNone(ste._WINDOWS_TARGET_CACHE)

    def test_reacquired_read_only_target_is_refused(self):
        self._seed()
        with (
            patch.object(ste.os, "getpid", return_value=900),
            patch.object(ste, "_windows_last_input_tick", return_value=10),
            patch.object(ste, "_windows_window_exists", return_value=True),
            patch.object(ste, "_windows_activate_window", return_value=True),
            patch.object(ste, "_windows_focused_element_info", side_effect=[jarvis_focus(), editor(read_only=True)]),
            patch.object(ste.time, "sleep"),
        ):
            result, _ = ste._resolve_windows_target("generic")
        self.assertFalse(result.ok)
        self.assertIsNone(ste._WINDOWS_TARGET_CACHE)

    def test_expired_target_is_not_reused(self):
        self._seed()
        ste._WINDOWS_TARGET_CACHE.validated_at -= ste.WINDOWS_TARGET_CACHE_TTL_SECONDS + 1
        with patch.object(ste, "_windows_focused_element_info", return_value=jarvis_focus()):
            result, _ = ste._resolve_windows_target("generic")
        self.assertFalse(result.ok)
        self.assertIsNone(ste._WINDOWS_TARGET_CACHE)

    def test_unicode_is_sent_exactly_once(self):
        text = "áéíóú ñ ¿Qué tal?"
        calls = []
        with (
            patch.object(ste, "_windows_focus_matches", return_value=True),
            patch.object(ste, "_windows_send_input", side_effect=lambda units: calls.append(units) or True),
        ):
            ok, _ = ste._write_windows_unicode(text, ste._windows_target_id(editor()))
        self.assertTrue(ok)
        reconstructed = b"".join(
            unit.to_bytes(2, "little") for call in calls for key, unit in call if key == 0
        ).decode("utf-16-le")
        self.assertEqual(reconstructed, text)

    def test_focus_change_during_send_aborts_before_remaining_characters(self):
        with (
            patch.object(ste, "_windows_focus_matches", side_effect=[True, False]),
            patch.object(ste, "_windows_send_input", return_value=True) as send,
        ):
            ok, message = ste._write_windows_unicode("abc", ste._windows_target_id(editor()))
        self.assertFalse(ok)
        self.assertIn("foco cambió", message)
        self.assertEqual(send.call_count, 1)

    def test_repeated_reacquisition_does_not_duplicate_write(self):
        self._seed()
        with (
            patch.object(ste.os, "getpid", return_value=900),
            patch.object(ste, "_windows_last_input_tick", return_value=10),
            patch.object(ste, "_windows_window_exists", return_value=True),
            patch.object(ste, "_windows_activate_window", return_value=True) as activate,
            patch.object(ste, "_windows_focused_element_info", side_effect=[jarvis_focus(), editor()]),
            patch.object(ste.time, "sleep"),
        ):
            result, _ = ste._resolve_windows_target("generic")
        self.assertTrue(result.ok)
        self.assertEqual(activate.call_count, 1)


if __name__ == "__main__":
    unittest.main()
