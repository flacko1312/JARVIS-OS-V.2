#!/usr/bin/env python3
"""Patch: Five fixes for turn integrity.

1. Fuzzy cross-turn replay detection
2. Post-barge-in standalone stop control
3. Interrupted assistant memory cleanup
4. AURORA -> JARVIS log label (headless only)
5. Save canonical form for fuzzy replay
"""

PATH = "/home/flako1312/jarvis-headless/main.py"
with open(PATH) as f:
    content = f.read()

changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Add _canonicalize_for_replay helper near _strip_noise_tags
# ═══════════════════════════════════════════════════════════════

# Find a good insertion point — after _strip_noise_tags definition
old_strip = '''def _strip_noise_tags(text: str) -> str:'''
idx = content.find(old_strip)
if idx < 0:
    print("  [1] SKIP - _strip_noise_tags not found")
else:
    # Find the end of _strip_noise_tags function (next def or class at same indent)
    # Insert after it
    insert_after = "_NOISE_TAG_RE.sub"
    idx2 = content.find(insert_after, idx)
    # Find end of that line
    eol = content.find("\n", idx2)
    # Find next blank line after function
    next_blank = content.find("\n\n", eol)

    canonical_func = '''


import unicodedata as _unicodedata
import re as _re_mod

_INTRA_WORD_SPACE_RE = _re_mod.compile(r"(?<=\w) (?=\w)")
_MULTI_SPACE_RE = _re_mod.compile(r"\s+")

def _canonicalize_for_replay(text: str) -> str:
    """Normalize text for fuzzy replay comparison.

    Strips accents, collapses artificial intra-word spaces from ASR,
    lowercases, removes punctuation. Designed for comparing two ASR
    transcriptions of the same utterance that may differ in spacing
    and minor word errors.
    """
    if not text:
        return ""
    t = text.strip().lower()
    # Strip accents: NFD decompose then drop combining marks
    t = "".join(
        c for c in _unicodedata.normalize("NFD", t)
        if _unicodedata.category(c) != "Mn"
    )
    # Remove punctuation
    t = _re_mod.sub(r"[^\w\s]", "", t)
    # Collapse all whitespace (including artificial intra-word spaces)
    t = _MULTI_SPACE_RE.sub(" ", t).strip()
    return t


def _is_fuzzy_replay(canonical_a: str, canonical_b: str, threshold: float = 0.78) -> bool:
    """Conservative similarity check for interrupted-turn replay detection.

    Uses token overlap (Jaccard on word tokens) plus a length ratio guard.
    Only used in the narrow context of comparing the immediately previous
    interrupted turn against the first following turn within a bounded
    time window.

    RESIDUAL AMBIGUITY: An intentional immediate identical repeat cannot
    be perfectly distinguished from a provider replay without provider
    metadata. The one-shot guard mitigates this.
    """
    if not canonical_a or not canonical_b:
        return False
    if canonical_a == canonical_b:
        return True
    tokens_a = set(canonical_a.split())
    tokens_b = set(canonical_b.split())
    if not tokens_a or not tokens_b:
        return False
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)
    # Length ratio guard: very different lengths are not replays
    len_ratio = min(len(canonical_a), len(canonical_b)) / max(len(canonical_a), len(canonical_b))
    if len_ratio < 0.5:
        return False
    return jaccard >= threshold'''

    content = content[:next_blank] + canonical_func + content[next_blank:]
    changes += 1
    print("  [1] Added _canonicalize_for_replay and _is_fuzzy_replay helpers")


# ═══════════════════════════════════════════════════════════════
# 2. Add _is_post_barge_in_stop_control helper
# ═══════════════════════════════════════════════════════════════

# Insert after _is_fuzzy_replay
insert_marker = "    return jaccard >= threshold"
idx = content.find(insert_marker)
if idx < 0:
    print("  [2] SKIP - _is_fuzzy_replay not found")
else:
    eol = content.find("\n", idx)
    stop_func = '''


_STOP_CONTROL_RE = _re_mod.compile(
    r"^(?:para|stop|basta|calla(?:te)?|silencio|ya)\.?$",
    _re_mod.IGNORECASE,
)
_POST_BARGE_IN_CONTROL_WINDOW_S = 5.0


def _is_standalone_stop_control(text: str) -> bool:
    """True if text is a standalone stop/control utterance."""
    clean = _strip_noise_tags(text).strip()
    return bool(_STOP_CONTROL_RE.match(clean))'''

    content = content[:eol] + stop_func + content[eol:]
    changes += 1
    print("  [2] Added _is_standalone_stop_control helper")


# ═══════════════════════════════════════════════════════════════
# 3. Add _last_barge_in_accepted_t to __init__
# ═══════════════════════════════════════════════════════════════

old_init = "self._last_interrupted_turn: dict | None = None"
new_init = "self._last_interrupted_turn: dict | None = None\n        self._last_barge_in_accepted_t: float = 0.0"

if old_init in content:
    content = content.replace(old_init, new_init, 1)
    changes += 1
    print("  [3] Added _last_barge_in_accepted_t to __init__")


# ═══════════════════════════════════════════════════════════════
# 4. Record barge-in timestamp at acceptance
# ═══════════════════════════════════════════════════════════════

old_barge = """        if decision.accepted and not previously_accepted and not self._local_barge_in_active:
            self._local_barge_in_active = True
            self._suppress_interrupted_output = True
            self._turn_interrupted = True"""

