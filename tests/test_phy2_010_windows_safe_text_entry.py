import unittest
from unittest.mock import MagicMock, patch

import pyperclip

from actions import safe_text_entry


def focused_edit(**overrides) -> dict:
    info = {
        "process_id": 120,
        "process_name": "Notepad.exe",
        "control_type": safe_text_entry.WINDOWS_DOCUMENT_CONTROL_TYPE,
        "class_name": "RichEditD2DPT",
        "name": "Editor de texto",
        "automation_id": "TextArea",
        "enabled": True,
        "keyboard_focusable": True,
        "has_keyboard_focus": True,
        "native_handle": 501,
        "runtime_id": (42, 501, 3),
        "read_only": None,
        "text_value": "",
        "supports_text": True,
    }
    info.update(overrides)
    return info


def safe_type_with_readback(text: str, *, before: str = "", after: str | None = None, **kwargs):
    first = focused_edit(text_value=before)
    second = focused_edit(text_value=before)
    third = focused_edit(text_value=text if after is None else after)
    with (
        patch.object(safe_text_entry, "_PYAUTOGUI", True),
        patch.object(safe_text_entry, "_actual_os", return_value="windows"),
        patch.object(safe_text_entry, "_windows_focused_element_info", side_effect=[first, second, third]),
        patch.object(safe_text_entry, "_write_windows_unicode", return_value=(True, "")) as write,
    ):
        result = safe_text_entry.safe_type_text(text, **kwargs)
    return result, write


class WindowsSafeTargetValidationTests(unittest.TestCase):
    def test_windows_11_notepad_editable_document_is_accepted(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit())
        self.assertTrue(result.ok)
        self.assertEqual(result.safety_path, "windows_uia")

    def test_standard_edit_control_is_accepted_when_writable(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit(
            process_name="sample.exe",
            control_type=safe_text_entry.WINDOWS_EDIT_CONTROL_TYPE,
            read_only=False,
            supports_text=False,
        ))
        self.assertTrue(result.ok)

    def test_browser_text_input_is_accepted_when_uia_marks_it_writable(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit(
            process_name="chrome.exe",
            control_type=safe_text_entry.WINDOWS_EDIT_CONTROL_TYPE,
            name="Nombre",
            automation_id="first-name",
            read_only=False,
            supports_text=False,
        ))
        self.assertTrue(result.ok)

    def test_no_focused_element_is_refused(self):
        result = safe_text_entry._validate_windows_text_target({})
        self.assertFalse(result.ok)

    def test_read_only_target_is_refused(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit(read_only=True))
        self.assertFalse(result.ok)
        self.assertIn("solo lectura", result.message)

    def test_desktop_focus_is_refused(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit(
            process_name="explorer.exe",
            control_type=50033,
            class_name="SysListView32",
            read_only=None,
            supports_text=False,
        ))
        self.assertFalse(result.ok)
        self.assertIn("escritorio", result.message)

    def test_non_text_control_is_refused(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit(control_type=50000))
        self.assertFalse(result.ok)

    def test_protected_terminal_or_code_target_is_refused(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit(
            process_name="Code.exe",
            control_type=safe_text_entry.WINDOWS_EDIT_CONTROL_TYPE,
            read_only=False,
        ))
        self.assertFalse(result.ok)
        self.assertIn("protegida", result.message)

    def test_browser_address_bar_is_refused(self):
        result = safe_text_entry._validate_windows_text_target(focused_edit(
            process_name="chrome.exe",
            control_type=safe_text_entry.WINDOWS_EDIT_CONTROL_TYPE,
            name="Address and search bar",
            read_only=False,
            supports_text=False,
        ))
        self.assertFalse(result.ok)
        self.assertIn("direcciones", result.message)


