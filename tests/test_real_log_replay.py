"""Regression tests from REAL journal log sequences (PID 2159082, 2024-10-19).

Each test class replays an actual sequence observed in production logs.
Tests verify turn integrity, void turn filtering, conversation memory
isolation, and noise tag handling.
"""
import asyncio
import re
import sys
import threading
import time
import unittest

sys.path.insert(0, "/home/flako1312/jarvis-headless")

from core.voice_stability import VoiceStabilityMonitor

# ── Module-level helpers (mirrors main.py) ──

_NON_SEMANTIC_PATTERN = re.compile(
    r"^[\s\.\,\;\:\!\?\-\—\…\<\>]*$"
    r"|^<noise>$"
    r"|^<silence>$"
    r"|^\[.*\]$",
    re.IGNORECASE,
)

_RE_NOISE_TAG = re.compile(r"<noise>|<silence>", re.IGNORECASE)


def _strip_noise_tags(text):
    if not text:
        return ""
    cleaned = _RE_NOISE_TAG.sub("", text)
    return " ".join(cleaned.split()).strip()


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


# ── Stub infrastructure (mirrors main.py behavior) ──

class FakeGate:
    def __init__(self):
        self._accepted = False

    @property
    def accepted(self):
        return self._accepted

    def start_playback(self):
        self._accepted = False

    def stop_playback(self):
        self._accepted = False


class FakeUI:
    def __init__(self):
        self.muted = False
        self._state = "LISTENING"
        self.logs = []

    def set_state(self, s):
        self._state = s

    def write_log(self, msg):
        self.logs.append(msg)


class StubJarvis:
    """Stub that mirrors the real main.py turn integrity + void turn logic."""

    def __init__(self):
        self._speaking_lock = threading.Lock()
        self._is_speaking = False
        self._barge_in_gate = FakeGate()
        self._barge_in_candidate_logged = False
        self._local_barge_in_active = False
        self._suppress_interrupted_output = False
        self._turn_interrupted = False
        self._turn_tool_signatures = set()
        self._active_turn_id = None
        self.audio_in_queue = asyncio.Queue()
        self.ui = FakeUI()

        # Conversation memory
        self._conversation_continuity = []
        self._current_input_transcript = ""
        self._last_input_transcript = ""

        # Tracking
        self._interrupt_calls = []
        self._tool_calls_executed = []
        self._tool_calls_rejected = []
        self._void_turns = []
        self._suppressed_bytes = 0

    def set_speaking(self, value):
        with self._speaking_lock:
            previous = self._is_speaking
            self._is_speaking = value
        gate = self._barge_in_gate
        if gate is not None and value != previous:
            if value:
                gate.start_playback()
                self._barge_in_candidate_logged = False
            else:
                gate.stop_playback()
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    @staticmethod
    def _drain_queue(queue):
        drained = 0
        if queue is None:
            return drained
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return drained
            else:
                drained += 1

    def _interrupt_live_playback(self, reason):
        drained = self._drain_queue(self.audio_in_queue)
        self.set_speaking(False)
        self._interrupt_calls.append({"reason": reason, "flushed": drained})
        return drained

    # ── Turn lifecycle ──

    def new_turn(self, turn_id):
        """Simulate top of receive loop."""
        self._active_turn_id = turn_id
        self._turn_interrupted = False
        self._turn_tool_signatures = set()
        self._suppress_interrupted_output = False
        self._local_barge_in_active = False

    def local_barge_in(self):
        """Simulate accepted barge-in."""
        if not self._local_barge_in_active:
            self._local_barge_in_active = True
            self._suppress_interrupted_output = True
            self._turn_interrupted = True
            self._interrupt_live_playback("local_barge_in")

    def provider_interruption(self):
        """Simulate server_content.interrupted."""
        self._interrupt_live_playback("provider_interruption")
        self._turn_interrupted = True
        self._suppress_interrupted_output = False
        self._local_barge_in_active = False

    def receive_response_audio(self, audio_bytes):
        """Simulate response_audio path."""
        if self._suppress_interrupted_output:
            self._suppressed_bytes += len(audio_bytes)
            return False
        self.audio_in_queue.put_nowait(audio_bytes)
        self.set_speaking(True)
        return True

    def dispatch_tool_call(self, name, call_id, in_buf):
        """Simulate tool_call dispatch with all guards."""
        if self._turn_interrupted or self._suppress_interrupted_output:
            self._tool_calls_rejected.append({
                "name": name, "reason": "stale_turn",
                "turn_id": self._active_turn_id,
            })
            return {"result": "Turn was interrupted; tool call discarded."}

        current_input = " ".join(in_buf).strip()
        if in_buf and not _is_semantic_transcript(current_input):
            self._tool_calls_rejected.append({
                "name": name, "reason": "non_semantic_transcript",
                "turn_id": self._active_turn_id, "text": current_input,
            })
            return {"result": "Non-semantic input; tool call skipped."}

        sig = f"{name}:{call_id}"
        if sig in self._turn_tool_signatures:
            self._tool_calls_rejected.append({
                "name": name, "reason": "duplicate_turn_call",
                "turn_id": self._active_turn_id,
            })
            return {"result": "Duplicate call in same turn; skipped."}

        self._turn_tool_signatures.add(sig)
        self._tool_calls_executed.append({
            "name": name, "call_id": call_id,
            "turn_id": self._active_turn_id,
        })
        return {"result": f"Executed {name}"}

    def turn_complete(self, in_buf, out_buf):
        """Simulate turn_complete with void turn filtering."""
        full_in = " ".join(in_buf).strip()
        clean_in = _strip_noise_tags(full_in) if full_in else ""
        is_void = bool(full_in) and not _is_semantic_transcript(clean_in)

        if is_void:
            self._void_turns.append({
                "turn_id": self._active_turn_id,
                "raw": full_in,
            })
            # Purge streaming partials
            self._conversation_continuity = [
                t for t in self._conversation_continuity
                if t.get("turn_id") != self._active_turn_id
            ]
        elif full_in:
            save_in = clean_in if clean_in != full_in else full_in
            self._current_input_transcript = save_in
            self._last_input_transcript = save_in
            self.ui.write_log(f"Tú: {save_in}")
            self._conversation_continuity.append({
                "role": "user", "text": save_in,
                "turn_id": self._active_turn_id,
            })

        full_out = " ".join(out_buf).strip()
        if full_out and not is_void:
            self.ui.write_log(f"AURORA: {full_out}")
            self._conversation_continuity.append({
                "role": "assistant", "text": full_out,
                "turn_id": self._active_turn_id,
            })

        # Reset flags
        self._suppress_interrupted_output = False
        self._local_barge_in_active = False

        return is_void


