#!/usr/bin/env python3
"""Patch JARVIS Ubuntu to preserve interrupted assistant context for conversation continuity.

ROOT CAUSE: Our previous patches deleted all assistant entries from _conversation_continuity
when a turn was interrupted. This destroyed conversation context — Gemini could no longer
resolve "continúa" or "volvemos a lo de antes" because the partial response was gone.

FIX: When a turn is interrupted and input was validated, preserve the partial assistant
output in durable memory with an [interrumpido] marker. This gives Gemini the context
to continue where it left off. Non-validated or noise turns still get zero side effects.

Also: When a stop-control ("Para") is consumed, save the interrupted assistant checkpoint
from the PREVIOUS turn (if any) so context is not lost.
"""

PATH = "/home/flako1312/jarvis-headless/main.py"

with open(PATH) as f:
    content = f.read()

changes = 0

# ─── CHANGE 1: At turn_complete, preserve interrupted assistant partial output ───
# Instead of deleting assistant entries when interrupted, upsert the partial output
# with an [interrumpido] marker so Gemini has context to continue.

old_interrupted_block = '''            elif self._turn_interrupted and _input_validated:
                                with self._conversation_lock:
                                    self._conversation_continuity = [
                                        t for t in self._conversation_continuity
                                        if not (t.get("turn_id") == live_turn_id and t.get("role") == "assistant")
                                    ]
                                    self._persist_conversation_state()'''

new_interrupted_block = '''            elif self._turn_interrupted and _input_validated:
                                if full_out:
                                    _interrupted_checkpoint = f"[interrumpido] {full_out}"
                                    self._remember_conversation_text(
                                        "assistant",
                                        _interrupted_checkpoint,
                                        expected_conversation_id=receive_conversation_id,
                                        turn_id=live_turn_id,
                                    )
                                    logger.info(
                                        "INTERRUPTED_CHECKPOINT saved turn_id=%s chars=%d",
                                        live_turn_id, len(full_out),
                                    )
                                else:
                                    with self._conversation_lock:
                                        self._conversation_continuity = [
                                            t for t in self._conversation_continuity
                                            if not (t.get("turn_id") == live_turn_id and t.get("role") == "assistant")
                                        ]
                                        self._persist_conversation_state()'''

if old_interrupted_block in content:
    content = content.replace(old_interrupted_block, new_interrupted_block, 1)
    changes += 1
    print("  [1] Preserve interrupted assistant checkpoint instead of deleting")
else:
    print("  [1] FAILED: old interrupted block not found")

# ─── CHANGE 2: Store interrupted checkpoint in _last_interrupted_turn for context ───
# When saving _last_interrupted_turn, also store the partial assistant output
# so the stop-control path can preserve it.

old_interrupted_save = '''                            if not _replay_rejected:
                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):
                                    self._last_interrupted_turn = {
                                        "turn_id": live_turn_id,
                                        "normalized_input": _clean_in.strip().lower(),
                                        "canonical_input": _canonicalize_for_replay(full_in),
                                        "timestamp": time.monotonic(),
                                    }'''

new_interrupted_save = '''                            if not _replay_rejected:
                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):
                                    self._last_interrupted_turn = {
                                        "turn_id": live_turn_id,
                                        "normalized_input": _clean_in.strip().lower(),
                                        "canonical_input": _canonicalize_for_replay(full_in),
                                        "partial_assistant_output": full_out or "",
                                        "timestamp": time.monotonic(),
                                    }'''

if old_interrupted_save in content:
    content = content.replace(old_interrupted_save, new_interrupted_save, 1)
    changes += 1
    print("  [2] Store partial_assistant_output in _last_interrupted_turn")
else:
    print("  [2] FAILED: old interrupted save not found")

# ─── CHANGE 3: When stop-control is consumed, don't destroy previous context ───
# The stop-control path currently clears quarantines (good) but doesn't preserve
# the interrupted topic context. The _last_interrupted_turn already has context
# from the prior turn, but the conversation store was losing it.
# We need to make sure that when "Para" is consumed, the conversation store
# still has the prior turn's assistant partial output (it does, because we no longer
# delete it in change 1).
# No code change needed here — change 1 already handles it.

# ─── CHANGE 4: Add _last_interrupted_turn to __init__ if needed ───
# It should already be there from the previous patches. Verify.
if "self._last_interrupted_turn" in content:
    print("  [4] _last_interrupted_turn already in __init__")
else:
    print("  [4] WARNING: _last_interrupted_turn not found in __init__")

# ─── CHANGE 5: Replay discard should also clear partial assistant checkpoint ───
# When a replay is detected, clean the assistant entry but keep the PREVIOUS turn's
# checkpoint (which is in the store from the prior turn, not this replay turn).
# The existing code already does this: it removes entries matching live_turn_id.
# No change needed.

print(f"\nTotal changes applied: {changes}")

with open(PATH, "w") as f:
    f.write(content)
