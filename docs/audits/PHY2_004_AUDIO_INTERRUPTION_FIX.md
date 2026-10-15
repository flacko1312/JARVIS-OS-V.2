# PHY2-004 — Live audio / interruption fix

**Date:** 2026-10-15  
**Repository:** `C:\JARVIS`  
**Starting HEAD:** `c2e838fff9fab960684dbc3fe38f260a93f05e85`  
**Physical reproduction:** FAILED before this change; NOT RERUN during this automated pass  
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
