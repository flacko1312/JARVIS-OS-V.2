#!/usr/bin/env python3
"""Patch: Cross-turn replay guard for interrupted turns."""

PATH = "/home/flako1312/jarvis-headless/main.py"
with open(PATH) as f:
    content = f.read()

changes = 0

# 1. Add _last_interrupted_turn to __init__
old_init = "self._turn_tool_signatures: set[str] = set()"
new_init = "self._turn_tool_signatures: set[str] = set()\n        self._last_interrupted_turn: dict | None = None"

if old_init in content and "_last_interrupted_turn" not in content:
    content = content.replace(old_init, new_init, 1)
    changes += 1
    print("  [1] Added _last_interrupted_turn to __init__")

# 2. Add _replay_rejected flag at turn start
old_ts = "                _input_validated = False\n                _audio_quarantine = []"
new_ts = "                _input_validated = False\n                _audio_quarantine = []\n                _replay_rejected = False"
if old_ts in content:
    content = content.replace(old_ts, new_ts, 1)
    changes += 1
    print("  [2] Added _replay_rejected to turn start")

# 3. At semantic validation, check for interrupted replay
old_val = (
    "                                if not _input_validated and _is_semantic_transcript(_strip_noise_tags(current_input)):\n"
    "                                    _input_validated = True\n"
    "                                    for _qchunk in _audio_quarantine:\n"
    "                                        self.audio_in_queue.put_nowait(_qchunk)\n"
    "                                    _audio_quarantine.clear()"
)
new_val = (
    "                                if not _input_validated and not _replay_rejected and _is_semantic_transcript(_strip_noise_tags(current_input)):\n"
    "                                    _norm = _strip_noise_tags(current_input).strip().lower()\n"
    "                                    if (\n"
    "                                        self._last_interrupted_turn is not None\n"
    "                                        and self._last_interrupted_turn.get(\"normalized_input\") == _norm\n"
    "                                    ):\n"
    "                                        _replay_rejected = True\n"
    "                                        logger.info(\n"
    "                                            \"TURN_REPLAY rejected source_turn=%s current_turn=%s input=%r reason=interrupted_turn_replay\",\n"
    "                                            self._last_interrupted_turn.get(\"turn_id\", \"?\"),\n"
    "                                            live_turn_id, current_input[:80],\n"
    "                                        )\n"
    "                                        _audio_quarantine.clear()\n"
    "                                    else:\n"
    "                                        _input_validated = True\n"
    "                                        for _qchunk in _audio_quarantine:\n"
    "                                            self.audio_in_queue.put_nowait(_qchunk)\n"
    "                                        _audio_quarantine.clear()"
)
if old_val in content:
    content = content.replace(old_val, new_val, 1)
    changes += 1
    print("  [3] Added interrupted replay check at semantic validation")

# 4a. Update TURN close log
old_tc_log = (
    '                            logger.info(\n'
    '                                "TURN close id=%s reason=turn_complete interrupted=%s",\n'
    '                                live_turn_id, self._turn_interrupted,\n'
    '                            )'
)
new_tc_log = (
    '                            logger.info(\n'
    '                                "TURN close id=%s reason=turn_complete interrupted=%s replay_rejected=%s",\n'
    '                                live_turn_id, self._turn_interrupted, _replay_rejected,\n'
    '                            )'
)
if old_tc_log in content:
    content = content.replace(old_tc_log, new_tc_log, 1)
    changes += 1
    print("  [4a] Updated TURN close log")

# 4b. Add replay discard block after void_turn computation
old_void = (
    "                            full_in = \" \".join(in_buf).strip()\n"
    "                            _clean_in = _strip_noise_tags(full_in) if full_in else \"\"\n"
    "                            _void_turn = bool(full_in) and not _is_semantic_transcript(_clean_in)\n"
    "\n"
    "                            if _void_turn:"
)
new_void = (
    "                            full_in = \" \".join(in_buf).strip()\n"
    "                            _clean_in = _strip_noise_tags(full_in) if full_in else \"\"\n"
    "                            _void_turn = bool(full_in) and not _is_semantic_transcript(_clean_in)\n"
    "\n"
    "                            if _replay_rejected:\n"
    "                                logger.info(\n"
    "                                    \"TURN_REPLAY discard turn_id=%s input=%r\",\n"
    "                                    live_turn_id, full_in[:80],\n"
    "                                )\n"
    "                                _audio_quarantine.clear()\n"
    "                                if turn_had_audio:\n"
    "                                    self._interrupt_live_playback(\"replay_discard\")\n"
    "                                    turn_had_audio = False\n"
    "                                with self._conversation_lock:\n"
    "                                    self._conversation_continuity = [\n"
    "                                        t for t in self._conversation_continuity\n"
    "                                        if t.get(\"turn_id\") != live_turn_id\n"
    "                                    ]\n"
    "                                    self._persist_conversation_state()\n"
    "                                self._last_interrupted_turn = None\n"
    "\n"
    "                            elif _void_turn:"
)
if old_void in content:
    content = content.replace(old_void, new_void, 1)
    changes += 1
    print("  [4b] Added replay discard block and changed if to elif chain")

