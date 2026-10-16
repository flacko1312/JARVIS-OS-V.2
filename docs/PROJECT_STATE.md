# JARVIS Project State

Status: **CANONICAL CURRENT STATE** as of 2026-10-16.

## Verdict

Machine-verifiable recovery and stabilization are complete on the real Windows checkout. JL-A10 is closed after owner-operated spoken validation proved correct `lilith_routine` create/list/delete routing and persistence of `22:00 Europe/Madrid`. Real screen capture, Gemini primary image analysis, and the spoken visual response also passed owner validation. AUT-8/AUT-9 were not started.

## Verified done

- Real Windows runtime and repository identity established at `C:\JARVIS`.
- Local code commit and remote documentation history reconciled without overwriting either side.
- Gemini Live session, Spanish prompt, tool registration/response path, voice/model precedence, and audio formats verified from code and tests.
- 48 unique declared tools have dispatch paths and schemas.
- Memory authority guards enforce LILITH persistence versus explicit in-process session storage.
- Routine guard enforces recurring/one-shot/immediate routing, turn provenance, and duplicate FunctionCall IDs.
- Routine guard now validates deterministic Spanish time expressions in current-turn routine descriptions before submitting `lilith_routine`, including the JL-A10 `10 de la noche` -> `22:00` regression.
- JL-A10 owner validation passed physically: recurring create/list/delete stayed on `lilith_routine`, persisted `22:00 Europe/Madrid`, and did not route to reminders or immediate Home actions.
- `screen_process` owner validation passed physically for screen capture, `gemini-3.8-flash` analysis, accurate visible-content description, and spoken response.
- The obsolete `gemini-2.5-flash` model and AFC warning regressions are fixed. Bounded cloud 503 handling and the final Ollama fallback are covered automatically; isolated local `qwen3-vl:4b` vision passed.
- LILITH HTTP contract is covered for health/runtime/docs/source/Git/commands/memory/Home/approvals; routine persistence uses the command gateway.
- Root pytest discovery is deterministic and ignores runtime snapshots under `tmp/`.
- Automated PyQt offscreen evidence, API/WebSocket tests, secret scan, dependency check, frontend lint/typecheck/build, and production dependency audit run successfully.
- Hosted WebSocket authentication no longer places bearer tokens in the URL.
- Active docs no longer claim the nonexistent cinematic first-run/tour UI or Linux-only canonical development.
- Gemini voice now starts in `STANDBY` with no Live connection or microphone forwarding. F8 and the conversation button pause/resume the same logical conversation instead of creating a new one.
- Normal completion of a Gemini `session.receive()` turn stays on the same Live connection. Real transport/session failures and `go_away` use bounded silent reconnect with session resumption; rejected/expired handles fall back to the retained local transcript and rolling continuity state.
- F8 pause/resume continuity passed owner-operated physical validation: the user established `88`, paused, resumed, then asked for the previous number multiplied by two and JARVIS answered `176` without a new greeting.
- Persistent logical-conversation continuity is complete and physically validated across full process restarts. The local `memory/conversation_state.json` store uses atomic replacement, bounded recent turns/tool summaries, and a rolling summary; it stores text only, never raw audio or Gemini resumption handles. F8, standby, reconnect, `go_away`, rejected/expired native handles, shutdown, and crashes do not clear it. Only an explicit `new_conversation()` replaces the durable logical conversation.
- Active/restored conversation context has highest precedence and needs no memory tool. `save_memory`/`local_memory_search` are reserved for explicit local-note intent, while LILITH memory tools are reserved for explicit long-term persistence/search. Owner restart validation confirmed ordinary immediate recall uses the restored conversation directly and an explicit local-memory request still invokes `local_memory_search`.
- Native Gemini session resumption remains the first transport-continuity path when a valid process-local handle exists. A clean transport reconstructs context from durable JARVIS state and produces no greeting. With installed `google-genai 2.25.0`, the tested Native Audio preview model/API rejects even minimal initial-history use with API 1007, so the current production compatibility path is compact durable continuity in `system_instruction`; this is not claimed as a permanent Gemini limitation.

## Non-blocking operational validation

- Real microphone selection, echo cancellation quality, barge-in, device loss/reconnect, Windows display scaling, and 30-minute soak are not machine-certifiable without hardware use.
- Camera capture/analysis has not received the same owner-operated physical validation as screen capture.
- Ollama `qwen3-vl:4b` passed an isolated local image smoke, but its position as final fallback in the complete real JARVIS provider chain has not been physically exercised because Gemini primary succeeded.
- Real forced Gemini transport interruption / `go_away` recovery remains pending. Session resumption is covered automatically, but has not yet been physically forced and must not be reported as a physical pass.
- The 24-hour soak has not started and must remain blocked until real transport recovery is physically validated.

## Not started / deferred

- AUT-8 / AUT-9: not started by this recovery.
- LILITH-native wake word/STT/TTS: deferred and not part of the JARVIS production voice pipeline.
- New UI features or redesign: not started.

## Current quality baseline

- Pytest for this block: 589 collected; 509 passed; 77 classified historical-spec skips; 3 known unrelated UI contract failures; 0 errors; 1 third-party Python 3.14 deprecation warning; 19 subtests passed. A clean `HEAD` baseline independently reproduces all three failures: tests expect `MUTED`, `Quit AURORA`, and `ANALYSIS COMPLETE`, while the previously committed Spanish UI shows `SILENCIADO`, `Cerrar AURORA`, and `ANÁLISIS COMPLETADO`.
- QA runner: 5/5 checks passed, P0=0, P1=0; three P2 debt findings.
- Python dependency consistency: clean.
- Web: ESLint pass, TypeScript pass, Next production build pass, production `npm audit` 0 vulnerabilities. Five high development-only transitive audit findings remain.

See `docs/audits/JARVIS_PROJECT_RECOVERY_2026-10-08.md` for evidence and `docs/TASKS.md` for the only active backlog.
