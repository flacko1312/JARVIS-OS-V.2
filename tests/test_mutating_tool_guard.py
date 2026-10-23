from types import SimpleNamespace

import main


def make_live(text: str, source: str = "voice", turn: str = "test:1"):
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis._schedule_turn_id = turn
    jarvis._schedule_turn_source = source
    jarvis._current_input_transcript = text
    jarvis._mutating_turn_effects = set()
    return jarvis


def call(call_id: str, name: str, **args):
    return SimpleNamespace(id=call_id, name=name, args=args)


def test_explicit_voice_open_is_allowed():
    jarvis = make_live("Ab re Notas rápidas.")
    result = jarvis._mutating_tool_guard_reason(
        call("a", "open_app", app_name="Notas rápidas")
    )
    assert result is None


def test_bare_app_name_from_voice_cannot_open_app():
    jarvis = make_live("Notas rápidas.")
    result = jarvis._mutating_tool_guard_reason(
        call("a", "open_app", app_name="Notas rápidas")
    )
    assert "Apertura ignorada" in result
    assert jarvis._mutating_turn_effects == set()


def test_noise_only_voice_cannot_mutate():
    jarvis = make_live(".")
    result = jarvis._mutating_tool_guard_reason(
        call("a", "computer_settings", action="close_window", app_name="Spotify")
    )
    assert "entrada de voz" in result
    assert jarvis._mutating_turn_effects == set()


def test_exact_same_effect_is_blocked_inside_same_turn_even_with_new_call_id():
    jarvis = make_live("Abre Notas rápidas.")
    first = jarvis._mutating_tool_guard_reason(
        call("a", "open_app", app_name="Notas rápidas")
    )
    second = jarvis._mutating_tool_guard_reason(
        call("b", "open_app", app_name="NOTAS RAPIDAS")
    )
    assert first is None
    assert "duplicada" in second


def test_same_effect_is_allowed_on_a_new_user_turn():
    jarvis = make_live("Abre Notas rápidas.", turn="test:1")
    assert jarvis._mutating_tool_guard_reason(
        call("a", "open_app", app_name="Notas rápidas")
    ) is None
    jarvis._schedule_turn_id = "test:2"
    jarvis._current_input_transcript = "Abre Notas rápidas."
    assert jarvis._mutating_tool_guard_reason(
        call("b", "open_app", app_name="Notas rápidas")
    ) is None


def test_two_different_effects_in_same_turn_are_allowed():
    jarvis = make_live("Abre Spotify y ciérralo.")
    assert jarvis._mutating_tool_guard_reason(
        call("a", "open_app", app_name="Spotify")
    ) is None
    assert jarvis._mutating_tool_guard_reason(
        call("b", "computer_settings", action="close_window", app_name="Spotify")
    ) is None


def test_computer_settings_description_does_not_evade_duplicate_guard():
    jarvis = make_live("Cierra Spotify.")
    first = jarvis._mutating_tool_guard_reason(
        call("a", "computer_settings", action="close_window", app_name="Spotify")
    )
    second = jarvis._mutating_tool_guard_reason(
        call(
            "b",
            "computer_settings",
            action="close_window",
            app_name="Spotify",
            description="Cerrar la ventana de Spotify",
        )
    )
    assert first is None
    assert "duplicada" in second


def test_active_voice_turn_binds_any_model_tool_to_current_user_turn():
    jarvis = make_live("Busca el tiempo de respuesta.")
    jarvis._tool_turn_active = True
    jarvis._active_tool_turn_id = "test:1"
    assert jarvis._tool_turn_binding_guard_reason(
        call("a", "web_search", query="tiempo de respuesta")
    ) is None


def test_tool_after_completed_voice_turn_is_blocked_even_if_old_transcript_remains():
    jarvis = make_live("Busca el tiempo de respuesta.")
    jarvis._tool_turn_active = False
    jarvis._active_tool_turn_id = ""
    result = jarvis._tool_turn_binding_guard_reason(
        call("late", "web_search", query="consulta fantasma")
    )
    assert "orden activa" in result


def test_tool_with_stale_turn_binding_is_blocked():
    jarvis = make_live("Abre Spotify.", turn="test:2")
    jarvis._tool_turn_active = True
    jarvis._active_tool_turn_id = "test:1"
    result = jarvis._tool_turn_binding_guard_reason(
        call("stale", "open_app", app_name="Spotify")
    )
    assert "orden activa" in result


def test_end_active_tool_turn_revokes_authority_without_delay():
    jarvis = make_live("Abre Spotify.")
    jarvis._tool_turn_active = True
    jarvis._active_tool_turn_id = "test:1"
    jarvis._end_active_tool_turn()
    assert jarvis._tool_turn_active is False
    assert jarvis._active_tool_turn_id == ""


def test_live_vad_silence_window_is_configurable_and_bounded():
    import os
    expected = max(250, min(3000, int(os.environ.get("JARVIS_LIVE_VAD_SILENCE_MS", "1000"))))
    assert main.LIVE_VAD_SILENCE_MS == expected
    assert 250 <= main.LIVE_VAD_SILENCE_MS <= 3000