# 5a. Gate user input persistence
old_elif = "                            elif full_in:\n                                save_in = _clean_in if _clean_in != full_in else full_in\n                                self._current_input_transcript = save_in"
# Now this is inside the elif chain after _replay_rejected and _void_turn
# It should already be correct since we turned `if _void_turn` into `elif _void_turn`
# and `elif full_in` stays as is. But replay turns skip to the new if block.
# The existing `elif full_in:` only runs when not _replay_rejected and not _void_turn.
# That's correct because the if/_replay_rejected block above handles replay cases.
print("  [5a] User input persistence already gated by elif chain (replay handled above)")

# 5b. Gate assistant output persistence
old_fo = "                            full_out = \" \".join(out_buf).strip()\n                            if full_out and not _void_turn:"
new_fo = "                            full_out = \" \".join(out_buf).strip()\n                            if full_out and not _void_turn and not _replay_rejected:"
if old_fo in content:
    content = content.replace(old_fo, new_fo, 1)
    changes += 1
    print("  [5b] Gated assistant output persistence")

# 6. Save interrupted turn state / clear at turn end
old_reset = (
    "                            if _audio_quarantine:\n"
    "                                if not _void_turn and (full_in == \"\" or _input_validated):\n"
    "                                    for _qchunk in _audio_quarantine:\n"
    "                                        self.audio_in_queue.put_nowait(_qchunk)\n"
    "                                else:\n"
    "                                    logger.info(\n"
    "                                        \"AUDIO_QUARANTINE discarded turn_id=%s chunks=%d\",\n"
    "                                        live_turn_id, len(_audio_quarantine),\n"
    "                                    )\n"
    "                                _audio_quarantine.clear()\n"
    "\n"
    "                            out_buf = []\n"
    "                            turn_had_audio = False\n"
    "                            _new_turn = True"
)
new_reset = (
    "                            if _audio_quarantine:\n"
    "                                if not _void_turn and not _replay_rejected and (full_in == \"\" or _input_validated):\n"
    "                                    for _qchunk in _audio_quarantine:\n"
    "                                        self.audio_in_queue.put_nowait(_qchunk)\n"
    "                                else:\n"
    "                                    logger.info(\n"
    "                                        \"AUDIO_QUARANTINE discarded turn_id=%s chunks=%d\",\n"
    "                                        live_turn_id, len(_audio_quarantine),\n"
    "                                    )\n"
    "                                _audio_quarantine.clear()\n"
    "\n"
    "                            if not _replay_rejected:\n"
    "                                if self._turn_interrupted and full_in and _is_semantic_transcript(_clean_in):\n"
    "                                    self._last_interrupted_turn = {\n"
    "                                        \"turn_id\": live_turn_id,\n"
    "                                        \"normalized_input\": _clean_in.strip().lower(),\n"
    "                                        \"tool_sigs\": set(self._turn_tool_signatures),\n"
    "                                        \"timestamp\": time.monotonic(),\n"
    "                                    }\n"
    "                                elif not self._turn_interrupted:\n"
    "                                    self._last_interrupted_turn = None\n"
    "\n"
    "                            out_buf = []\n"
    "                            turn_had_audio = False\n"
    "                            _new_turn = True"
)
if old_reset in content:
    content = content.replace(old_reset, new_reset, 1)
    changes += 1
    print("  [6] Added interrupted turn state save/clear")

# 7. Gate tool execution on not _replay_rejected
old_tg = '                            if not _input_validated:\n                                current_input = " ".join(in_buf).strip()\n                                logger.info(\n                                    "TOOL_CALL rejected reason=no_valid_semantic_input turn_id=%s text=%r tools=%s",'
new_tg = '                            if _replay_rejected or not _input_validated:\n                                current_input = " ".join(in_buf).strip()\n                                _reject_reason = "interrupted_turn_replay" if _replay_rejected else "no_valid_semantic_input"\n                                logger.info(\n                                    "TOOL_CALL rejected reason=%s turn_id=%s text=%r tools=%s",\n                                    _reject_reason,'
if old_tg in content:
    content = content.replace(old_tg, new_tg, 1)
    changes += 1
    print("  [7a] Added _replay_rejected to tool guard")

# Update tool rejection response
old_resp = '                                        response={"result": "No valid semantic input; tool call rejected."},'
new_resp = '                                        response={"result": f"{_reject_reason}; tool call rejected."},'
if old_resp in content:
    content = content.replace(old_resp, new_resp, 1)
    changes += 1
    print("  [7b] Updated tool rejection response")

with open(PATH, "w") as f:
    f.write(content)

print(f"\nPatch applied: {changes} changes")
