#!/usr/bin/env python3
"""Patch part 2: Flush quarantine on validated input, discard on void turn."""

PATH = "/home/flako1312/jarvis-headless/main.py"
with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

changes = 0

# 2c. After in_buf is updated with input text, validate and flush quarantine
old_input_update = '''                                current_input = _merge_transcript_text(
                                    " ".join(in_buf), txt
                                )
                                in_buf = [current_input]
                                self._update_schedule_turn(current_input)'''

new_input_update = '''                                current_input = _merge_transcript_text(
                                    " ".join(in_buf), txt
                                )
                                in_buf = [current_input]
                                self._update_schedule_turn(current_input)
                                if not _input_validated and _is_semantic_transcript(_strip_noise_tags(current_input)):
                                    _input_validated = True
                                    for _qchunk in _audio_quarantine:
                                        self.audio_in_queue.put_nowait(_qchunk)
                                    _audio_quarantine.clear()'''

if old_input_update in content:
    content = content.replace(old_input_update, new_input_update, 1)
    changes += 1
    print("  [2c] Added quarantine flush on semantic input validation")
else:
    print("  [2c] SKIP - input update pattern not found")

# 2d. At turn_complete, if void turn, discard quarantine and interrupt playback
# Find the void_turn block and add quarantine discard
old_void_turn = '''                            if _void_turn:
                                logger.info(
                                    "VOID_TURN id=%s raw=%r",
                                    live_turn_id, full_in[:80],
                                )'''

new_void_turn = '''                            if _void_turn:
                                logger.info(
                                    "VOID_TURN id=%s raw=%r quarantined_chunks=%d",
                                    live_turn_id, full_in[:80], len(_audio_quarantine),
                                )
                                _audio_quarantine.clear()
                                if turn_had_audio:
                                    self._interrupt_live_playback("void_turn_discard")
                                    turn_had_audio = False'''

if old_void_turn in content:
    content = content.replace(old_void_turn, new_void_turn, 1)
    changes += 1
    print("  [2d] Added quarantine discard + playback interrupt on void turn")
else:
    print("  [2d] SKIP - void_turn pattern not found")

# 2e. Also flush quarantine for tool_call path if input is semantic
# The tool_call path already has a non_semantic check at ~line 5712
# If tool call arrives and input is non-semantic, it rejects.
# But if tool call arrives and input IS semantic, we need to validate.
# Find the tool_call section where it checks semantic input
old_tool_semantic = '''                            if in_buf and not _is_semantic_transcript(current_input):
                                logger.info(
                                    "VOICE_INPUT ignored reason=non_semantic_transcript turn_id=%s text=%r",
                                    live_turn_id, current_input[:80],
                                )'''

# Find what comes after - need more context
# Actually the existing tool_call path already handles this:
# if input is non-semantic, it rejects the tool call
# if input IS semantic, it proceeds normally
# We just need to make sure quarantine is flushed when tool call is accepted

# Let me check what comes right after the non-semantic check
print("  [2e] Checking tool_call semantic path...")

with open(PATH, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the tool_call semantic check
for i, line in enumerate(lines):
    if "VOICE_INPUT ignored reason=non_semantic_transcript" in line:
        # Print context around it
        for j in range(max(0, i-5), min(len(lines), i+20)):
            print(f"    {j+1}: {lines[j].rstrip()}")
        break

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\nPatch part 2 applied: {changes} changes")
