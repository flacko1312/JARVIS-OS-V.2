# BLOCK 06 — ROBUSTNESS, RECOVERY & PERSISTENCE

**Date:** 2026-10-15  
**Repository:** `C:\JARVIS`  
**Audited HEAD:** `1c05b3edfbe3345cae9a5f8aa699d306bc7a2010` plus preserved working-tree changes  
**Scope note:** Avatar, visemes and lip-sync are **DEFERRED BY USER — OUT OF CURRENT SCOPE**.

## 1. Result

Block 6 is complete for automated and static validation. Two in-scope resource-cleanup defects were found and fixed:

1. Browser sessions closed Playwright but left their event-loop worker thread alive. Startup failures could also return before the failed worker had terminated.
2. `WebSocketClient.close()` could wait indefinitely when its bounded event queue was full and no sender was draining it.

Focused robustness suite after the fixes:

| Run | Passed | Failed | Skipped | Warnings |
|---|---:|---:|---:|---:|
| Live/reconnect/persistence/LILITH/Ollama/Codex + Block 6 | 378 | 0 | 10 | 1 |
| Browser/files/Gmail/hosted API/camera-startup helpers | 202 | 0 | 0 | 1 |

The warning in both runs is the same third-party `google.genai.types` Python 3.17 deprecation warning. Counts must not be added because the runs overlap with the later full suite.

## 2. Failure-scenario matrix

These are automated simulations or isolated smoke checks unless explicitly marked physical.

| # | Scenario | Result | Evidence / limitation |
|---:|---|---|---|
| 1 | Gemini operational | IMPLEMENTED + AUTOMATED PASS | Live config/session tests use deterministic fake sessions; real network/voice remains physical. |
| 2 | Gemini timeout | IMPLEMENTED + AUTOMATED PASS | Recoverable timeout classification and bounded reconnect tests pass. |
| 3 | Gemini disconnected | IMPLEMENTED + AUTOMATED PASS | Disconnect, GoAway and resumption-handle paths pass. |
| 4 | WebSocket broken | IMPLEMENTED + AUTOMATED PASS | Hosted API disconnect cleanup and sender cancellation pass. |
| 5 | WebSocket recovery | PARTIALLY IMPLEMENTED | Client reconnection is an external/browser concern; server-side cleanup is automated. Physical reconnect remains required. |
| 6 | Ollama operational | IMPLEMENTED + AUTOMATED PASS | Local vision request/config response simulated. Real local model is not claimed. |
| 7 | Ollama offline | IMPLEMENTED + AUTOMATED PASS | Eligible local-provider failures fall back or return explicit offline result. |
| 8 | LILITH operational | IMPLEMENTED + AUTOMATED PASS | Client/runtime/tool paths simulated with valid responses. |
| 9 | LILITH offline | IMPLEMENTED + AUTOMATED PASS | Connection/timeout/offline result paths pass. |
| 10 | LILITH recovery | IMPLEMENTED + AUTOMATED PASS | Retry count and exponential delays are bounded by `max_retries`; live service recovery remains physical. |
| 11 | Home Assistant offline | IMPLEMENTED + AUTOMATED PASS | LILITH-owned home action failures are surfaced without false success. Real HA remains physical. |
| 12 | Browser failure | IMPLEMENTED + AUTOMATED PASS | Timeout/error handling and new startup-cleanup regression tests pass. |
| 13 | Missing file | IMPLEMENTED + AUTOMATED PASS | File controller/processor missing-path handling passes. |
| 14 | Missing camera | IMPLEMENTED + AUTOMATED PASS | Vision preview unavailable-device behavior is simulated; hardware test remains physical. |
| 15 | Microphone unavailable | PARTIALLY IMPLEMENTED | Live audio error/cleanup paths exist; actual missing-device behavior is **PHYSICAL TEST REQUIRED**. |
| 16 | Gmail unauthenticated | IMPLEMENTED + AUTOMATED PASS | Sign-in assistance timeout/unauthenticated paths pass; real account flow remains physical. |
| 17 | Codex failure | IMPLEMENTED + AUTOMATED PASS | Missing command, timeout and non-zero result paths pass. |
| 18 | Claude Code failure | IMPLEMENTED + AUTOMATED PASS | Missing command and failure reporting pass; real CLI/auth remains physical. |
| 19 | Tool exception | IMPLEMENTED + AUTOMATED PASS | Tool exceptions become bounded error responses and do not crash the Live loop. |
| 20 | JARVIS shutdown | IMPLEMENTED + AUTOMATED PASS | Shutdown from all conversation states, during backoff and after persistence passes. |
| 21 | JARVIS restart/reopen | IMPLEMENTED + AUTOMATED PASS | Durable context restore, corrupt-state handling and clean restart simulations pass. Real packaged restart is physical. |

## 3. Retry, timeout and resource audit

### Gemini Live

- Maximum reconnect attempts: 5 (`MAX_LIVE_RECONNECT_ATTEMPTS`).
- Backoff is bounded and interruptible by shutdown/conversation stop.
- A stable connection resets the attempt counter.
- `asyncio.TaskGroup` owns realtime send, receive, playback and microphone tasks, so peer tasks are cancelled when a task fails.
- Durable continuity is saved before shutdown and survives exhausted reconnect attempts.

### LILITH

- `httpx.AsyncClient` has a configured timeout (default 10 seconds).
- Connect and timeout errors retry `1 + max_retries` times with delays `1, 2, 4, 5...` seconds (capped at 5).
- The client supports explicit async close/context-manager cleanup.
- HTTP/auth/permission/domain failures do not enter uncontrolled retry loops.

### Browser and WebSocket fixes

- `actions/browser_control.py`: startup has a 20-second bound, propagates initialization failure, joins a failed worker, stops the event loop on close, joins the worker with a 10-second bound, and clears references.
- `api/websocket_client.py`: close now makes room for the sentinel when needed and uses non-blocking insertion.
- Four regression tests cover normal browser close, failed browser startup, full WebSocket queue close and sender termination.

### Subprocesses, threads and handles

- Code execution helpers use bounded `subprocess.run(..., timeout=...)` paths and report timeouts.
- Several `Popen` uses intentionally launch user applications/URLs and do not represent child jobs owned for later termination.
- The browser worker defect was the concrete stale background-thread issue found in exercised code and is fixed.
- Static inspection found many broad exception handlers in optional integrations. Most are best-effort UI/device probes, but they reduce diagnostics and remain technical debt.

## 4. Risks and limitations

- Real microphone, camera, speaker, browser profile, Gmail login, Gemini network, Ollama process, LILITH server and Home Assistant recovery cannot be proven by isolated tests.
- The desktop runner is a daemon thread. Normal UI shutdown is tested at the controller level, while packaged-process exit remains a physical test.
- Some optional/background integrations use broad `except Exception` handlers. No infinite retry loop was observed in the audited core paths, but suppressed diagnostics can make field failures harder to investigate.
- There is no automated long-duration soak with process RSS/handle sampling; therefore absence of a slow memory leak is not claimed.

## 5. Changed files

- `actions/browser_control.py` — deterministic startup failure and worker-loop shutdown.
- `api/websocket_client.py` — non-blocking close of a full event queue.
- `tests/test_block6_robustness_recovery.py` — four regression tests.
- `docs/audits/BLOCK_05_HUD_STATES_AVATAR.md` — scope clarification only; avatar code/assets untouched.

## 6. Physical follow-up

All remaining hardware, credentials and real-service checks are consolidated in `PHYSICAL_TEST_PLAN.md`. No physical result is claimed by this block.