# ═══════════════════════════════════════════════════════════════
# TEST CLASSES — each replays a real log sequence
# ═══════════════════════════════════════════════════════════════


class TestRealLog_NoiseInput(unittest.TestCase):
    """Real log: 21:14:31 Tú: <noise> → AURORA responded + ghost date_time.

    Journal sequence (PID 2159082):
      BARGE_IN accepted → local_barge_in flushed=16
      provider_interruption flushed=0
      Turn complete
      Tú: <noise>
      AURORA: ¿En qué más puedo ayudarte, flako?
      date_time {'action': 'current_time', 'query': '¿qué hora es?'}
    """

    def setUp(self):
        self.j = StubJarvis()
        # JARVIS was speaking (responding to previous question)
        self.j.set_speaking(True)
        for i in range(16):
            self.j.audio_in_queue.put_nowait(b"chunk_%d" % i)

    def test_full_sequence(self):
        # Turn 1: user interrupts with noise
        self.j.new_turn("turn_noise_1")

        # Barge-in accepted
        self.j.local_barge_in()
        self.assertEqual(self.j._interrupt_calls[-1]["flushed"], 16)

        # Provider interruption follows
        self.j.provider_interruption()

        # Tool call arrives (ghost from previous question)
        result = self.j.dispatch_tool_call("date_time", "fc_ghost", ["<noise>"])
        self.assertIn("stale_turn", [r["reason"] for r in self.j._tool_calls_rejected])

        # Turn complete with <noise> input
        is_void = self.j.turn_complete(
            ["<noise>"],
            ["¿En qué más puedo ayudarte, flako?"]
        )
        self.assertTrue(is_void)

        # Conversation memory must NOT contain <noise> or the assistant response
        user_turns = [t for t in self.j._conversation_continuity if t["role"] == "user"]
        assistant_turns = [t for t in self.j._conversation_continuity if t["role"] == "assistant"]
        self.assertEqual(len(user_turns), 0)
        self.assertEqual(len(assistant_turns), 0)

    def test_noise_tool_blocked(self):
        self.j.new_turn("turn_noise_2")
        result = self.j.dispatch_tool_call("date_time", "fc_001", ["<noise>"])
        self.assertEqual(len(self.j._tool_calls_executed), 0)
        self.assertEqual(self.j._tool_calls_rejected[0]["reason"], "non_semantic_transcript")

    def test_noise_not_in_logs(self):
        self.j.new_turn("turn_noise_3")
        self.j.turn_complete(["<noise>"], ["Response to noise"])
        self.assertNotIn("Tú: <noise>", [l for l in self.j.ui.logs])
        self.assertNotIn("AURORA: Response to noise", [l for l in self.j.ui.logs])


