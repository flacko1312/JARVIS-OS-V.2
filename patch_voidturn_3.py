#!/usr/bin/env python3
"""Patch part 3: Flush remaining quarantine at turn_complete for valid turns,
discard for empty-input turns that got no validation."""

PATH = "/home/flako1312/jarvis-headless/main.py"
with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

changes = 0

# After the void_turn block and the elif full_in block, before in_buf = [],
# add a final quarantine flush for any remaining audio in valid turns.
# The turn_had_audio = False and _new_turn = True happen right after out_buf = [].
# We add the flush right before turn_had_audio = False.

old_turn_reset = '''                            out_buf = []
                            turn_had_audio = False
                            _new_turn = True'''

new_turn_reset = '''                            if _audio_quarantine:
                                if not _void_turn and (full_in == "" or _input_validated):
                                    for _qchunk in _audio_quarantine:
                                        self.audio_in_queue.put_nowait(_qchunk)
                                else:
                                    logger.info(
                                        "AUDIO_QUARANTINE discarded turn_id=%s chunks=%d",
                                        live_turn_id, len(_audio_quarantine),
                                    )
                                _audio_quarantine.clear()

                            out_buf = []
                            turn_had_audio = False
                            _new_turn = True'''

if old_turn_reset in content:
    content = content.replace(old_turn_reset, new_turn_reset, 1)
    changes += 1
    print("  [3a] Added final quarantine flush/discard at turn reset")
else:
    print("  [3a] SKIP - turn reset pattern not found")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\nPatch part 3 applied: {changes} changes")
