# JARVIS Project State

Status: **CANONICAL CURRENT STATE** as of 2026-10-08.

## Verdict

Machine-verifiable recovery and stabilization are complete on the real Windows checkout. The repository is not eligible for an unconditional production GO because owner-operated JL-A10 found a real semantic schedule bug in spoken routine creation: "10 de la noche" was intended as `22:00`, but JARVIS submitted `13:00` to LILITH. JL-A10 therefore remains open pending physical retest of the fix; AUT-8/AUT-9 were not started.

## Verified done

- Real Windows runtime and repository identity established at `C:\JARVIS`.
- Local code commit and remote documentation history reconciled without overwriting either side.
- Gemini Live session, Spanish prompt, tool registration/response path, voice/model precedence, and audio formats verified from code and tests.
- 46 unique declared tools have dispatch paths and schemas.
- Memory authority guards enforce LILITH persistence versus explicit in-process session storage.
- Routine guard enforces recurring/one-shot/immediate routing, turn provenance, and duplicate FunctionCall IDs.
- Routine guard now validates deterministic Spanish time expressions in current-turn routine descriptions before submitting `lilith_routine`, including the JL-A10 `10 de la noche` -> `22:00` regression.
- LILITH HTTP contract is covered for health/runtime/docs/source/Git/commands/memory/Home/approvals; routine persistence uses the command gateway.
- Root pytest discovery is deterministic and ignores runtime snapshots under `tmp/`.
- Automated PyQt offscreen evidence, API/WebSocket tests, secret scan, dependency check, frontend lint/typecheck/build, and production dependency audit run successfully.
- Hosted WebSocket authentication no longer places bearer tokens in the URL.
- Active docs no longer claim the nonexistent cinematic first-run/tour UI or Linux-only canonical development.

## Partial or human-gated

- Real Gemini Live network enumeration was observed from the runtime/test environment, but complete spoken STT/TTS/tool E2E must be owner-operated.
- Real microphone selection, echo cancellation quality, barge-in, device loss/reconnect, Windows display scaling, and 30-minute soak are not machine-certifiable without hardware use.
- JL-A10 physical test is a partial pass / bug found: microphone/runtime active, LILITH connectivity, `lilith_routine` list, recurring routing, create persistence, list after create, delete, and list after delete passed; semantic schedule correctness failed because intended `22:00` was submitted as `13:00`.
- The fixed build still requires owner physical retest. Do not mark JL-A10 complete from automated tests.

## Not started / deferred

- AUT-8 / AUT-9: not started by this recovery.
- LILITH-native wake word/STT/TTS: deferred and not part of the JARVIS production voice pipeline.
- New UI features or redesign: not started.

## Current quality baseline

- Pytest: 502 collected; 425 passed; 77 classified historical-spec skips; 0 failed; 0 errors; 1 third-party Python 3.14 deprecation warning; 10 subtests passed.
- QA runner: 5/5 checks passed, P0=0, P1=0; three P2 debt findings.
- Python dependency consistency: clean.
- Web: ESLint pass, TypeScript pass, Next production build pass, production `npm audit` 0 vulnerabilities. Five high development-only transitive audit findings remain.

See `docs/audits/JARVIS_PROJECT_RECOVERY_2026-10-08.md` for evidence and `docs/TASKS.md` for the only active backlog.
