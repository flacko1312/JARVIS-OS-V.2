#!/usr/bin/env python3
"""Patch: Eliminate all side effects before replay/validation decision.

1. Defer _update_schedule_turn until after validation
2. Defer _remember_conversation_text("user") until after validation
3. Quarantine output_transcription (assistant memory + subtitle) until input validated
4. Remove dead state from _last_interrupted_turn (tool_sigs, timestamp)
"""

PATH = "/home/flako1312/jarvis-headless/main.py"
with open(PATH) as f:
    content = f.read()

changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Add _output_quarantine at turn start (alongside _audio_quarantine)
# ═══════════════════════════════════════════════════════════════
old_turn_start = "                _audio_quarantine = []\n                _replay_rejected = False"
new_turn_start = "                _audio_quarantine = []\n                _output_quarantine = []\n                _replay_rejected = False"
if old_turn_start in content:
    content = content.replace(old_turn_start, new_turn_start, 1)
    changes += 1
    print("  [1] Added _output_quarantine to turn start")

# ═══════════════════════════════════════════════════════════════
# 2. Quarantine output_transcription until input validated
# ═══════════════════════════════════════════════════════════════
old_output_trans = '''                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                merged_output = _merge_transcript_text(
                                    " ".join(out_buf), txt
                                )
                                out_buf = [merged_output]
                                self._interrupted_text = merged_output
                                self._remember_conversation_text(
                                    "assistant",
                                    self._interrupted_text,
                                    expected_conversation_id=receive_conversation_id,
                                    turn_id=live_turn_id,
                                )
                                if not self.ui.muted:
                                    if _new_turn:
                                        self.ui.clear_subtitle()
                                        _new_turn = False
                                    self.ui.show_subtitle(txt)'''

new_output_trans = '''                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                merged_output = _merge_transcript_text(
                                    " ".join(out_buf), txt
                                )
                                out_buf = [merged_output]
                                self._interrupted_text = merged_output
                                if _input_validated:
                                    self._remember_conversation_text(
                                        "assistant",
                                        self._interrupted_text,
                                        expected_conversation_id=receive_conversation_id,
                                        turn_id=live_turn_id,
                                    )
                                    if not self.ui.muted:
                                        if _new_turn:
                                            self.ui.clear_subtitle()
                                            _new_turn = False
                                        self.ui.show_subtitle(txt)
                                else:
                                    _output_quarantine.append(("assistant_text", self._interrupted_text, txt))'''

if old_output_trans in content:
    content = content.replace(old_output_trans, new_output_trans, 1)
    changes += 1
    print("  [2] Quarantined output_transcription until input validated")

# ═══════════════════════════════════════════════════════════════
# 3. Defer schedule + user memory until after validation; flush output quarantine on validate
# ═══════════════════════════════════════════════════════════════
old_input_block = '''                                in_buf = [current_input]
                                self._update_schedule_turn(current_input)
                                if not _input_validated and not _replay_rejected and _is_semantic_transcript(_strip_noise_tags(current_input)):
                                    _norm = _strip_noise_tags(current_input).strip().lower()
                                    if (
                                        self._last_interrupted_turn is not None
                                        and self._last_interrupted_turn.get("normalized_input") == _norm
                                    ):
                                        _replay_rejected = True
                                        logger.info(
                                            "TURN_REPLAY rejected source_turn=%s current_turn=%s input=%r reason=interrupted_turn_replay",
                                            self._last_interrupted_turn.get("turn_id", "?"),
                                            live_turn_id, current_input[:80],
                                        )
                                        _audio_quarantine.clear()
                                    else:
                                        _input_validated = True
                                        for _qchunk in _audio_quarantine:
                                            self.audio_in_queue.put_nowait(_qchunk)
                                        _audio_quarantine.clear()
                                self._remember_conversation_text(
                                    "user",
                                    current_input,
                                    expected_conversation_id=receive_conversation_id,
                                    turn_id=live_turn_id,
                                )
                                if (
                                    not getattr(self, "_pending_self_quit", False)
                                    and self._is_explicit_self_quit_transcript(self._current_input_transcript)
                                ):
                                    self._queue_self_quit_after_farewell()'''

new_input_block = '''                                in_buf = [current_input]
                                if not _input_validated and not _replay_rejected and _is_semantic_transcript(_strip_noise_tags(current_input)):
                                    _norm = _strip_noise_tags(current_input).strip().lower()
                                    if (
                                        self._last_interrupted_turn is not None
                                        and self._last_interrupted_turn.get("normalized_input") == _norm
                                    ):
                                        _replay_rejected = True
                                        logger.info(
                                            "TURN_REPLAY rejected source_turn=%s current_turn=%s input=%r reason=interrupted_turn_replay",
                                            self._last_interrupted_turn.get("turn_id", "?"),
                                            live_turn_id, current_input[:80],
                                        )
                                        _audio_quarantine.clear()
                                        _output_quarantine.clear()
                                    else:
                                        _input_validated = True
                                        self._update_schedule_turn(current_input)
                                        self._remember_conversation_text(
                                            "user",
                                            current_input,
                                            expected_conversation_id=receive_conversation_id,
                                            turn_id=live_turn_id,
                                        )
                                        for _qchunk in _audio_quarantine:
                                            self.audio_in_queue.put_nowait(_qchunk)
                                        _audio_quarantine.clear()
                                        for _qtype, _qtext, _qtxt in _output_quarantine:
                                            self._remember_conversation_text(
                                                "assistant",
                                                _qtext,
                                                expected_conversation_id=receive_conversation_id,
                                                turn_id=live_turn_id,
                                            )
                                            if not self.ui.muted:
                                                self.ui.show_subtitle(_qtxt)
                                        _output_quarantine.clear()
                                        if (
                                            not getattr(self, "_pending_self_quit", False)
                                            and self._is_explicit_self_quit_transcript(current_input)
                                        ):
                                            self._queue_self_quit_after_farewell()
                                elif _input_validated:
                                    self._update_schedule_turn(current_input)
                                    self._remember_conversation_text(
                                        "user",
                                        current_input,
                                        expected_conversation_id=receive_conversation_id,
                                        turn_id=live_turn_id,
                                    )'''