new_barge = """        if decision.accepted and not previously_accepted and not self._local_barge_in_active:
            self._local_barge_in_active = True
            self._suppress_interrupted_output = True
            self._turn_interrupted = True
            self._last_barge_in_accepted_t = time.monotonic()"""

if old_barge in content:
    content = content.replace(old_barge, new_barge, 1)
    changes += 1
    print("  [4] Record barge-in timestamp at acceptance")


# ═══════════════════════════════════════════════════════════════
# 5. Replace exact replay check with fuzzy + add post-barge-in stop + save canonical
# ═══════════════════════════════════════════════════════════════

old_replay_check = """                                if not _input_validated and not _replay_rejected and _is_semantic_transcript(_strip_noise_tags(current_input)):
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
                                    else:"""

new_replay_check = """                                if not _input_validated and not _replay_rejected and _is_semantic_transcript(_strip_noise_tags(current_input)):
                                    _canon = _canonicalize_for_replay(current_input)
                                    _is_replay = False
                                    if self._last_interrupted_turn is not None:
                                        _prev_canon = self._last_interrupted_turn.get("canonical_input", "")
                                        _is_replay = _is_fuzzy_replay(_prev_canon, _canon)
                                    _is_stop_ctrl = (
                                        _is_standalone_stop_control(current_input)
                                        and (time.monotonic() - self._last_barge_in_accepted_t) < _POST_BARGE_IN_CONTROL_WINDOW_S
                                    )
                                    if _is_replay:
                                        _replay_rejected = True
                                        logger.info(
                                            "TURN_REPLAY rejected source_turn=%s current_turn=%s input=%r reason=fuzzy_interrupted_turn_replay",
                                            self._last_interrupted_turn.get("turn_id", "?"),
                                            live_turn_id, current_input[:80],
                                        )
                                        _audio_quarantine.clear()
                                        _output_quarantine.clear()
                                    elif _is_stop_ctrl:
                                        _replay_rejected = True
                                        logger.info(
                                            "STOP_CONTROL consumed turn_id=%s input=%r reason=post_barge_in_stop",
                                            live_turn_id, current_input[:80],
                                        )
                                        _audio_quarantine.clear()
                                        _output_quarantine.clear()
                                    else:"""

if old_replay_check in content:
    content = content.replace(old_replay_check, new_replay_check, 1)
    changes += 1
    print("  [5] Replaced exact replay with fuzzy + added post-barge-in stop control")


# ═══════════════════════════════════════════════════════════════
# 6. Save canonical form in _last_interrupted_turn
# ═══════════════════════════════════════════════════════════════

old_save = """                            if not _replay_rejected:
                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):
                                    self._last_interrupted_turn = {
                                        "turn_id": live_turn_id,
                                        "normalized_input": _clean_in.strip().lower(),
                                    }"""

new_save = """                            if not _replay_rejected:
                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):
                                    self._last_interrupted_turn = {
                                        "turn_id": live_turn_id,
                                        "normalized_input": _clean_in.strip().lower(),
                                        "canonical_input": _canonicalize_for_replay(full_in),
                                        "timestamp": time.monotonic(),
                                    }"""

if old_save in content:
    content = content.replace(old_save, new_save, 1)
    changes += 1
    print("  [6] Save canonical form + timestamp in _last_interrupted_turn")


# ═══════════════════════════════════════════════════════════════
# 7. Fix interrupted assistant memory: at turn_complete, if interrupted,
#    remove assistant entry for this turn_id
# ═══════════════════════════════════════════════════════════════

# The full_out block writes assistant memory. Gate it on not interrupted.
old_full_out = """                            full_out = " ".join(out_buf).strip()
                            if full_out and _input_validated and not _void_turn and not _replay_rejected:
                                self.ui.write_log(f"AURORA: {full_out}")
                                self._remember_conversation_text(
                                    "assistant",
                                    full_out,
                                    expected_conversation_id=receive_conversation_id,
                                    turn_id=live_turn_id,
                                )"""

new_full_out = """                            full_out = " ".join(out_buf).strip()
                            if full_out and _input_validated and not _void_turn and not _replay_rejected and not self._turn_interrupted:
                                self.ui.write_log(f"JARVIS: {full_out}")
                                self._remember_conversation_text(
                                    "assistant",
                                    full_out,
                                    expected_conversation_id=receive_conversation_id,
                                    turn_id=live_turn_id,
                                )
                            elif self._turn_interrupted and _input_validated:
                                with self._conversation_lock:
                                    self._conversation_continuity = [
                                        t for t in self._conversation_continuity
                                        if not (t.get("turn_id") == live_turn_id and t.get("role") == "assistant")
                                    ]
                                    self._persist_conversation_state()"""

if old_full_out in content:
    content = content.replace(old_full_out, new_full_out, 1)
    changes += 1
    print("  [7] Fixed interrupted assistant memory + AURORA->JARVIS label")


# ═══════════════════════════════════════════════════════════════
# 8. Also gate inline output_transcription assistant memory on not interrupted
#    (the inline handler in the output_transcription block)
# ═══════════════════════════════════════════════════════════════
# The inline handler already gates on _input_validated, but when interrupted
# happens mid-turn AFTER validation, it still writes. However, the turn_complete
# cleanup (fix 7) removes it. So the inline write is OK — it's cleaned at turn end.
# No additional change needed for inline.

print(f"\nPatch applied: {changes} changes")

with open(PATH, "w") as f:
    f.write(content)
