from unittest.mock import MagicMock, patch

from actions import computer_control as cc


def test_copy_sends_ctrl_c_to_current_selection():
    with patch.object(cc, "_hotkey") as hotkey, patch.object(cc.time, "sleep"):
        result = cc.computer_control({"action": "copy"})
    hotkey.assert_called_once_with("ctrl", "c")
    assert "Copied current selection" in result


def test_paste_without_text_uses_real_ctrl_v_after_target_validation():
    before = MagicMock(ok=True, target_id=(1, 2, 3))
    after = MagicMock(ok=True, target_id=(1, 2, 3))
    with (
        patch.object(cc, "_PYPERCLIP", True),
        patch.object(cc.pyperclip, "paste", return_value="texto del portapapeles"),
        patch("actions.safe_text_entry.validate_safe_text_target", side_effect=[before, after]),
        patch.object(cc, "_hotkey") as hotkey,
        patch.object(cc.time, "sleep"),
    ):
        result = cc.computer_control({"action": "paste"})
    hotkey.assert_called_once_with("ctrl", "v")
    assert "pegado" in result.lower()


def test_paste_refuses_if_focus_changes_after_ctrl_v():
    before = MagicMock(ok=True, target_id=(1, 2, 3))
    after = MagicMock(ok=True, target_id=(9, 9, 9))
    with (
        patch.object(cc, "_PYPERCLIP", True),
        patch.object(cc.pyperclip, "paste", return_value="texto"),
        patch("actions.safe_text_entry.validate_safe_text_target", side_effect=[before, after]),
        patch.object(cc, "_hotkey"),
        patch.object(cc.time, "sleep"),
    ):
        result = cc.computer_control({"action": "paste"})
    assert "foco cambió" in result


def test_paste_explicit_text_still_uses_safe_text_entry():
    safe = MagicMock(ok=True, message="ok")
    with patch.object(cc, "safe_type_text", return_value=safe) as safe_type:
        result = cc.computer_control({"action": "paste", "text": "texto explícito"})
    safe_type.assert_called_once_with("texto explícito", purpose="generic")
    assert "pegado" in result.lower()


def test_empty_clipboard_is_refused_cleanly():
    with patch.object(cc, "_PYPERCLIP", True), patch.object(cc.pyperclip, "paste", return_value=""):
        result = cc.computer_control({"action": "paste"})
    assert "portapapeles de texto" in result.lower()


def test_select_all_uses_only_ctrl_a_on_verified_text_target():
    resolved = MagicMock(ok=True, message="ok")
    with (
        patch("actions.safe_text_entry._resolve_windows_target", return_value=(resolved, {"process_id": 1})),
        patch.object(cc, "_hotkey") as hotkey,
    ):
        result = cc.computer_control({"action": "select_all"})
    hotkey.assert_called_once_with("ctrl", "a")
    assert "seleccionado" in result.lower()


def test_select_all_refuses_unverified_target_without_hotkey():
    bad = MagicMock(ok=False, message="No hay campo de texto verificado.")
    with (
        patch("actions.safe_text_entry._resolve_windows_target", return_value=(bad, {})),
        patch.object(cc, "_hotkey") as hotkey,
    ):
        result = cc.computer_control({"action": "select_all"})
    hotkey.assert_not_called()
    assert "verificado" in result.lower()
