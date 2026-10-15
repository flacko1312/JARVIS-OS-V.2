# PHY2-004 — Live audio / interruption fix

**Date:** 2026-10-15  
**Repository:** `C:\JARVIS`  
**Starting HEAD:** `c2e838fff9fab960684dbc3fe38f260a93f05e85`  
**Physical reproduction:** first fix restored interruption; second physical run FAILED on ambient false positives; NOT RERUN after the second fix
**Avatar:** untouched

## Audit result

PHY2-004 exposed two separate defects.

### A. Recoverable Live disconnects could truncate audible output

The historical log only retained `error=RecoverableLiveDisconnect`; it discarded the exception message, close classification and queue/playback state. Consequently the old entries cannot be classified retrospectively as provider GoAway, network reset or provider close with certainty.

The code audit nevertheless confirmed a deterministic truncation path:

1. `_receive_audio()` raised immediately on a Gemini `go_away`, before processing any audio or `server_content` carried by that response.
2. Any recoverable exception ended the session `TaskGroup`, cancelling playback.
3. The reconnect `finally` replaced `audio_in_queue` and `out_queue`, abandoning queued audio without an explicit cleanup record.
4. A boolean remembered that *some* earlier GoAway had attempted resumption. It was not associated with the actual handle, so a later independent GoAway could unnecessarily discard a newly issued valid handle.

The fix processes the complete response first. A GoAway received during output is held until turn completion and a playback drain bounded to 30 seconds; an idle GoAway still reconnects immediately. Abrupt disconnects explicitly drain stale queues before a new session. Resumption fallback is now keyed to the specific handle, while bounded exponential retry remains 1/2/4/8/16 seconds with five attempts and a 30-second delay ceiling.

Sanitized logs now record category (`provider_goaway`, `provider_close`, `network`, `timeout` or `transport`), exception type, close code when present, bounded single-line detail, handle presence, active-playback state and queue sizes. They never log credentials, resumption-handle values or audio content.

### B. Native spoken interruption was locally blocked

The microphone callback explicitly discarded every input chunk while `_is_speaking` was true. Therefore “Para”, “stop” and natural speech could not reach Gemini while JARVIS audio was playing. This was the confirmed root cause of failed barge-in.

The microphone now stays upstream during Gemini playback unless the user has muted it. Live configuration explicitly selects `START_OF_ACTIVITY_INTERRUPTS`. When Gemini returns `server_content.interrupted`, JARVIS flushes queued stale output, clears SPEAKING and returns the UI to LISTENING. Repeated interruption is idempotent and creates no extra task. There is no string-only “Para” hack; provider-native interruption is primary.

## Files changed

- `main.py`
- `tests/test_phy2_004_audio_interruption.py`
- `docs/audits/PHY2_004_AUDIO_INTERRUPTION_FIX.md`

No avatar file or unrelated dirty/untracked path was changed.

## Tests added

`tests/test_phy2_004_audio_interruption.py` contains 13 focused tests:

- disconnect during active playback retains a network diagnostic category;
- provider GoAway waits for turn/playback drain;
- reconnect uses the latest valid resumption handle;
- unavailable resumption retains local continuity;
- one Live runner owns reconnects;
- retry count/backoff stay bounded;
- stale playback/input queues are cleaned;
- microphone audio is forwarded during model playback;
- provider interruption flushes output and transitions to LISTENING;
- repeated interruption is idempotent and creates no tasks;
- configuration requests native start-of-activity interruption;
- intentional standby is not a recoverable disconnect;
- diagnostics expose close type without payload logging.

## Automated evidence

- Focused PHY2-004 tests: **13 passed, 1 warning**.
- Relevant Live/audio/context tests: **252 passed, 1 warning, 13 subtests passed**.
- Complete suite: **1085 passed, 93 skipped, 1 warning, 46 subtests passed** in 31.91 seconds.
- `compileall`: **PASS**.
- `git diff --check`: **PASS** (only pre-existing line-ending notices).

The warning is the existing Google GenAI Python 3.17 deprecation warning.

## Expected before/after behavior

Before: output suppressed the mic; provider interruption could not happen. GoAway/reconnect could cancel playback and silently abandon queued chunks; logs could not distinguish the trigger.

After: user speech continues to Gemini during output, Gemini's native interruption clears stale output and returns to listening, GoAway during a completed response allows bounded drain, abrupt disconnect cleanup is explicit, and each reconnect has actionable sanitized diagnostics with a single runner owner.

## Still requires physical validation

Automated tests cannot prove acoustic echo handling, actual microphone capture, speaker cancellation, provider VAD behavior, perceived cut-free playback, or real network/provider close codes. PHY2-004 must be repeated with the real microphone, speaker/headphones and Gemini Live service. LILITH health is independent and should remain HTTP 200, but it is not evidence that the Gemini transport is healthy.

## Exact physical repeat procedure