class WindowsSafeTypingTests(unittest.TestCase):
    def test_unicode_text_is_passed_without_normalization(self):
        text = "Prueba física JARVIS, áéíóú ñ ü ¿Qué tal? ¡Bien! 5827"
        result, write = safe_type_with_readback(text)
        self.assertTrue(result.ok)
        write.assert_called_once()
        self.assertEqual(write.call_args.args[0], text)

    def test_native_unicode_writer_preserves_accents_and_inverted_punctuation(self):
        text = "áéíóú ñ ü ¿Qué tal? ¡Sí!"
        captured: list[list[tuple[int, int]]] = []
        with (
            patch.object(safe_text_entry, "_windows_focus_matches", return_value=True),
            patch.object(safe_text_entry, "_windows_send_input", side_effect=lambda units: captured.append(units) or True),
        ):
            ok, error = safe_text_entry._write_windows_unicode(text, (1,))
        self.assertTrue(ok, error)
        reconstructed = b"".join(
            unit.to_bytes(2, "little")
            for call in captured
            for virtual_key, unit in call
            if virtual_key == 0
        ).decode("utf-16-le")
        self.assertEqual(reconstructed, text)

    def test_multiline_input_is_sent_as_one_guarded_operation(self):
        text = "línea uno\nlínea dos\n¿fin?"
        result, write = safe_type_with_readback(text)
        self.assertTrue(result.ok)
        write.assert_called_once()
        self.assertEqual(write.call_args.args[0], text)

    def test_empty_text_is_refused_before_focus_or_input(self):
        with (
            patch.object(safe_text_entry, "_PYAUTOGUI", True),
            patch.object(safe_text_entry, "_windows_focused_element_info") as probe,
            patch.object(safe_text_entry, "_write_windows_unicode") as write,
        ):
            result = safe_text_entry.safe_type_text("")
        self.assertFalse(result.ok)
        probe.assert_not_called()
        write.assert_not_called()

    def test_clipboard_is_untouched_for_unicode_success(self):
        with (
            patch.object(pyperclip, "paste") as paste,
            patch.object(pyperclip, "copy") as copy,
        ):
            result, _write = safe_type_with_readback("áéíóú ñ")
        self.assertTrue(result.ok)
        paste.assert_not_called()
        copy.assert_not_called()

    def test_clipboard_remains_untouched_after_input_failure(self):
        info = focused_edit()
        with (
            patch.object(safe_text_entry, "_PYAUTOGUI", True),
            patch.object(safe_text_entry, "_actual_os", return_value="windows"),
            patch.object(safe_text_entry, "_windows_focused_element_info", side_effect=[info, info]),
            patch.object(safe_text_entry, "_write_windows_unicode", return_value=(False, "target disappeared")),
            patch.object(pyperclip, "paste") as paste,
            patch.object(pyperclip, "copy") as copy,
        ):
            result = safe_text_entry.safe_type_text("ñ")
        self.assertFalse(result.ok)
        paste.assert_not_called()
        copy.assert_not_called()

    def test_focus_change_between_validation_and_typing_is_refused(self):
        original = focused_edit()
        changed = focused_edit(process_id=999, runtime_id=(9, 9, 9), process_name="other.exe")
        with (
            patch.object(safe_text_entry, "_PYAUTOGUI", True),
            patch.object(safe_text_entry, "_actual_os", return_value="windows"),
            patch.object(safe_text_entry, "_windows_focused_element_info", side_effect=[original, changed]),
            patch.object(safe_text_entry, "_write_windows_unicode") as write,
        ):
            result = safe_text_entry.safe_type_text("texto")
        self.assertFalse(result.ok)
        self.assertIn("foco cambió", result.message)
        write.assert_not_called()

    def test_target_disappears_during_operation_stops_typing(self):
        info = focused_edit()
        with (
            patch.object(safe_text_entry, "_PYAUTOGUI", True),
            patch.object(safe_text_entry, "_actual_os", return_value="windows"),
            patch.object(safe_text_entry, "_windows_focused_element_info", side_effect=[info, info]),
            patch.object(
                safe_text_entry,
                "_write_windows_unicode",
                return_value=(False, "El foco cambió o el campo desapareció."),
            ),
        ):
            result = safe_text_entry.safe_type_text("texto")
        self.assertFalse(result.ok)
        self.assertIn("desapareció", result.message)

    def test_failed_readback_does_not_fabricate_success(self):
        result, _write = safe_type_with_readback("nuevo", before="original", after="original")
        self.assertFalse(result.ok)
        self.assertIn("no pude verificar", result.message)

    def test_repeated_calls_send_each_text_once_without_internal_duplication(self):
        first, first_write = safe_type_with_readback("uno")
        second, second_write = safe_type_with_readback("dos")
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        first_write.assert_called_once()
        second_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
