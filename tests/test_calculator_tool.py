from actions.calculator import calculate


def test_basic_arithmetic():
    assert calculate("88*2") == "Resultado: 176"


def test_spanish_arithmetic():
    assert calculate("88 por 2") == "Resultado: 176"
    assert calculate("10 más 5 entre 3") == "Resultado: 11.666666666667"


def test_percentage():
    assert calculate("20% de 50") == "Resultado: 10"
    assert calculate("20 por ciento de 50") == "Resultado: 10"


def test_parentheses_and_power():
    assert calculate("(5+3)^2") == "Resultado: 64"


def test_division_by_zero_is_safe():
    assert calculate("10/0") == "No se puede dividir entre cero."


def test_code_execution_is_rejected():
    result = calculate("__import__('os').system('echo nope')")
    assert result.startswith("No he podido calcular esa operación:")


import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

import main


class _UI:
    def __init__(self):
        self.states = []
        self.logs = []
        self.muted = False
        self.on_text_command = None
        self.on_conversation_toggle = None
        self.operational_ready = True

    def set_state(self, state):
        self.states.append(state)

    def write_log(self, text):
        self.logs.append(text)

    def clear_subtitle(self):
        pass

    def show_subtitle(self, _text):
        pass

    def sync_voice_display(self, _voice):
        pass


def test_calculator_is_declared_for_gemini_live():
    declaration = next(item for item in main.TOOL_DECLARATIONS if item.get("name") == "calculator")
    assert declaration["parameters"]["required"] == ["expression"]
    assert "instead of opening the Windows Calculator" in declaration["description"]


def test_live_tool_execution_returns_real_result():
    with tempfile.TemporaryDirectory() as tmp:
        jarvis = main.JarvisLive(
            _UI(), api_key="test", external_audio=True,
            conversation_store_path=Path(tmp) / "conversation_state.json",
        )
        call = SimpleNamespace(id="calc-1", name="calculator", args={"expression": "88 por 2"})
        response = asyncio.run(jarvis._execute_tool(call))
    assert response.response["result"] == "Resultado: 176"