class TestRealLog_DotInput(unittest.TestCase):
    """Real log: 21:14:36 Tú: . → AURORA: Ahora son las 21:14

    Journal sequence (PID 2159082):
      BARGE_IN rejected × several
      Turn complete
      Tú: .
      AURORA: Ahora son las 21:14
    """

    def setUp(self):
        self.j = StubJarvis()

    def test_dot_is_void_turn(self):
        self.j.new_turn("turn_dot_1")
        is_void = self.j.turn_complete(["."], ["Ahora son las 21:14"])
        self.assertTrue(is_void)
        self.assertEqual(len(self.j._conversation_continuity), 0)

    def test_dot_tool_blocked(self):
        self.j.new_turn("turn_dot_2")
        self.j.dispatch_tool_call("date_time", "fc_dot", ["."])
        self.assertEqual(len(self.j._tool_calls_executed), 0)

    def test_dot_not_saved_to_transcript(self):
        self.j.new_turn("turn_dot_3")
        self.j.turn_complete(["."], ["Some response"])
        self.assertNotEqual(self.j._current_input_transcript, ".")
        self.assertNotEqual(self.j._last_input_transcript, ".")

    def test_ellipsis_also_void(self):
        self.j.new_turn("turn_ellipsis")
        is_void = self.j.turn_complete(["..."], ["Response"])
        self.assertTrue(is_void)

    def test_punctuation_only_void(self):
        self.j.new_turn("turn_punct")
        is_void = self.j.turn_complete([".,;:!?"], ["Response"])
        self.assertTrue(is_void)


class TestRealLog_MixedNoise(unittest.TestCase):
    """Real log: Tú: <noise> Voilà. <noise> — mixed noise + real content.

    From conversation store turn [11]: user: <noise> Voilà. <noise>
    """

    def setUp(self):
        self.j = StubJarvis()

    def test_mixed_noise_is_semantic(self):
        self.j.new_turn("turn_mixed")
        is_void = self.j.turn_complete(
            ["<noise> Voilà. <noise>"],
            ["Como te he explicado..."]
        )
        self.assertFalse(is_void)

    def test_noise_tags_stripped_from_saved_text(self):
        self.j.new_turn("turn_mixed_2")
        self.j.turn_complete(
            ["<noise> Voilà. <noise>"],
            ["Response"]
        )
        user_turns = [t for t in self.j._conversation_continuity if t["role"] == "user"]
        self.assertEqual(len(user_turns), 1)
        self.assertEqual(user_turns[0]["text"], "Voilà.")
        self.assertNotIn("<noise>", user_turns[0]["text"])

    def test_noise_para_cleaned(self):
        """Real log: Tú: <noise> Para → saved as 'Para'."""
        self.j.new_turn("turn_para")
        self.j.turn_complete(["<noise> Para"], ["Disculpa, ¿qué necesitas?"])
        user_turns = [t for t in self.j._conversation_continuity if t["role"] == "user"]
        self.assertEqual(user_turns[0]["text"], "Para")

    def test_tool_allowed_for_mixed_semantic(self):
        """If real speech is embedded in noise, tool calls should proceed."""
        self.j.new_turn("turn_tool_mixed")
        result = self.j.dispatch_tool_call(
            "date_time", "fc_mix_001", ["<noise> Dime la hora <noise>"]
        )
        # _strip_noise_tags is not applied in dispatch — only in memory save
        # The raw text "<noise> Dime la hora <noise>" contains semantic content
        # _is_semantic_transcript would return True for this
        self.assertEqual(len(self.j._tool_calls_executed), 1)


