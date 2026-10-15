import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from actions import file_processor, open_app


def test_unknown_text_action_preserves_original_instruction(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("source body", encoding="utf-8")
    with patch.object(file_processor, "_generate_content", return_value="done") as generate:
        assert file_processor._process_text_doc(source, "txt", "make it friendlier", {}) == "done"
    prompt = generate.call_args.args[0][0]
    assert prompt.startswith("make it friendlier\n\n")
    assert "custom\n\n" not in prompt


def test_explicit_custom_instruction_is_preserved(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("source body", encoding="utf-8")
    with patch.object(file_processor, "_generate_content", return_value="done") as generate:
        file_processor._process_text_doc(source, "txt", "custom", {"instruction": "Hazlo breve"})
    assert generate.call_args.args[0][0].startswith("Hazlo breve\n\n")


def test_unicode_launcher_uses_clipboard_and_restores_it():
    gui = MagicMock()
    clipboard = MagicMock()
    clipboard.paste.return_value = "original"
    with patch.dict("sys.modules", {"pyautogui": gui, "pyperclip": clipboard}):
        open_app._type_launcher_text("Música")
    assert clipboard.copy.call_args_list[0].args == ("Música",)
    assert clipboard.copy.call_args_list[-1].args == ("original",)
    gui.hotkey.assert_called_once_with("ctrl", "v")
    gui.write.assert_not_called()


def test_ascii_launcher_keeps_direct_typing():
    gui = MagicMock()
    with patch.dict("sys.modules", {"pyautogui": gui}):
        open_app._type_launcher_text("Spotify")
    gui.write.assert_called_once_with("Spotify", interval=0.05)


def test_ui_locale_literal_has_no_duplicate_keys():
    source = Path(__file__).resolve().parents[1] / "ui_locale.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    assignment = next(
        node for node in module.body
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "UI_TEXT"
    )
    keys = [key.value for key in assignment.value.keys]
    assert len(keys) == len(set(keys))
