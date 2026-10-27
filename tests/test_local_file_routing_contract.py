from pathlib import Path

import main


def _tool(name: str) -> dict:
    return next(item for item in main.TOOL_DECLARATIONS if item.get("name") == name)


def test_prompt_routes_local_file_content_to_file_processor():
    prompt = (Path(__file__).resolve().parents[1] / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert "file_processor: use for local Windows files" in prompt
    assert "Do NOT route local Windows files to lilith_docs_*" in prompt


def test_file_processor_declares_local_windows_files():
    description = _tool("file_processor")["description"]
    assert "local Windows files" in description
    assert "C:\\JARVIS\\README.md" in description
    assert "lilith_docs_*" in description


def test_lilith_docs_read_excludes_ordinary_local_windows_files():
    description = _tool("lilith_docs_read")["description"]
    assert "LILITH/Ubuntu integration server" in description
    assert "never use this for ordinary local Windows files" in description


def test_voice_router_recognizes_readme_aliases():
    for phrase in (
        "Explícame el README de JARVIS Windows",
        "Explícame el readmi de Jarvis Windows",
        "Explícame el Realme de Harvick Windows",
    ):
        request = main._local_file_request_from_text(phrase)
        assert request == {"file_path": "README.md", "action": "explain", "save": False}


def test_voice_router_recognizes_explicit_windows_path():
    request = main._local_file_request_from_text(
        r"Explícame el archivo C:\JARVIS\README.md"
    )
    assert request == {"file_path": r"C:\JARVIS\README.md", "action": "explain", "save": False}


def test_voice_router_recognizes_spoken_filename_extension():
    request = main._local_file_request_from_text(
        "Explícame el archivo prompt punto txt de JARVIS"
    )
    assert request == {"file_path": "prompt.txt", "action": "explain", "save": False}


def test_provider_denial_recovers_named_local_file():
    request = main._local_file_recovery_from_denial(
        "Lamento no poder acceder a un archivo `prompt.txt` de JARVIS, flako."
    )
    assert request == {"file_path": "prompt.txt", "action": "explain", "save": False}


def test_provider_denial_recovery_does_not_hijack_normal_answers():
    assert main._local_file_recovery_from_denial("El archivo prompt.txt contiene reglas.") is None
    assert main._local_file_recovery_from_denial("No puedo acceder a Internet ahora.") is None


def test_voice_router_does_not_hijack_non_file_questions():
    assert main._local_file_request_from_text("Explícame qué es un agujero negro") is None
    assert main._local_file_request_from_text("Busca en tu memoria local el README") is None