class TestRealLog_BargeInSequence(unittest.TestCase):
    """Real log: 21:14:06 — full barge-in → provider_interruption → turn_complete.

    Journal (PID 2159082):
      BARGE_IN accepted speech=189ms rms=0.0211
      STATE SPEAKING -> LISTENING
      LIVE_AUDIO interrupted reason=local_barge_in flushed_chunks=271
      LIVE_AUDIO interrupted reason=provider_interruption flushed_chunks=0
      Turn complete
      Tú: Ex plí ca me qué sa bes hacer con vari os ejemplos.
      AURORA: Puedo hacer varias cosas, flako...
      date_time {'query': 'hora', 'action': 'current_time'}
    """

    def setUp(self):
        self.j = StubJarvis()
        self.j.set_speaking(True)
        for i in range(271):
            self.j.audio_in_queue.put_nowait(b"audio_%d" % i)

    def test_barge_in_cuts_271_chunks(self):
        self.j.new_turn("turn_barge_1")
        self.j.local_barge_in()
        self.assertEqual(self.j._interrupt_calls[0]["flushed"], 271)

    def test_provider_interruption_idempotent(self):
        self.j.new_turn("turn_barge_2")
        self.j.local_barge_in()
        self.j.provider_interruption()
        self.assertEqual(len(self.j._interrupt_calls), 2)
        self.assertEqual(self.j._interrupt_calls[1]["flushed"], 0)

    def test_old_response_audio_suppressed(self):
        self.j.new_turn("turn_barge_3")
        self.j.local_barge_in()
        enqueued = self.j.receive_response_audio(b"old_audio")
        self.assertFalse(enqueued)

    def test_tool_after_barge_in_blocked(self):
        """date_time from interrupted turn should be blocked."""
        self.j.new_turn("turn_barge_4")
        self.j.local_barge_in()
        self.j.dispatch_tool_call("date_time", "fc_stale", ["¿Qué hora es?"])
        self.assertEqual(len(self.j._tool_calls_executed), 0)
        self.assertEqual(self.j._tool_calls_rejected[0]["reason"], "stale_turn")

    def test_semantic_turn_saves_normally(self):
        """Real semantic input saves to conversation memory."""
        self.j.new_turn("turn_barge_5")
        self.j.local_barge_in()
        self.j.provider_interruption()
        is_void = self.j.turn_complete(
            ["Ex plí ca me qué sa bes hacer con vari os ejemplos."],
            ["Puedo hacer varias cosas, flako."]
        )
        self.assertFalse(is_void)
        user_turns = [t for t in self.j._conversation_continuity if t["role"] == "user"]
        self.assertEqual(len(user_turns), 1)


class TestRealLog_GhostToolCall(unittest.TestCase):
    """Real log: date_time tool call after <noise> turn — ghost from previous question.

    Journal (PID 2159082):
      Turn complete → Tú: <noise>
      date_time {'action': 'current_time', 'query': '¿qué hora es?'}  ← GHOST
    """

    def test_ghost_tool_after_noise_blocked(self):
        j = StubJarvis()
        # Turn 1: real question
        j.new_turn("turn_real")
        j.dispatch_tool_call("date_time", "fc_real", ["¿Qué hora es?"])
        self.assertEqual(len(j._tool_calls_executed), 1)

        # Turn 2: noise — after the interruption
        j.new_turn("turn_ghost")
        # Gemini sends a tool call with a query from the previous turn
        j.dispatch_tool_call("date_time", "fc_ghost", ["<noise>"])
        self.assertEqual(len(j._tool_calls_executed), 1)  # Still just 1
        self.assertEqual(j._tool_calls_rejected[-1]["reason"], "non_semantic_transcript")

    def test_ghost_tool_after_dot_blocked(self):
        j = StubJarvis()
        j.new_turn("turn_dot_ghost")
        j.dispatch_tool_call("date_time", "fc_dot_ghost", ["."])
        self.assertEqual(len(j._tool_calls_executed), 0)


