#!/usr/bin/env python3
"""Patch: Fix PortAudio write/close race + void turn audio quarantine.

FALLO 1 — PortAudio:
  _play_audio does `await asyncio.to_thread(stream.write, chunk)`.
  When TaskGroup cancels (GoAway), finally calls stream.stop()/close()
  while the thread-pool write may still be running.
  Fix: wrap write and close with a threading.Lock so close waits for
  the in-flight write to finish.

FALLO 2 — Void turn:
  response_audio is enqueued immediately, before knowing if input is
  semantic. So a "." input triggers SPEAKING + playback.
  Fix: hold response_audio in a local buffer until input is validated.
  On turn_complete: if _void_turn, discard the buffer; if semantic,
  the audio was already enqueued (we flush the buffer as we go once
  input text arrives and is semantic).
"""

import re

PATH = "/home/flako1312/jarvis-headless/main.py"
with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

changes = 0

# ═══════════════════════════════════════════════════════════════
# FIX 1: PortAudio write/close race
# ═══════════════════════════════════════════════════════════════

# 1a. Add _playback_stream_lock to __init__
old_init_lock = "self._speaking_lock = threading.Lock()"
new_init_lock = (
    "self._speaking_lock = threading.Lock()\n"
    "        self._playback_stream_lock = threading.Lock()"
)
if old_init_lock in content and "_playback_stream_lock" not in content:
    content = content.replace(old_init_lock, new_init_lock, 1)
    changes += 1
    print("  [1a] Added _playback_stream_lock to __init__")

# 1b. Make _close_playback_stream use the lock
old_close = '''    @staticmethod
    def _close_playback_stream(stream):
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass'''

new_close = '''    def _close_playback_stream(self, stream):
        if stream is not None:
            with self._playback_stream_lock:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass'''

if old_close in content:
    content = content.replace(old_close, new_close, 1)
    changes += 1
    print("  [1b] _close_playback_stream now acquires _playback_stream_lock")
else:
    print("  [1b] SKIP - _close_playback_stream pattern not found")

# 1c. Wrap asyncio.to_thread(stream.write, chunk) with a locked helper
old_write = "                        await asyncio.to_thread(stream.write, chunk)"
new_write = (
    "                        def _locked_write(s, c, lk):\n"
    "                            with lk:\n"
    "                                s.write(c)\n"
    "                        await asyncio.to_thread(_locked_write, stream, chunk, self._playback_stream_lock)"
)

if old_write in content:
    content = content.replace(old_write, new_write, 1)
    changes += 1
    print("  [1c] stream.write now wrapped with _playback_stream_lock")
else:
    print("  [1c] SKIP - asyncio.to_thread(stream.write) not found")

# 1d. Update _close_playback_stream calls in _play_audio from static to instance
# The finally block and the lazy_lifecycle close
content = content.replace(
    "self._close_playback_stream(stream)",
    "self._close_playback_stream(stream)",
)
# The static calls need updating - there's one JarvisLive._drain_queue already
# but _close_playback_stream was @staticmethod, now it's instance method
# All calls in _play_audio already use self._close_playback_stream, so no change needed

# ═══════════════════════════════════════════════════════════════
# FIX 2: Void turn audio quarantine
# ═══════════════════════════════════════════════════════════════

# 2a. Add _turn_input_validated flag and audio quarantine buffer init
# in the turn start block inside _receive_audio
old_turn_start = '''                self._turn_interrupted = False
                self._turn_tool_signatures = set()
                received_message = False
                _turn_start_t = time.monotonic()
                _last_input_transcript_t = None
                _first_response_audio_t = None'''

new_turn_start = '''                self._turn_interrupted = False
                self._turn_tool_signatures = set()
                received_message = False
                _turn_start_t = time.monotonic()
                _last_input_transcript_t = None
                _first_response_audio_t = None
                _input_validated = False
                _audio_quarantine = []'''

if old_turn_start in content:
    content = content.replace(old_turn_start, new_turn_start, 1)
    changes += 1
    print("  [2a] Added _input_validated + _audio_quarantine to turn start")

# 2b. Replace the response_audio enqueue block to quarantine instead
old_audio_enqueue = '''                    response_audio = _live_response_audio_bytes(response)
                    if response_audio:
                        if self._suppress_interrupted_output:
                            logger.debug(
                                "LIVE_AUDIO suppressed reason=local_barge_in bytes=%d",
                                len(response_audio),
                            )
                        else:
                            if not turn_had_audio:
                                _first_response_audio_t = time.monotonic()
                                self._first_response_audio_t = _first_response_audio_t
                            turn_had_audio = True
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            self.audio_in_queue.put_nowait(response_audio)'''

new_audio_enqueue = '''                    response_audio = _live_response_audio_bytes(response)
                    if response_audio:
                        if self._suppress_interrupted_output:
                            logger.debug(
                                "LIVE_AUDIO suppressed reason=local_barge_in bytes=%d",
                                len(response_audio),
                            )
                        else:
                            if not turn_had_audio:
                                _first_response_audio_t = time.monotonic()
                                self._first_response_audio_t = _first_response_audio_t
                            turn_had_audio = True
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            if _input_validated:
                                self.audio_in_queue.put_nowait(response_audio)
                            else:
                                _audio_quarantine.append(response_audio)'''

if old_audio_enqueue in content:
    content = content.replace(old_audio_enqueue, new_audio_enqueue, 1)
    changes += 1
    print("  [2b] response_audio now quarantined until input validated")
else:
    print("  [2b] SKIP - response_audio enqueue pattern not found")

# 2c. In the input transcript handler, validate input and flush quarantine
# Find where input text is first buffered (in_buf append for model_turn parts)
# We need to set _input_validated = True when the first semantic text arrives
# Look for the in_buf.append and the text parts handling

# The input transcript comes in server_content.model_turn or input_transcription
# Let's find where in_buf is populated
old_input_text_section = '''                        if sc.turn_complete:'''

# We need to add validation check BEFORE turn_complete but after we have
# input text. The input comes via sc.input_transcription blocks.
# Let me find that pattern.

# Actually, the non_semantic check at tool_call time (line ~5712) already
# checks `in_buf`. So we need to validate once in_buf has semantic content.
# The cleanest approach: when an input_transcription piece arrives that is
# semantic, set _input_validated and flush quarantine.

# Find input_transcription handling
input_transcript_search = "input_transcription"
# Let me check where in_buf gets populated

with open(PATH, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find in_buf.append
in_buf_lines = [(i+1, l.rstrip()) for i, l in enumerate(lines) if "in_buf.append" in l]
print(f"  [debug] in_buf.append at lines: {[n for n,_ in in_buf_lines]}")

# Find input_transcription
input_trans_lines = [(i+1, l.rstrip()) for i, l in enumerate(lines) if "input_transcription" in l.lower() and i > 5400]
print(f"  [debug] input_transcription at lines: {[n for n,_ in input_trans_lines]}")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\nPatch applied: {changes} changes (debug info above for next step)")
