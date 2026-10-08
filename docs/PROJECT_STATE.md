# JARVIS Project State

Status: **CANONICAL CURRENT STATE** as of 2026-10-08.

## Verdict

Machine-verifiable recovery and stabilization are complete on the real Windows checkout. The repository is not eligible for an unconditional production GO because real microphone/Gemini spoken interaction, device audio behavior, and safe owner-operated routine lifecycle remain human gates. JL-A10 therefore remains open; AUT-8 was not started.

## Verified done

- Real Windows runtime and repository identity established at `C:\JARVIS`.
- Local code commit and remote documentation history reconciled without overwriting either side.
- Gemini Live session, Spanish prompt, tool registration/response path, voice/model precedence, and audio formats verified from code and tests.
- 46 unique declared tools have dispatch paths and schemas.
- Memory authority guards enforce LILITH persistence versus explicit in-process session storage.
- Routine guard enforces recurring/one-shot/immediate routing, turn provenance, and duplicate FunctionCall IDs.
- LILITH HTTP contract is covered for health/runtime/docs/source/Git/commands/memory/Home/approvals; routine persistence uses the command gateway.
- Root pytest discovery is deterministic and ignores runtime snapshots under `tmp/`.
- Automated PyQt offscreen evidence, API/WebSocket tests, secret scan, dependency check, frontend lint/typecheck/build, and production dependency audit run successfully.
- Hosted WebSocket authentication no longer places bearer tokens in the URL.
- Active docs no longer claim the nonexistent cinematic first-run/tour UI or Linux-only canonical development.

## Partial or human-gated

- Real Gemini Live network enumeration was observed from the runtime/test environment, but complete spoken STT/TTS/tool E2E must be owner-operated.
- Real microphone selection, echo cancellation quality, barge-in, device loss/reconnect, Windows display scaling, and 30-minute soak are not machine-certifiable without hardware use.
- Real LILITH routine create/list/delete and one safe Home Assistant action require owner approval because they mutate authoritative external state.
- The active runtime was restarted from `C:\JARVIS\.venv\Scripts\jarvis.exe` after the recovery commits. Its process tree resolves to the same checkout, `import main` resolves to `C:\JARVIS\main.py`, status is online, Gemini model discovery succeeded, and the LILITH monitor reported online. Spoken/audio behavior remains a human gate.

## Not started / deferred

- AUT-8: not started by this recovery.
- LILITH-native wake word/STT/TTS: deferred and not part of the JARVIS production voice pipeline.
- New UI features or redesign: not started.

## Current quality baseline

- Pytest: 502 collected; 425 passed; 77 classified historical-spec skips; 0 failed; 0 errors; 1 third-party Python 3.14 deprecation warning; 10 subtests passed.
- QA runner: 5/5 checks passed, P0=0, P1=0; three P2 debt findings.
- Python dependency consistency: clean.
- Web: ESLint pass, TypeScript pass, Next production build pass, production `npm audit` 0 vulnerabilities. Five high development-only transitive audit findings remain.

See `docs/audits/JARVIS_PROJECT_RECOVERY_2026-10-08.md` for evidence and `docs/TASKS.md` for the only active backlog.
