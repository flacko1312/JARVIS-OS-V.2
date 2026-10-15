# PHY2-005 — Microphone hot-recovery fix

**Date:** 2026-10-15
**Repository:** `C:\JARVIS`
**Starting HEAD:** `f8782f094eaf01f2072a54f9d6370d7e0b591f6e`
**Physical microphone result before fix:** FAIL
**Physical output result:** PASS
**Physical retest after fix:** NOT PERFORMED

## Confirmed root cause

`JarvisLive._listen_audio()` created exactly one `sounddevice.InputStream` inside the Gemini Live session TaskGroup. It checked only shutdown/standby flags. When Windows disabled the active input, PortAudio could leave the Python stream/task alive but stop delivering callbacks. Because no exception was raised and callback liveness was not monitored, the worker remained permanently silent after the device returned.

F8 appeared to repair it because standby tears down the entire Live TaskGroup; starting again constructs a new `InputStream`. Gemini reconnection was incidental and is not required to recover a local microphone.

## Implementation

The single capture worker now owns a recoverable inner InputStream lifecycle:

- detects `stream.active=False`, property/open errors, or no callback for 2.5 seconds;
- closes only the failed local stream;
- clears queued stale microphone chunks;
- resolves the current Windows/default input again on every attempt;
- reopens with bounded cooperative backoff: 0.5, 1, 2, 4, 8, then at most 10 seconds;
- confirms recovery only after three valid callbacks;
- safely adopts a changed valid Windows default input device;
- keeps the Gemini session, playback task, conversation ID and durable context intact;
- uses a single worker lock, so recovery cannot create duplicate capture workers;
- exits recovery promptly when standby or shutdown clears the conversation request.

Sanitized logs now include:

- `AUDIO_INPUT device_lost` with exception class, bounded/redacted detail, prior device ID and stale chunk count;
- `AUDIO_INPUT recovery_wait` with attempt and delay;
- `AUDIO_INPUT recovered` with device ID/name, whether the default changed and attempt count.

The UI reports one Spanish unavailable notice per loss epoch and one recovery notice. No raw audio, credentials or captured speech is logged.

## Output-device audit

The confirmed physical output test already passed. The output stream remained usable after Windows restored the device. Its playback task has a separate lifecycle and does not share the silent-callback defect: output is driven by explicit `write()` calls rather than waiting for input callbacks. No output production code was changed. A deterministic regression verifies that the same output stream/worker delivers queued audio before and after a simulated backend toggle without reopening or duplicating the worker.

## Files changed

- `main.py`
- `tests/test_phy2_005_device_recovery.py`
- `docs/audits/PHY2_005_DEVICE_RECOVERY_FIX.md`

No avatar file or unrelated dirty/untracked path was modified.

## Tests added

The 12 deterministic tests cover:

1. microphone loss, restoration and automatic recreation without F8;
2. silent/stalled callback detection;
3. bounded recovery backoff;
4. safe adoption of a replacement Windows default input;
5. duplicate microphone-worker prevention;
6. standby cancellation during recovery;
7. shutdown cancellation during recovery;
8. repeated disappearance with one worker and increasing delay;
9. stale microphone queue cleanup;
10. conversation/session-context preservation;
11. output loss/restoration behavior with one stream;
12. single Live/output TaskGroup ownership.

## Automated evidence

- Focused device recovery: **12 passed, 1 warning**.
- Live/audio/QA regression: **309 passed, 1 warning, 13 subtests passed**.
- Complete suite: **1111 passed, 93 skipped, 1 warning, 46 subtests passed** in 33.86 seconds.
- `compileall`: PASS.
- `git diff --check`: PASS apart from pre-existing line-ending notices.

The warning is the existing Google GenAI Python 3.17 deprecation warning. Automated evidence does not certify Windows/PortAudio hardware behavior.

## Physical retest instructions

1. Record HEAD, start time and the current Windows default input/output device names.
2. Start JARVIS and one Live conversation. Ask a short question to prove microphone capture and context.
3. Disable the active microphone in Windows while leaving JARVIS and the Live conversation running.
4. Wait at least 12 seconds. JARVIS must remain alive with no reconnect storm. Expect one unavailable UI notice and bounded `AUDIO_INPUT recovery_wait` entries, not a tight loop.
5. Re-enable the same microphone without pressing F8. Within the current backoff window (normally at most 10 seconds), expect `AUDIO_INPUT recovered` and the UI recovery notice.
6. Speak a new question. JARVIS must hear and answer without standby, restart or a second Live session.
7. Ask a contextual follow-up referring to step 2. Context must remain intact.
8. Disable and restore the microphone twice more. Require one capture worker and one recovery sequence per loss, with no duplicate responses or input frames.
9. Disable the original microphone, select another valid device as the Windows default, and keep the original disabled. JARVIS should adopt the replacement; verify `default_changed=True` and successful speech.
10. Disable the microphone again, then press F8 to enter standby while recovery is waiting. No further retry should occur after standby.
11. Restart the conversation, disable the microphone, then quit JARVIS while recovery waits. The process must exit without hanging.
12. Reconfirm output only as a regression: disable/re-enable the output device and verify speech resumes, but treat this as already-passing behavior unless it regresses.

PASS requires automatic microphone recovery without F8, bounded logs/retries, no duplicate worker/session, no stale input, preserved context and clean standby/shutdown cancellation.
