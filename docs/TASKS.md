# JARVIS Tasks

Status: **CANONICAL ACTIONABLE BACKLOG**. Do not use historical prompts or audit findings as a second task system.

## Next task

### AUT-9 — next autonomous work block

Status: NOT STARTED.

Do not start AUT-9 until explicitly requested.

## Closed

### JL-A10 — owner-operated spoken Gemini Live certification

Status: PASS / CLOSED.

Owner physical retest on Git HEAD `bbe95a8d3abcdbbab130e46a3ac336bd47f5c374` passed. Windows regression reported `429 passed`, `77 skipped`, `0 failed`, `0 errors`, `1 warning`, and `15 subtests passed`. Real startup reached interface ready, loaded 87 LILITH context facts, connected, opened microphone stream, ran receive loop, and started playback. Spoken routine create for "Encender bombilla mueble todos los días a las 10 de la noche" submitted `schedule.hour=22`, `minute=0`, `timezone=Europe/Madrid`; LILITH confirmed create with correlation ID; list, delete of `routine_id=14`, and final list were confirmed.

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
