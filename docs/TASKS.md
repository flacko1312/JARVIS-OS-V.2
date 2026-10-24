# AURORA / JARVIS Windows — Tasks

Status: **CANONICAL ACTIONABLE BACKLOG** as of 2026-10-24. Do not use historical prompts or audit findings as a second task system.

## Global coordination

AURORA is the active Windows adapter for LILITH CORE. JARVIS Ubuntu Headless is maintained separately on `server-lilith`. The final 24-hour ecosystem soak is deferred until AURORA, Ubuntu Headless, Monitor and the integration configuration are all frozen. Continue Windows stabilization now; do not treat partial soak evidence as final certification.

## Current voice stabilization state — 2026-10-23

Status: **PARTIALLY CLOSED / ONE PHYSICAL CHECK REMAINS**.

- Natural conversational pause handling: **PHYSICAL PASS** at `JARVIS_LIVE_VAD_SILENCE_MS=2500`. Keep this value unless owner testing again shows premature cuts.
- Live input transcript assembly regression (artificial intra-word spaces): **PHYSICAL PASS** for the observed failure mode.
- Pending repeated-user-request suppression: **PHYSICAL PASS**.
- Spotify/background speech filtering: current mode `shadow_v4`; automatic/offline replay gives **0 false gate-open sequences**, but final real spoken-ad/music acceptance is still **PENDING**.
- Rollback remains `JARVIS_SPOTIFY_FILTER_MODE=off`; do not alter the now-good 2500 ms conversation timing while diagnosing Spotify.

Next voice test: run a real Spotify spoken advertisement or voice-heavy track for 30–60 seconds while the owner stays silent. Expected result is zero user turns/replies/tools. Then speak one normal question over Spotify and confirm a single complete turn without pausing playback.
## Silent audit — 2026-10-23

Status: **PASS / NO NEW SILENT BLOCKER FOUND**.

- Full suite baseline: 1235 passed, 93 skipped, 0 failures.
- Additional reconnect/continuity/device-recovery/Windows-browser guard suite: 260 passed, 0 failures.
- Python compile/dependency checks and web lint/typecheck/production build: PASS.
- Reviewed shadow_v4 runtime window: 0 errors and 0 warnings.
- The old 29-item physical plan is retained as historical certification coverage, but it is no longer the actionable backlog. Use this file plus AURORA_SILENT_AUDIT_2026-10-23.md for current closure order.

Current critical closure order for AURORA: **Spotify v4 physical acceptance -> final barge-in/audio-device recovery -> real Gemini transport recovery -> freeze AURORA**. The global soak comes later, after Ubuntu Headless, Monitor and the integration baseline are also frozen. Keep the 2500 ms turn timing frozen.

## Current validation state

### Gemini Live transport recovery — next required physical validation

Status: **PENDING / NOT PHYSICALLY FORCED**.

F8 pause/resume and immediate conversational continuity are physically validated. The owner established `88`, paused and resumed with F8, and JARVIS correctly answered `176` when asked for the previous number multiplied by two. Normal multi-turn operation stays on one Live connection and resume produces no new greeting.

The next task is to establish context in an active conversation, force a real recoverable network/Live interruption, observe `RECONNECTING` and return to `LISTENING`, then verify the prior immediate context without a greeting, traceback, or LILITH-memory workaround. Do not mark session resumption as physically passed until this succeeds. JL-A10 is already closed; this transport-recovery check is a separate remaining physical gate. The final 24-hour soak stays deferred until the whole ecosystem is frozen.

### AUT-9 — subsequent autonomous work block

Status: **NOT STARTED / NOT AUTHORIZED**.

Do not start AUT-9 until explicitly requested and the transport-recovery gate above is complete.

## Closed

### Persistent logical conversation continuity

Status: **CLOSED / PHYSICAL RESTART ACCEPTANCE PASS**.

Durable text continuity now survives F8/standby, transport reconnects, `go_away`, rejected or expired native resumption handles, process restart, and crash recovery. State is written atomically with bounded recent turns, tool-result summaries, and a rolling summary; raw audio and opaque Gemini handles are never persisted. Only explicit `new_conversation()` clears/replaces this logical conversation.

Physical acceptance across real restarts confirmed STANDBY startup, normal Live/audio operation, compact continuity restoration without greeting or API 1007/1008 failure, direct recall from the active conversation without memory-search tools, and preserved explicit `local_memory_search` behavior. The current `google-genai 2.25.0` plus tested Native Audio preview model/API rejects initial-history replay with API 1007, so this configuration uses compact durable context in `system_instruction` after native resumption is unavailable or rejected.

The full-suite baseline retains three unrelated UI localization-contract failures already reproducible on clean `HEAD`; they are not part of this block.

### JL-A10 — owner-operated spoken Gemini Live certification

Status: **CLOSED / PHYSICAL E2E PASS**.

Owner physical evidence confirmed microphone/runtime activity, LILITH connectivity, exclusive `lilith_routine` create/list/delete routing, and correct persistence of `22:00 Europe/Madrid` from "10 de la noche". No incorrect `reminder` or `lilith_home_action` route was observed.

### Screen vision — owner-operated validation

Status: **SCREEN PHYSICAL E2E PASS; CAMERA AND OLLAMA FAILOVER STILL HUMAN-GATED**.

The owner invoked `screen_process` through the real runtime. JARVIS captured a 142,430-byte screen image, selected `gemini-3.8-flash`, produced a description matching the visible ChatGPT and AURORA windows, and spoke the result. The obsolete `gemini-2.5-flash` and AFC warning regressions are fixed. Automated tests cover bounded Gemini 503 handling and the final local Ollama fallback; an isolated `qwen3-vl:4b` image smoke passed. The complete real provider chain has not physically exercised Ollama because Gemini primary succeeded.

There is no open P1 feature task. Perform the transport-recovery validation above before any soak; otherwise continue only with the stabilization backlog or a separately authorized supervised validation.

## Stabilization backlog

1. **TD-002 / P2** — migrate secondary action/agent modules from deprecated `google.generativeai` to `google.genai`, one tested module family at a time.
2. **TD-003 / P2** — reduce broad exception swallowing in runtime-critical paths and add structured error codes without altering user-facing behavior.
3. **TD-004 / P2** — separate legacy local JSON memory compatibility from active prompt construction after a migration/deprecation plan is approved.
4. **TD-005 / P2** — pin or constrain remaining `latest` frontend dependencies and resolve development-only audit advisories without a breaking downgrade.
5. **TD-006 / P2** — split `main.py` and `ui.py` only as a dedicated refactor with behavioral parity tests; no UI redesign.
6. **TD-007 / P3** — improve current GUI accessibility names, scaling coverage, and theme-token consistency.

## Explicitly out of scope

- AUT-8 / AUT-9.
- LILITH-native production voice.
- New agents, schedulers, memory stores, Home Assistant clients, or GUI redesign.