class TestRealLog_DuplicateToolCall(unittest.TestCase):
    """Test duplicate tool call dedup within same turn.

    Scenario: Gemini sends date_time twice with same function_call_id.
    """

    def test_exact_duplicate_blocked(self):
        j = StubJarvis()
        j.new_turn("turn_dup")
        j.dispatch_tool_call("date_time", "fc_001", ["¿Qué hora es?"])
        j.dispatch_tool_call("date_time", "fc_001", ["¿Qué hora es?"])
        self.assertEqual(len(j._tool_calls_executed), 1)
        self.assertEqual(j._tool_calls_rejected[-1]["reason"], "duplicate_turn_call")

    def test_different_id_allowed(self):
        j = StubJarvis()
        j.new_turn("turn_diff_id")
        j.dispatch_tool_call("date_time", "fc_001", ["¿Qué hora es?"])
        j.dispatch_tool_call("date_time", "fc_002", ["¿Qué hora es?"])
        self.assertEqual(len(j._tool_calls_executed), 2)

    def test_same_tool_different_turns_allowed(self):
        j = StubJarvis()
        j.new_turn("turn_A")
        j.dispatch_tool_call("date_time", "fc_A", ["¿Qué hora es?"])
        j.new_turn("turn_B")
        j.dispatch_tool_call("date_time", "fc_B", ["¿Qué hora es?"])
        self.assertEqual(len(j._tool_calls_executed), 2)


class TestRealLog_TurnBoundaryReset(unittest.TestCase):
    """Test that new turn resets all flags correctly."""

    def test_new_turn_clears_interrupted(self):
        j = StubJarvis()
        j.new_turn("t1")
        j.local_barge_in()
        self.assertTrue(j._turn_interrupted)

        j.new_turn("t2")
        self.assertFalse(j._turn_interrupted)
        self.assertFalse(j._suppress_interrupted_output)
        self.assertEqual(len(j._turn_tool_signatures), 0)

    def test_new_turn_allows_tools_again(self):
        j = StubJarvis()
        j.new_turn("t1")
        j.local_barge_in()
        j.dispatch_tool_call("date_time", "fc_blocked", ["¿Qué hora es?"])
        self.assertEqual(len(j._tool_calls_executed), 0)

        j.new_turn("t2")
        j.dispatch_tool_call("date_time", "fc_allowed", ["¿Qué hora es?"])
        self.assertEqual(len(j._tool_calls_executed), 1)

    def test_new_turn_allows_audio(self):
        j = StubJarvis()
        j.new_turn("t1")
        j.local_barge_in()
        self.assertFalse(j.receive_response_audio(b"suppressed"))

        j.new_turn("t2")
        self.assertTrue(j.receive_response_audio(b"new_audio"))


class TestRealLog_ConversationMemoryIsolation(unittest.TestCase):
    """Test that void turns don't contaminate conversation memory."""

    def test_streaming_partial_purged(self):
        """Streaming partial saved during turn is removed at turn_complete for void."""
        j = StubJarvis()
        j.new_turn("turn_stream_purge")
        # Simulate streaming save (happens during input_transcription)
        j._conversation_continuity.append({
            "role": "user", "text": "<noise>",
            "turn_id": "turn_stream_purge",
        })
        # At turn_complete, void turn purges it
        is_void = j.turn_complete(["<noise>"], ["Response"])
        self.assertTrue(is_void)
        self.assertEqual(len(j._conversation_continuity), 0)

    def test_other_turns_preserved(self):
        """Purging void turn doesn't affect other turns."""
        j = StubJarvis()
        # Existing turn in memory
        j._conversation_continuity.append({
            "role": "user", "text": "¿Qué hora es?",
            "turn_id": "turn_old",
        })
        j._conversation_continuity.append({
            "role": "assistant", "text": "Son las 21:14",
            "turn_id": "turn_old",
        })

        # New void turn
        j.new_turn("turn_void")
        j._conversation_continuity.append({
            "role": "user", "text": ".",
            "turn_id": "turn_void",
        })
        j.turn_complete(["."], ["Should be voided"])

        # Old turn preserved, void turn removed
        self.assertEqual(len(j._conversation_continuity), 2)
        self.assertEqual(j._conversation_continuity[0]["text"], "¿Qué hora es?")
        self.assertEqual(j._conversation_continuity[1]["text"], "Son las 21:14")

    def test_no_aurora_entry_for_void(self):
        """AURORA response to void input must not be saved."""
        j = StubJarvis()
        j.new_turn("turn_no_aurora")
        j.turn_complete(["<silence>"], ["¿En qué puedo ayudarte?"])
        assistant_turns = [t for t in j._conversation_continuity if t["role"] == "assistant"]
        self.assertEqual(len(assistant_turns), 0)


