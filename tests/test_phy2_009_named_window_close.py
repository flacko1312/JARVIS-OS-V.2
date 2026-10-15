import unittest
from unittest.mock import MagicMock, patch

import main
from actions import computer_settings
from actions import windows_window_control as window_control


def window(
    hwnd: int,
    title: str,
    process: str,
    class_name: str = "WindowClass",
    process_id: int | None = None,
) -> window_control.WindowInfo:
    return window_control.WindowInfo(
        hwnd=hwnd,
        title=title,
        class_name=class_name,
        process_id=process_id or hwnd + 1000,
        process_name=process,
    )


def successful_close(requested: str, initial_windows: list[window_control.WindowInfo]):
    enumerations = iter((initial_windows, []))
    closed: list[int] = []

    def post(hwnd: int) -> bool:
        closed.append(hwnd)
        return True

    result = window_control.close_named_window(
        requested,
        enumerate_fn=lambda: next(enumerations),
        post_close_fn=post,
        exists_fn=lambda hwnd: hwnd not in closed,
        foreground_fn=lambda: 999,
        timeout_seconds=0,
        poll_interval=0,
    )
    return result, closed


class NamedWindowResolverTests(unittest.TestCase):
    def test_windows_11_notepad_title_sin_titulo_matches_by_process(self):
        notepad = window(10, "Sin título", "Notepad.exe", "ApplicationFrameWindow")
        display, matches = window_control.matching_windows("Bloc de notas", [notepad])
        self.assertEqual(display, "Bloc de notas")
        self.assertEqual(matches, [notepad])

    def test_named_notepad_close_succeeds_and_targets_its_hwnd(self):
        notepad = window(10, "Sin título", "Notepad.exe")
        result, closed = successful_close("Bloc de notas", [notepad])
        self.assertEqual(result, "Cerrado: Bloc de notas.")
        self.assertEqual(closed, [10])

    def test_full_spanish_command_extracts_named_notepad_target(self):
        notepad = window(10, "Sin título", "Notepad.exe")
        result, closed = successful_close("Cierra el Bloc de notas.", [notepad])
        self.assertEqual(result, "Cerrado: Bloc de notas.")
        self.assertEqual(closed, [10])

    def test_success_requires_post_close_verification(self):
        notepad = window(10, "Sin título", "Notepad.exe")
        result = window_control.close_named_window(
            "Bloc de notas",
            enumerate_fn=lambda: [notepad],
            post_close_fn=lambda _hwnd: True,
            exists_fn=lambda _hwnd: True,
            timeout_seconds=0,
            poll_interval=0,
        )
        self.assertEqual(result, "No he podido cerrar Bloc de notas.")

    def test_close_message_rejected_returns_failure(self):
        notepad = window(10, "Sin título", "Notepad.exe")
        result = window_control.close_named_window(
            "Bloc de notas",
            enumerate_fn=lambda: [notepad],
            post_close_fn=lambda _hwnd: False,
            exists_fn=lambda _hwnd: True,
            timeout_seconds=0,
        )
        self.assertEqual(result, "No he podido cerrar Bloc de notas.")

    def test_already_closed_is_verified_from_current_enumeration(self):
        result = window_control.close_named_window(
            "Bloc de notas",
            enumerate_fn=lambda: [],
        )
        self.assertEqual(result, "No hay ninguna ventana abierta de Bloc de notas.")

    def test_unrelated_foreground_chrome_is_not_closed(self):
        chrome = window(20, "JARVIS audit - Google Chrome", "chrome.exe")
        notepad = window(10, "Sin título", "Notepad.exe")
        foreground = MagicMock(return_value=chrome.hwnd)
        enumerations = iter(([chrome, notepad], [chrome]))
        closed: list[int] = []
        result = window_control.close_named_window(
            "Bloc de notas",
            enumerate_fn=lambda: next(enumerations),
            post_close_fn=lambda hwnd: closed.append(hwnd) or True,
            exists_fn=lambda hwnd: hwnd not in closed,
            foreground_fn=foreground,
            timeout_seconds=0,
        )
        self.assertEqual(result, "Cerrado: Bloc de notas.")
        self.assertEqual(closed, [notepad.hwnd])
        foreground.assert_not_called()

    def test_named_spotify_target(self):
        spotify = window(30, "Spotify Premium", "Spotify.exe")
        result, closed = successful_close("Spotify", [spotify])
        self.assertEqual(result, "Cerrado: Spotify.")
        self.assertEqual(closed, [30])

    def test_multiple_matching_windows_requests_clarification(self):
        windows = [
            window(10, "Sin título", "Notepad.exe"),
            window(11, "notas.txt", "Notepad.exe"),
        ]
        post = MagicMock()
        result = window_control.close_named_window(
            "Bloc de notas",
            enumerate_fn=lambda: windows,
            post_close_fn=post,
        )
        self.assertIn("varias ventanas", result)
        post.assert_not_called()

    def test_unknown_target_with_no_match_is_truthful(self):
        result = window_control.close_named_window(
            "Aplicación inexistente",
            enumerate_fn=lambda: [window(20, "Chrome", "chrome.exe")],
        )
        self.assertEqual(
            result,
            "No hay ninguna ventana abierta de Aplicación inexistente.",
        )

    def test_protected_jarvis_window_is_never_closed(self):
        post = MagicMock()
        result = window_control.close_named_window(
            "JARVIS",
            enumerate_fn=lambda: [window(40, "JARVIS", "jarvis.exe")],
            post_close_fn=post,
        )
        self.assertIn("protegida", result)
        post.assert_not_called()

    def test_unicode_accented_application_name_matches(self):
        music = window(50, "Música – Reproductor", "player.exe")
        result, closed = successful_close("Música", [music])
        self.assertEqual(result, "Cerrado: Música.")
        self.assertEqual(closed, [50])

    def test_repeated_close_does_not_repeat_false_success(self):
        notepad = window(10, "Sin título", "Notepad.exe")
        first, _closed = successful_close("Bloc de notas", [notepad])
        second = window_control.close_named_window("Bloc de notas", enumerate_fn=lambda: [])
        self.assertEqual(first, "Cerrado: Bloc de notas.")
        self.assertEqual(second, "No hay ninguna ventana abierta de Bloc de notas.")

    def test_foreground_after_other_focus_is_not_authority(self):
        spotify = window(30, "Spotify", "Spotify.exe")
        notepad = window(10, "Sin título", "Notepad.exe")
        enumerations = iter(([spotify, notepad], [spotify]))
        closed: list[int] = []
        result = window_control.close_named_window(
            "Bloc de notas",
            enumerate_fn=lambda: next(enumerations),
            post_close_fn=lambda hwnd: closed.append(hwnd) or True,
            exists_fn=lambda hwnd: hwnd not in closed,
            foreground_fn=lambda: spotify.hwnd,
            timeout_seconds=0,
        )
        self.assertEqual(result, "Cerrado: Bloc de notas.")
        self.assertEqual(closed, [notepad.hwnd])

    def test_process_identity_wins_over_unrelated_title(self):
        chrome = window(20, "Bloc de notas - búsqueda", "chrome.exe")
        notepad = window(10, "Sin título", "Notepad.exe")
        _display, matches = window_control.matching_windows("Bloc de notas", [chrome, notepad])
        self.assertEqual(matches, [notepad])


