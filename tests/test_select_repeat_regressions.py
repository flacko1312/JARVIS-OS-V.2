from unittest.mock import patch

from actions import computer_control as cc
from actions.safe_text_entry import SafeTextEntryResult
import main


def test_select_all_delegates_to_safe_select_all_text():
    ok_result = SafeTextEntryResult(ok=True, message="Texto seleccionado mediante Windows UI Automation.")
    with patch("actions.computer_control.safe_select_all_text", return_value=ok_result):
        result = cc.computer_control({"action": "select_all"})
    assert "seleccionado" in result.lower()


def test_select_all_refuses_when_safe_select_all_fails():
    fail_result = SafeTextEntryResult(ok=False, message="sin destino")
    with patch("actions.computer_control.safe_select_all_text", return_value=fail_result):
        result = cc.computer_control({"action": "select_all"})
    assert result == "sin destino"


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
