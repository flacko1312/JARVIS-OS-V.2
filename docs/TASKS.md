# JARVIS Tasks

Status: **CANONICAL ACTIONABLE BACKLOG**. Do not use historical prompts or audit findings as a second task system.

## Current validation state

### AUT-9 — next autonomous work block

Status: NOT STARTED.

Do not start AUT-9 until explicitly requested.

## Closed

### JL-A10 — owner-operated spoken Gemini Live certification

Status: **CLOSED / PHYSICAL E2E PASS**.

Owner physical evidence confirmed microphone/runtime activity, LILITH connectivity, exclusive `lilith_routine` create/list/delete routing, and correct persistence of `22:00 Europe/Madrid` from "10 de la noche". No incorrect `reminder` or `lilith_home_action` route was observed.

### Screen vision — owner-operated validation

Status: **SCREEN PHYSICAL E2E PASS; CAMERA AND OLLAMA FAILOVER STILL HUMAN-GATED**.

The owner invoked `screen_process` through the real runtime. JARVIS captured a 142,430-byte screen image, selected `gemini-3.8-flash`, produced a description matching the visible ChatGPT and AURORA windows, and spoke the result. The obsolete `gemini-2.5-flash` and AFC warning regressions are fixed. Automated tests cover bounded Gemini 503 handling and the final local Ollama fallback; an isolated `qwen3-vl:4b` image smoke passed. The complete real provider chain has not physically exercised Ollama because Gemini primary succeeded.

There is no open P1 feature task. Continue only with the stabilization backlog or a separately authorized supervised validation; do not infer authorization to start deferred work.

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
