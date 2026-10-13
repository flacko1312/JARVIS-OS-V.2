# JARVIS Project State

Status: **CANONICAL CURRENT STATE** as of 2026-10-13.

## Verdict

Machine-verifiable recovery and stabilization are complete on the real Windows checkout. JL-A10 is closed after owner-operated spoken validation proved correct `lilith_routine` create/list/delete routing and persistence of `22:00 Europe/Madrid`. Real screen capture, Gemini primary image analysis, and the spoken visual response also passed owner validation. AUT-8/AUT-9 were not started.

## Verified done

- Real Windows runtime and repository identity established at `C:\JARVIS`.
- Local code commit and remote documentation history reconciled without overwriting either side.
- Gemini Live session, Spanish prompt, tool registration/response path, voice/model precedence, and audio formats verified from code and tests.
- 46 unique declared tools have dispatch paths and schemas.
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

## Non-blocking operational validation

- Real microphone selection, echo cancellation quality, barge-in, device loss/reconnect, Windows display scaling, and 30-minute soak are not machine-certifiable without hardware use.
- Camera capture/analysis has not received the same owner-operated physical validation as screen capture.
- Ollama `qwen3-vl:4b` passed an isolated local image smoke, but its position as final fallback in the complete real JARVIS provider chain has not been physically exercised because Gemini primary succeeded.

## Not started / deferred

- AUT-8 / AUT-9: not started by this recovery.
- LILITH-native wake word/STT/TTS: deferred and not part of the JARVIS production voice pipeline.
- New UI features or redesign: not started.

## Current quality baseline

- Pytest: 526 collected; 449 passed; 77 classified historical-spec skips; 0 failed; 0 errors; 1 third-party Python 3.14 deprecation warning; 19 subtests passed.
- QA runner: 5/5 checks passed, P0=0, P1=0; three P2 debt findings.
- Python dependency consistency: clean.
- Web: ESLint pass, TypeScript pass, Next production build pass, production `npm audit` 0 vulnerabilities. Five high development-only transitive audit findings remain.

See `docs/audits/JARVIS_PROJECT_RECOVERY_2026-10-08.md` for evidence and `docs/TASKS.md` for the only active backlog.