if old_input_block in content:
    content = content.replace(old_input_block, new_input_block, 1)
    changes += 1
    print("  [3] Deferred schedule/user memory until after validation; added output quarantine flush")

# ═══════════════════════════════════════════════════════════════
# 4. Remove dead state from _last_interrupted_turn
# ═══════════════════════════════════════════════════════════════
old_save = '''                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):
                                    self._last_interrupted_turn = {
                                        "turn_id": live_turn_id,
                                        "normalized_input": _clean_in.strip().lower(),
                                        "tool_sigs": set(self._turn_tool_signatures),
                                        "timestamp": time.monotonic(),
                                    }'''

new_save = '''                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):
                                    self._last_interrupted_turn = {
                                        "turn_id": live_turn_id,
                                        "normalized_input": _clean_in.strip().lower(),
                                    }'''

if old_save in content:
    content = content.replace(old_save, new_save, 1)
    changes += 1
    print("  [4] Removed dead state (tool_sigs, timestamp) from _last_interrupted_turn")

# Also remove from __init__ if present
old_init_lit = 'self._last_interrupted_turn: dict | None = None'
if old_init_lit in content:
    print("  [4b] __init__ declaration already clean (no dead fields)")

# ═══════════════════════════════════════════════════════════════
# 5. Also discard _output_quarantine on replay at turn_complete
# ═══════════════════════════════════════════════════════════════
# The replay discard block at turn_complete already clears _audio_quarantine
# Add _output_quarantine.clear() there too
old_replay_discard = '''                            if _replay_rejected:
                                logger.info(
                                    "TURN_REPLAY discard turn_id=%s input=%r",
                                    live_turn_id, full_in[:80],
                                )
                                _audio_quarantine.clear()'''

new_replay_discard = '''                            if _replay_rejected:
                                logger.info(
                                    "TURN_REPLAY discard turn_id=%s input=%r",
                                    live_turn_id, full_in[:80],
                                )
                                _audio_quarantine.clear()
                                _output_quarantine.clear()'''

if old_replay_discard in content:
    content = content.replace(old_replay_discard, new_replay_discard, 1)
    changes += 1
    print("  [5] Added _output_quarantine.clear() to replay discard block")

# ═══════════════════════════════════════════════════════════════
# 6. Also discard _output_quarantine on void turn
# ═══════════════════════════════════════════════════════════════
old_void_clear = '''                            elif _void_turn:
                                logger.info(
                                    "VOID_TURN id=%s raw=%r quarantined_chunks=%d",
                                    live_turn_id, full_in[:80], len(_audio_quarantine),
                                )
                                _audio_quarantine.clear()'''

new_void_clear = '''                            elif _void_turn:
                                logger.info(
                                    "VOID_TURN id=%s raw=%r quarantined_chunks=%d",
                                    live_turn_id, full_in[:80], len(_audio_quarantine),
                                )
                                _audio_quarantine.clear()
                                _output_quarantine.clear()'''

if old_void_clear in content:
    content = content.replace(old_void_clear, new_void_clear, 1)
    changes += 1
    print("  [6] Added _output_quarantine.clear() to void turn discard")

# ═══════════════════════════════════════════════════════════════
# 7. Final quarantine flush at turn reset: also handle _output_quarantine
# ═══════════════════════════════════════════════════════════════
old_final_q = '''                            if _audio_quarantine:
                                if not _void_turn and not _replay_rejected and (full_in == "" or _input_validated):
                                    for _qchunk in _audio_quarantine:
                                        self.audio_in_queue.put_nowait(_qchunk)
                                else:
                                    logger.info(
                                        "AUDIO_QUARANTINE discarded turn_id=%s chunks=%d",
                                        live_turn_id, len(_audio_quarantine),
                                    )
                                _audio_quarantine.clear()'''

new_final_q = '''                            if _audio_quarantine:
                                if not _void_turn and not _replay_rejected and (full_in == "" or _input_validated):
                                    for _qchunk in _audio_quarantine:
                                        self.audio_in_queue.put_nowait(_qchunk)
                                else:
                                    logger.info(
                                        "AUDIO_QUARANTINE discarded turn_id=%s chunks=%d",
                                        live_turn_id, len(_audio_quarantine),
                                    )
                                _audio_quarantine.clear()
                            if _output_quarantine:
                                if not _void_turn and not _replay_rejected and _input_validated:
                                    for _qtype, _qtext, _qtxt in _output_quarantine:
                                        self._remember_conversation_text(
                                            "assistant",
                                            _qtext,
                                            expected_conversation_id=receive_conversation_id,
                                            turn_id=live_turn_id,
                                        )
                                _output_quarantine.clear()'''

if old_final_q in content:
    content = content.replace(old_final_q, new_final_q, 1)
    changes += 1
    print("  [7] Added final _output_quarantine flush at turn reset")

with open(PATH, "w") as f:
    f.write(content)

print(f"\nPatch applied: {changes} changes")