1. Start JARVIS from this checkout and begin one Live conversation. Record HEAD and the test start time.
2. Prefer headphones for the first pass; repeat once on speakers to expose echo/feedback behavior.
3. Ask for a response lasting at least 30–45 seconds. Verify it completes without a spontaneous cut.
4. During a second long response, say “Para” clearly after 5–10 seconds. PASS requires playback to stop promptly and the UI to leave SPEAKING for LISTENING without stopping the conversation.
5. Repeat with “stop”, then interrupt naturally with a new question. The new question must reach Gemini while old audio is playing; no duplicate reply or overlapping audio is allowed.
6. Interrupt twice in quick succession. Verify no deadlock, duplicate session/reconnect or permanent SPEAKING state.
7. Continue with a contextual follow-up to prove continuity. Change voice once and repeat one interruption.
8. Leave the conversation active for at least 10 minutes and request several long replies. Record any audible truncation timestamp exactly.
9. End via the normal standby control. Confirm this intentional stop produces no recoverable-disconnect error or reconnect loop.
10. Inspect `logs/jarvis.log` for the recorded interval. For every disconnect, capture the sanitized `category`, `close_code`, `detail`, resumption flag and queue counts. PASS requires one reconnect sequence per real disconnect, bounded attempts, no overlapping reconnect owner, and successful continuity with either `resumption=True` or local-continuity fallback.

Do not alter the Windows audio configuration mid-case unless running a separately recorded device-loss test.

## Second physical finding — false barge-in from ambient noise

### Observed evidence

The first fix successfully restored full-duplex capture and native Gemini interruption, but the physical run logged seven `provider_interruption` events between 16:53:03 and 16:54:09. Passing traffic and ordinary room sounds could stop playback. Conversation continuity remained correct.

### Root cause

Gemini Live was configured with `START_OF_ACTIVITY_INTERRUPTS` and high start sensitivity. After the first fix, every microphone frame was forwarded during playback. Native provider interruption is activity-driven; by the time `server_content.interrupted` arrives, Gemini has already accepted the acoustic activity. There was no local confirmation that the activity resembled sustained human speech, nor any comparison with JARVIS's own playback. Therefore a guard placed only on the returned provider event would be too late.

### Second-fix architecture

The microphone remains open and captures continuously. Outside playback, microphone audio remains unchanged. During playback only, `SpeechAwareBargeInGate` temporarily retains a maximum 320 ms in-memory pre-roll and evaluates each 64 ms frame using:

- adaptive RMS noise floor and minimum energy;
- consecutive speech-like duration, requiring 160 ms and normally accepting at about 192 ms;
- crest factor for impacts/keyboard transients;
- zero-crossing rate, spectral centroid and low-frequency ratio for traffic/rumble;
- spectral flatness for broadband environmental noise;
- a bounded spectral fingerprint of recent JARVIS output for playback-leakage rejection.

After confirmation, the pre-roll and subsequent frames are forwarded to Gemini, which remains the authority that emits the native interruption event. This preserves natural questions and “Para”/“stop” without keyword matching. Rejected activity never reaches provider VAD while JARVIS is speaking. No raw audio is logged or persisted; audio/pre-roll exists only in bounded process memory.

Sanitized diagnostics now produce debounced records shaped as:

- `BARGE_IN candidate ...`
- `BARGE_IN rejected reason=<classification> ...`
- `BARGE_IN accepted ...`

They contain only duration, normalized RMS, adaptive noise floor and echo-similarity values.

### Second-fix files changed

- `core/audio_barge_in.py` — local speech-aware gate.
- `main.py` — capture/playback integration and diagnostics.
- `tests/test_phy2_004_audio_interruption.py` — full-duplex test updated for confirmed speech.
- `tests/test_phy2_004_speech_gate.py` — 14 deterministic speech/noise tests.
- `docs/audits/PHY2_004_AUDIO_INTERRUPTION_FIX.md` — this finding and retest boundary.

### Second-fix automated evidence

- Focused PHY2-004 suites: **27 passed, 1 warning**.
- Live/audio/QA regression: **297 passed, 1 warning, 13 subtests passed**.
- Complete suite: **1099 passed, 93 skipped, 1 warning, 46 subtests passed** in 31.61 seconds.
- `compileall`: **PASS**.
- `git diff --check`: **PASS** apart from pre-existing line-ending notices.

The 14 new gate tests cover normal/short spoken interruption, natural question, impulse, repeated ambient noise, car-like noise, keyboard transients, speaker leakage, sustained speech, sub-250 ms acceptance, duplicate prevention, context preservation, listening passthrough, mute and reset/standby behavior. Physical acoustics remain unverified.

### Updated physical retest

1. Record the new HEAD, start time, selected microphone/output device and whether headphones or speakers are used.
2. Start one Live conversation and request a 30–45 second answer.
3. While JARVIS speaks, remain silent and independently create each sound: pass/record a car outside, move a chair, type several keys, close a door normally, tap the desk once and make two short bumps. None may stop playback.
4. Leave ordinary room/background noise present for at least one complete long answer. It must not accumulate into a false interruption.
5. With speakers, request another long answer and do not speak. JARVIS's own voice must not self-interrupt. Repeat at the normal volume and once slightly louder, without exceeding a safe listening level.
6. During separate long answers say “Para”, “stop”, and a natural new question. Each real utterance must interrupt promptly; target perceived latency is below 500 ms and automated local confirmation is about 192 ms.
7. Begin once softly and once at normal speaking level. Record any failure to accept real speech; do not compensate by shouting.
8. Interrupt twice in quick succession. Require one flush/response path, no overlapping audio, duplicate task or stuck SPEAKING state.
9. Ask a contextual follow-up after interruption. It must use the preceding conversational context.
10. Toggle mute while JARVIS speaks: muted microphone activity must do nothing. Unmute and verify a real spoken interruption works again.
11. End through standby. Require no recoverable-disconnect classification or reconnect loop.
12. Inspect the exact log interval. Ambient cases should show debounced `BARGE_IN rejected` entries and no corresponding `LIVE_AUDIO interrupted`; real speech should show `candidate`, one `accepted`, then one provider interruption. No raw audio or spoken contents should appear.
