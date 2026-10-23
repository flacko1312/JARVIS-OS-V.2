from types import SimpleNamespace
from unittest.mock import patch

from actions import computer_control as cc
import main


def test_select_all_uses_resolved_safe_target_and_ctrl_a_once():
    validation = SimpleNamespace(ok=True, message="ok")
    with (
        patch("actions.safe_text_entry._resolve_windows_target", return_value=(validation, {"process_id": 1})),
        patch.object(cc, "_hotkey") as hotkey,
    ):
        result = cc.computer_control({"action": "select_all"})
    hotkey.assert_called_once_with("ctrl", "a")
    assert "seleccionado" in result.lower()


def test_select_all_refuses_when_safe_target_cannot_be_resolved():
    validation = SimpleNamespace(ok=False, message="sin destino")
    with (
        patch("actions.safe_text_entry._resolve_windows_target", return_value=(validation, {})),
        patch.object(cc, "_hotkey") as hotkey,
    ):
        result = cc.computer_control({"action": "select_all"})
    assert result == "sin destino"
    hotkey.assert_not_called()


def test_duplicate_confirmation_inside_single_live_chunk_collapses():
    sentence = 'El texto "Hola, ¿qué tal?" ha sido escrito en el Bloc de notas, flako.'
    assert main._dedupe_repeated_output(f"{sentence} {sentence}") == sentence


def test_computer_control_success_is_reduced_to_one_exact_confirmation():
    assert main._tool_result_for_model(
        "computer_control", {"action": "type"}, "Typed safely: texto escrito"
    ) == "Hecho."


def test_computer_control_failure_is_not_hidden():
    failure = "El foco cambió durante la selección; no puedo confirmar el destino."
    assert main._tool_result_for_model("computer_control", {"action": "select_all"}, failure) == failure