class CloseWindowDispatchTests(unittest.TestCase):
    def test_notepad_request_never_uses_browser_tab_hotkey(self):
        with (
            patch.object(computer_settings, "_PYAUTOGUI", True),
            patch.object(computer_settings, "_OS", "Windows"),
            patch.object(computer_settings, "close_named_window", return_value="Cerrado: Bloc de notas.") as close,
            patch.object(computer_settings.pyautogui, "hotkey") as hotkey,
        ):
            result = computer_settings.computer_settings({
                "action": "close_window",
                "app_name": "Bloc de notas",
            })
        self.assertEqual(result, "Cerrado: Bloc de notas.")
        close.assert_called_once_with("Bloc de notas")
        hotkey.assert_not_called()

    def test_close_tab_remains_a_distinct_browser_action(self):
        with (
            patch.object(computer_settings, "_PYAUTOGUI", True),
            patch.object(computer_settings, "_OS", "Windows"),
            patch.object(computer_settings, "close_named_window") as close,
            patch.object(computer_settings.pyautogui, "hotkey") as hotkey,
        ):
            result = computer_settings.computer_settings({"action": "close_tab"})
        self.assertEqual(result, "Done: close_tab.")
        hotkey.assert_called_once_with("ctrl", "w")
        close.assert_not_called()

    def test_natural_description_extracts_notepad_name(self):
        with (
            patch.object(computer_settings, "_PYAUTOGUI", True),
            patch.object(computer_settings, "_OS", "Windows"),
            patch.object(computer_settings, "close_named_window", return_value="Cerrado: Bloc de notas.") as close,
        ):
            computer_settings.computer_settings({
                "action": "close_window",
                "description": "Cierra el Bloc de notas.",
            })
        close.assert_called_once_with("Cierra el Bloc de notas.")

    def test_tool_contract_exposes_named_app_and_tab_distinction(self):
        declaration = next(
            item for item in main.get_tool_declarations()
            if item["name"] == "computer_settings"
        )
        properties = declaration["parameters"]["properties"]
        self.assertIn("app_name", properties)
        self.assertIn("close_tab", properties["action"]["description"])
        self.assertIn("close_window", properties["action"]["description"])

    def test_spoken_response_policy_requires_verified_tool_success(self):
        self.assertIn("única autoridad", main.TOOL_RESULT_TRUTH_RULE)
        self.assertIn("Solo confirma el cierre", main.TOOL_RESULT_TRUTH_RULE)


if __name__ == "__main__":
    unittest.main()
