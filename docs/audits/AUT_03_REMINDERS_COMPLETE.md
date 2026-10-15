# AUT-03 — REMINDERS COMPLETE LIFECYCLE

**Date:** 2026-10-15  
**Scope:** Local one-shot reminders only. LILITH routines remain separate and unchanged.

## Implemented

- Spanish relative parsing: `en 30 minutos`, `dentro de dos horas` and numeric/word quantities.
- `hoy`, `mañana`, `pasado mañana`, ISO dates, 24-hour times and qualified morning/afternoon/night times.
- Explicit clarification for genuinely ambiguous wording such as `mañana a las 5`.
- Timezone-aware targets with `Europe/Madrid` default and IANA validation.
- Recurring wording fails closed with an explicit LILITH-routine message.
- Persistent atomic JSON registry under the reminder directory.
- Safe opaque IDs (`rem_` plus random hexadecimal identifier).
- List, cancel/delete, modify/update and create lifecycle.
- Duplicate detection by normalized message and target minute.
- Restart reload and cleanup of malformed/expired registry records.
- Modify schedules the replacement before cancelling the old task and rolls the replacement back if old cancellation fails.
- OS-specific cancellation hooks for Windows Task Scheduler, macOS launchd and Linux systemd user timers.
- Gemini tool schema now exposes lifecycle operations, natural text and timezone.
- The schedule guard permits explicit list/cancel/modify management while retaining FunctionCall/current-turn/duplicate protections.
- Pytest globally isolates the reminder directory so tests never touch the owner's registry.

## Important semantic fix

The parser previously reused `mañana` both as “tomorrow” and “morning”. `mañana a las 5` is now clarification-required; `mañana a las 5 de la tarde` remains unambiguous.

## Files changed

- `actions/reminder.py`
- `main.py`
- `tests/conftest.py`
- `tests/test_aut03_reminders_complete.py` (new)
- `tests/test_block2_integrations.py` (Spanish current-contract expectations)

## Validation

```text
300 passed, 0 failed, 7 skipped, 1 warning, 13 subtests passed
```

No real OS reminder was created or cancelled. The seven existing integration skips remain physical/provider checks; no skip was added.

## Physical boundary

Actual Windows Task Scheduler creation, notification delivery after restart and real cancellation/modify behavior remain **PHYSICAL TEST REQUIRED**.