class TestStripNoiseTags(unittest.TestCase):
    """Test _strip_noise_tags helper."""

    def test_pure_noise(self):
        self.assertEqual(_strip_noise_tags("<noise>"), "")

    def test_pure_silence(self):
        self.assertEqual(_strip_noise_tags("<silence>"), "")

    def test_mixed_noise_content(self):
        self.assertEqual(_strip_noise_tags("<noise> Voilà. <noise>"), "Voilà.")

    def test_noise_prefix(self):
        self.assertEqual(_strip_noise_tags("<noise> Para"), "Para")

    def test_no_noise(self):
        self.assertEqual(_strip_noise_tags("¿Qué hora es?"), "¿Qué hora es?")

    def test_empty(self):
        self.assertEqual(_strip_noise_tags(""), "")
        self.assertEqual(_strip_noise_tags(None), "")

    def test_case_insensitive(self):
        self.assertEqual(_strip_noise_tags("<NOISE> Hola <Noise>"), "Hola")

    def test_multiple_spaces_collapsed(self):
        self.assertEqual(_strip_noise_tags("<noise>   Hola   <noise>"), "Hola")

    def test_silence_and_noise_mixed(self):
        self.assertEqual(_strip_noise_tags("<silence> <noise> Dime"), "Dime")


class TestRealLog_FullTurnSequence(unittest.TestCase):
    """Replay the full real sequence from the journal: question → barge-in → noise → dot.

    Journal timeline:
      21:14:24  ¿Qué hora es? → date_time → Ahora son las 21:14
      21:14:27  barge-in → <noise> → ghost date_time
      21:14:33  (new turn) dot input → ghost date_time result displayed
    """

    def test_three_turn_sequence(self):
        j = StubJarvis()

        # Turn 1: real question
        j.new_turn("turn_hora")
        j.dispatch_tool_call("date_time", "fc_hora", ["¿Qué hora es?"])
        self.assertEqual(len(j._tool_calls_executed), 1)
        j.turn_complete(["¿Qué hora es?"], ["Ahora son las 21:14"])
        self.assertEqual(j._current_input_transcript, "¿Qué hora es?")

        # Turn 2: barge-in while JARVIS speaks → <noise>
        j.set_speaking(True)
        for i in range(16):
            j.audio_in_queue.put_nowait(b"old")
        j.new_turn("turn_noise")
        j.local_barge_in()
        j.provider_interruption()

        # Ghost tool call from noise context
        j.dispatch_tool_call("date_time", "fc_ghost", ["<noise>"])
        self.assertEqual(len(j._tool_calls_executed), 1)  # Still just 1 from turn 1

        # Turn complete with noise
        is_void = j.turn_complete(["<noise>"], ["¿En qué más puedo ayudarte?"])
        self.assertTrue(is_void)
        self.assertEqual(j._current_input_transcript, "¿Qué hora es?")  # NOT overwritten

        # Turn 3: dot input
        j.new_turn("turn_dot")
        j.dispatch_tool_call("date_time", "fc_dot", ["."])
        self.assertEqual(len(j._tool_calls_executed), 1)  # STILL just 1

        is_void = j.turn_complete(["."], ["Ahora son las 21:14"])
        self.assertTrue(is_void)

        # Verify final state: only turn 1's entries in conversation memory
        user_turns = [t for t in j._conversation_continuity if t["role"] == "user"]
        self.assertEqual(len(user_turns), 1)
        self.assertEqual(user_turns[0]["text"], "¿Qué hora es?")

        # No noise or dots in memory
        all_texts = [t["text"] for t in j._conversation_continuity]
        self.assertNotIn("<noise>", all_texts)
        self.assertNotIn(".", all_texts)


class TestRealLog_InaudibleBracket(unittest.TestCase):
    """Test [inaudible], [music] and similar bracket annotations."""

    def test_inaudible_rejected(self):
        self.assertFalse(_is_semantic_transcript("[inaudible]"))

    def test_music_rejected(self):
        self.assertFalse(_is_semantic_transcript("[music]"))

    def test_applause_rejected(self):
        self.assertFalse(_is_semantic_transcript("[applause]"))

    def test_inaudible_void_turn(self):
        j = StubJarvis()
        j.new_turn("turn_inaudible")
        is_void = j.turn_complete(["[inaudible]"], ["No te he entendido"])
        self.assertTrue(is_void)


if __name__ == "__main__":
    unittest.main()
