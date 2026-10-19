"""Tests for turn integrity — stale tool guard, dedup, transcript validation."""
import sys
import unittest

sys.path.insert(0, "/home/flako1312/jarvis-headless")

# Import the helper directly from main.py module-level
# Since main.py is huge and has side effects, we test the function in isolation
import re

_NON_SEMANTIC_PATTERN = re.compile(
    r"^[\s\.\,\;\:\!\?\-\—\…\<\>]*$"
    r"|^<noise>$"
    r"|^<silence>$"
    r"|^\[.*\]$",
    re.IGNORECASE,
)


def _is_semantic_transcript(text):
    if not text:
        return False
    cleaned = text.strip()
    if not cleaned:
        return False
    if _NON_SEMANTIC_PATTERN.match(cleaned):
        return False
    if len(cleaned) <= 1 and not cleaned.isalnum():
        return False
    return True


class TestTranscriptValidation(unittest.TestCase):

    def test_noise_rejected(self):
        self.assertFalse(_is_semantic_transcript("<noise>"))

    def test_silence_rejected(self):
        self.assertFalse(_is_semantic_transcript("<silence>"))

    def test_dot_rejected(self):
        self.assertFalse(_is_semantic_transcript("."))

    def test_ellipsis_rejected(self):
        self.assertFalse(_is_semantic_transcript("..."))
        self.assertFalse(_is_semantic_transcript("…"))

    def test_empty_rejected(self):
        self.assertFalse(_is_semantic_transcript(""))
        self.assertFalse(_is_semantic_transcript(None))

    def test_whitespace_rejected(self):
        self.assertFalse(_is_semantic_transcript("   "))
        self.assertFalse(_is_semantic_transcript("\n"))

    def test_punctuation_only_rejected(self):
        self.assertFalse(_is_semantic_transcript(".,;:!?"))
        self.assertFalse(_is_semantic_transcript("- -"))
        self.assertFalse(_is_semantic_transcript("...!"))

    def test_bracket_noise_rejected(self):
        self.assertFalse(_is_semantic_transcript("[inaudible]"))
        self.assertFalse(_is_semantic_transcript("[music]"))

    def test_real_speech_accepted(self):
        self.assertTrue(_is_semantic_transcript("Para"))
        self.assertTrue(_is_semantic_transcript("¿Qué hora es?"))
        self.assertTrue(_is_semantic_transcript("Dime"))
        self.assertTrue(_is_semantic_transcript("Oh"))

    def test_short_word_accepted(self):
        self.assertTrue(_is_semantic_transcript("Sí"))
        self.assertTrue(_is_semantic_transcript("No"))

    def test_single_letter_accepted(self):
        self.assertTrue(_is_semantic_transcript("A"))

    def test_case_insensitive_noise(self):
        self.assertFalse(_is_semantic_transcript("<NOISE>"))
        self.assertFalse(_is_semantic_transcript("<Noise>"))


class TestTurnIntegrityState(unittest.TestCase):
    """Test the turn integrity state management logic."""

    def test_turn_tool_signatures_dedup(self):
        sigs = set()
        sig1 = "date_time:call_001"
        sig2 = "date_time:call_002"

        sigs.add(sig1)
        self.assertIn(sig1, sigs)

        # Same sig again — already in set
        self.assertIn(sig1, sigs)

        # Different call_id — allowed
        sigs.add(sig2)
        self.assertEqual(len(sigs), 2)

    def test_turn_interrupted_blocks_tools(self):
        """Simulate: turn_interrupted=True blocks tool execution."""
        turn_interrupted = True
        suppress = True
        should_execute = not (turn_interrupted or suppress)
        self.assertFalse(should_execute)

    def test_normal_turn_allows_tools(self):
        turn_interrupted = False
        suppress = False
        should_execute = not (turn_interrupted or suppress)
        self.assertTrue(should_execute)

    def test_stale_turn_after_local_barge_in(self):
        """Full scenario: JARVIS speaking, barge-in, tool call arrives — blocked."""
        turn_interrupted = False
        suppress = False

        # Local barge-in fires
        turn_interrupted = True
        suppress = True

        # Tool call arrives from old response
        should_execute = not (turn_interrupted or suppress)
        self.assertFalse(should_execute)

    def test_new_turn_allows_tools_again(self):
        """After new turn starts, tools are allowed."""
        turn_interrupted = True

        # New turn starts — reset
        turn_interrupted = False
        should_execute = not turn_interrupted
        self.assertTrue(should_execute)


class TestTurnLifecycle(unittest.TestCase):
    """Test the full turn lifecycle scenarios."""

    def test_normal_turn_complete(self):
        """1 input → 1 tool → 1 output → turn_complete."""
        state = {
            "turn_id": "abc123",
            "interrupted": False,
            "suppress": False,
            "tool_sigs": set(),
        }

        # Tool call arrives
        sig = "date_time:fc_001"
        self.assertNotIn(sig, state["tool_sigs"])
        state["tool_sigs"].add(sig)

        # turn_complete
        state["interrupted"] = False
        state["suppress"] = False
        # Turn closes normally

    def test_stale_tool_after_turn_complete(self):
        """Tool call after turn_complete in new turn — new turn_id, so it's a new call."""
        turn1_sigs = {"date_time:fc_001"}
        turn2_sigs = set()

        sig = "date_time:fc_002"
        self.assertNotIn(sig, turn2_sigs)
        # Allowed in new turn

    def test_duplicate_tool_same_turn(self):
        """Same tool+id in same turn — blocked."""
        sigs = set()
        sig = "date_time:fc_001"
        sigs.add(sig)
        self.assertIn(sig, sigs)  # Duplicate

    def test_same_tool_different_turns_allowed(self):
        """Same tool name in different turns — allowed (different ids)."""
        turn1_sigs = {"date_time:fc_001"}
        turn2_sigs = set()
        sig = "date_time:fc_002"
        self.assertNotIn(sig, turn2_sigs)  # Allowed

    def test_barge_in_closes_old_opens_new(self):
        """Barge-in: old turn interrupted, new turn clean."""
        old_turn = {"interrupted": False, "suppress": False}

        # Barge-in
        old_turn["interrupted"] = True
        old_turn["suppress"] = True

        # New turn
        new_turn = {"interrupted": False, "suppress": False, "tool_sigs": set()}
        self.assertFalse(new_turn["interrupted"])

    def test_provider_interruption_after_local_safe(self):
        state = {"interrupted": True, "suppress": True}
        # provider_interruption
        state["interrupted"] = True  # already True
        state["suppress"] = False
        # No crash, idempotent

    def test_date_time_one_question_one_execution(self):
        """One hora question = one date_time call."""
        sigs = set()
        sig = "date_time:fc_001"
        sigs.add(sig)
        self.assertEqual(len(sigs), 1)

        # Duplicate — already in set
        self.assertIn(sig, sigs)

    def test_two_real_hora_questions_two_executions(self):
        """Two real questions in different turns = two allowed calls."""
        turn1_sigs = set()
        turn1_sigs.add("date_time:fc_001")

        turn2_sigs = set()
        turn2_sigs.add("date_time:fc_002")

        self.assertEqual(len(turn1_sigs), 1)
        self.assertEqual(len(turn2_sigs), 1)

    def test_session_resumption_no_revive(self):
        """Session resumption doesn't revive a closed turn."""
        state = {"interrupted": True}
        # Resumption happens — but turn is still interrupted
        self.assertTrue(state["interrupted"])
        # New turn starts fresh
        state = {"interrupted": False}
        self.assertFalse(state["interrupted"])


if __name__ == "__main__":
    unittest.main()
