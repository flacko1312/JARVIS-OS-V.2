# JARVIS Tasks

Status: **CANONICAL ACTIONABLE BACKLOG**. Do not use historical prompts or audit findings as a second task system.

## Next task

### JL-A10 — owner-operated spoken Gemini Live certification

Status: OPEN / PARTIAL PASS / BUG FOUND.

Owner physical evidence confirmed microphone/runtime activity, LILITH connectivity, `lilith_routine` list routing, create persistence, list after create, delete, and list after delete. It also found a semantic schedule correctness bug: intended `22:00` from "10 de la noche", but JARVIS submitted `13:00` to LILITH. JL-A10 must stay open until the fixed build is retested physically.

Run the exact procedure in `docs/TESTING.md` from the restarted `C:\JARVIS` runtime. Verify spoken Spanish, microphone/audio, routine create/list/delete through `lilith_routine`, and semantic schedule correctness for `10 de la noche` -> `22:00`. Record sanitized log correlation IDs and then close JL-A10 only with owner evidence.

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
