import main


def test_merge_transcript_dedupes_punctuation_only_repeat():
    first = "El texto Hola que tal ha sido escrito en el Bloc de notas, flako."
    repeat = "El texto: Hola que tal ha sido escrito en el Bloc de notas flako"
    merged = main._merge_transcript_text(first, repeat)
    assert merged.count("El texto") == 1


def test_merge_transcript_keeps_distinct_followup():
    first = "Texto escrito correctamente."
    second = "La ventana sigue abierta."
    assert main._merge_transcript_text(first, second) == first + " " + second


def test_input_transcript_preserves_provider_word_boundaries():
    current = ""
    for chunk in ("Ex", "plí", "ca", "me", " la", " di", "ferencia"):
        current = main._merge_input_transcript_text(current, chunk)
    assert current == "Explícame la diferencia"


def test_input_transcript_accepts_cumulative_provider_correction():
    current = main._merge_input_transcript_text("", "Explícame")
    current = main._merge_input_transcript_text(current, "Explícame la diferencia")
    assert current == "Explícame la diferencia"


def test_input_transcript_attaches_punctuation_without_fake_space():
    current = main._merge_input_transcript_text("Hola", ",")
    current = main._merge_input_transcript_text(current, " flako")
    assert current == "Hola, flako"


def test_prompt_forbids_duplicate_tool_confirmation_and_save_as_for_select_all():
    prompt = open(r"C:\JARVIS\core\prompt.txt", encoding="utf-8").read().casefold()
    assert "exactly one brief confirmation sentence" in prompt
    assert "selecciona todo" in prompt
    assert "ctrl+shift+s" in prompt


def test_subtitle_delta_drops_identical_provider_chunk():
    text = "Notas rápidas abierto, flako."
    assert main._subtitle_delta(text, text, text) == ""


def test_subtitle_delta_keeps_only_new_suffix_from_cumulative_chunk():
    previous = "Notas rápidas abierto, flako."
    merged = previous + " Todo correcto."
    assert main._subtitle_delta(previous, merged, merged) == "Todo correcto."


def test_subtitle_delta_keeps_distinct_new_chunk():
    previous = "Aplicación abierta."
    raw = "Ventana lista."
    merged = main._merge_transcript_text(previous, raw)
    assert main._subtitle_delta(previous, merged, raw) == raw
