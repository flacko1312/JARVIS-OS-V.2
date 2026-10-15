# AUT — Date/time authority

**Date:** 2026-10-15  
**Repository:** `C:\JARVIS`  
**Disposition:** IMPLEMENTED AND AUTOMATICALLY VERIFIED  
**Physical spoken verification:** NOT PERFORMED

## Audit finding

The requested feature did **not** already exist as a complete authority. Reminder parsing already defaulted to `Europe/Madrid` and rejected ambiguous bare hours, but current date/time questions still reached Gemini. `main.py` also captured `datetime.now()` once while building a Live session prompt, so that value could become stale and did not prove that answers came from the Windows host clock.

## Implementation

- `core/date_time_authority.py` is the central, read-only authority. It reads the Windows timezone identifier from the registry (with a read-only `tzutil /g` fallback), maps Windows identifiers to IANA zones, and uses aware UTC instants plus `zoneinfo` conversion.
- `Romance Standard Time`, `Europe/Madrid`, `CET` and `CEST` normalize to the Madrid ruleset, preserving CET/CEST and daylight-saving transitions.
- Current time/date queries have an exact router domain and a local handler; they do not pass to conversational generation.
- Typed Gemini Live input is replaced before model routing with an authoritative host-produced sentence. The original question is not sent as a time-guessing prompt.
- Voice Live has a mandatory `date_time` tool and system rule. The removed session-start timestamp can no longer become the source of an answer.
- Reminders use the same authority for `now`, relative dates, timezone normalization, and DST-safe wall-time localization.
- Routine and scheduled Home Assistant normalization continue through `core.schedule_safety`, which now delegates timezone normalization to the central authority.
- No code path changes the Windows clock or timezone.

## Deterministic coverage

`tests/test_time_date_authority.py` adds 13 tests covering:

1. all four required current-time phrasings;
2. both required current-date phrasings;
3. Windows `Romance Standard Time` and CET/CEST aliases;
4. frozen Madrid winter CET and summer CEST;
5. nonexistent spring-forward and duplicated fall-back wall times;
6. near-midnight date rollover and year rollover;
7. today, tomorrow and day after tomorrow;
8. `10 de la noche = 22:00` and ambiguous `a las 5`;
9. reminder integration across year rollover plus ambiguity rejection;
10. routine integration with the central timezone and 22:00 parsing;
11. router/runtime handling without conversational-model fallback;
12. proof that typed Live current-time questions are replaced by host data and never offered to LILITH/model guessing;
13. the Live tool contract for authoritative current time/date.

## Evidence

- Dedicated suite: **13 passed, 1 third-party warning**.
- Related Live/runtime/reminder suite: **107 passed, 1 third-party warning**.
- Full suite: **1072 passed, 93 skipped, 1 warning, 46 subtests passed** in 32.30 seconds.
- `py_compile`: PASS for all changed Python runtime modules.
- `git diff --check`: PASS after whitespace correction.
- Real read-only host probe: `Romance Standard Time` resolved to `Europe/Madrid`; the observed abbreviation was `CEST` on 2026-10-15.

The warning is the pre-existing Google GenAI Python 3.17 deprecation warning. Automated tests do not certify microphone recognition, spoken playback, or Gemini Live compliance during a real audio turn.

## Physical boundary

`PHY2-027` in `PHYSICAL_TEST_PLAN_V2.md` is the required supervised test: compare JARVIS's spoken answer for every required phrase against the Windows clock while recording the before/after clock interval and timezone. No physical test was performed during this pass.
