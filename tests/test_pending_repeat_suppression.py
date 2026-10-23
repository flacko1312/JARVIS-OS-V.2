import main


def make_live():
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis._pending_unanswered_input_key = ""
    jarvis._pending_unanswered_input_text = ""
    jarvis._pending_unanswered_live_turn_id = ""
    return jarvis


def test_repeat_key_ignores_accents_punctuation_and_stt_spacing():
    assert main._pending_repeat_key("¿Puedes oírme?") == main._pending_repeat_key("pu e des oir me")


def test_same_question_is_repeat_while_previous_turn_has_no_answer():
    jarvis = make_live()
    jarvis._track_pending_user_input("¿Puedes oírme?", "turn-1")
    assert jarvis._is_unanswered_repeat("pu e des oír me", "turn-2")


def test_same_question_is_not_suppressed_inside_same_live_turn():
    jarvis = make_live()
    jarvis._track_pending_user_input("¿Puedes oírme?", "turn-1")
    assert not jarvis._is_unanswered_repeat("¿Puedes oírme?", "turn-1")


def test_same_question_is_not_suppressed_after_answer_has_started():
    jarvis = make_live()
    jarvis._track_pending_user_input("¿Puedes oírme?", "turn-1")
    jarvis._mark_assistant_response_started()
    assert not jarvis._is_unanswered_repeat("¿Puedes oírme?", "turn-2")


def test_different_followup_is_never_absorbed():
    jarvis = make_live()
    jarvis._track_pending_user_input("¿Puedes oírme?", "turn-1")
    assert not jarvis._is_unanswered_repeat("¿Qué hora es?", "turn-2")


def test_short_acknowledgements_are_not_collapsed():
    jarvis = make_live()
    jarvis._track_pending_user_input("sí", "turn-1")
    assert not jarvis._is_unanswered_repeat("sí", "turn-2")


def test_repeated_command_is_absorbed_until_first_response_starts():
    jarvis = make_live()
    jarvis._track_pending_user_input("Abre Spotify", "turn-1")
    assert jarvis._is_unanswered_repeat("abre spotify", "turn-2")
    jarvis._mark_assistant_response_started()
    assert not jarvis._is_unanswered_repeat("abre spotify", "turn-3")


def test_new_distinct_pending_turn_replaces_previous_pending_key():
    jarvis = make_live()
    jarvis._track_pending_user_input("¿Puedes oírme?", "turn-1")
    jarvis._track_pending_user_input("¿Qué hora es?", "turn-2")
    assert not jarvis._is_unanswered_repeat("¿Puedes oírme?", "turn-3")
    assert jarvis._is_unanswered_repeat("¿Qué hora es?", "turn-3")
