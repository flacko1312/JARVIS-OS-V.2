# JARVIS Project State

Status: **CANONICAL CURRENT STATE** as of 2026-10-08.

## Verdict

Machine-verifiable recovery and stabilization are complete on the real Windows checkout. JL-A10 owner-operated spoken Gemini Live and persistent routine lifecycle certification is PASS / CLOSED on Git HEAD `bbe95a8d3abcdbbab130e46a3ac336bd47f5c374`. The earlier "10 de la noche" `22:00` -> `13:00` routine defect is fixed and physically retested. AUT-8/AUT-9 were not started.

## Verified done

- Real Windows runtime and repository identity established at `C:\JARVIS`.
- Local code commit and remote documentation history reconciled without overwriting either side.
- Gemini Live session, Spanish prompt, tool registration/response path, voice/model precedence, and audio formats verified from code and tests.
- 46 unique declared tools have dispatch paths and schemas.
- Memory authority guards enforce LILITH persistence versus explicit in-process session storage.
- Routine guard enforces recurring/one-shot/immediate routing, turn provenance, and duplicate FunctionCall IDs.
- Routine guard now validates deterministic Spanish time expressions in current-turn routine descriptions before submitting `lilith_routine`, including the JL-A10 `10 de la noche` -> `22:00` regression.
- JL-A10 physical retest passed: interface ready, 87 LILITH context facts loaded, connected, microphone stream open, receive loop running, playback running, `lilith_routine` create/list/delete/list confirmed, and the spoken routine create submitted `22:00 Europe/Madrid`.
- LILITH HTTP contract is covered for health/runtime/docs/source/Git/commands/memory/Home/approvals; routine persistence uses the command gateway.
- Root pytest discovery is deterministic and ignores runtime snapshots under `tmp/`.
- Automated PyQt offscreen evidence, API/WebSocket tests, secret scan, dependency check, frontend lint/typecheck/build, and production dependency audit run successfully.
- Hosted WebSocket authentication no longer places bearer tokens in the URL.
- Active docs no longer claim the nonexistent cinematic first-run/tour UI or Linux-only canonical development.

## Non-blocking operational validation

- Optional robustness checks such as mute/unmute, interruption/barge-in depth, device loss/reconnect recovery, display scaling sweeps, and long soak remain useful operational validation. They are not blockers for the core JL-A10 spoken Gemini Live / persistent routine lifecycle gate.

## Not started / deferred

- AUT-8 / AUT-9: not started by this recovery.
- LILITH-native wake word/STT/TTS: deferred and not part of the JARVIS production voice pipeline.
- New UI features or redesign: not started.

## Current quality baseline

- Windows pytest at JL-A10 retest HEAD: 429 passed; 77 skipped; 0 failed; 0 errors; 1 warning; 15 subtests passed.
- QA runner: 5/5 checks passed, P0=0, P1=0; three P2 debt findings.
- Python dependency consistency: clean.
- Web: ESLint pass, TypeScript pass, Next production build pass, production `npm audit` 0 vulnerabilities. Five high development-only transitive audit findings remain.

See `docs/audits/JARVIS_PROJECT_RECOVERY_2026-10-08.md` for evidence and `docs/TASKS.md` for the only active backlog.
