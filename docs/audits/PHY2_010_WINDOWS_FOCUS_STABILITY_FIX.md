# PHY2-010 Windows UIA Focus Stability Fix

Date: 2026-10-15

## Scope and evidence boundary

The first physical retest proved that the existing UI Automation validation and `KEYEVENTF_UNICODE` writer work with Windows 11 Notepad. This pass preserves that implementation and fixes consecutive-command focus stability. No physical test was performed, no avatar code was changed, and nothing was pushed.

## Confirmed root cause

The failure was structural in `actions/safe_text_entry.py`:

1. SafeTextEntry retained no record of the most recently validated user editor. A later tool call accepted only the element returned by `GetFocusedElement()` at that instant.
2. The UIA runtime ID was part of the exact target identity and was compared at initial validation, immediately before writing, before every Unicode character, and after writing. Modern UIA providers may regenerate that ID while the underlying editor remains the same.
3. No top-level application HWND or ancestor relationship was captured, so the code could not distinguish an equivalent Notepad editor from an unrelated target.
4. Any momentary focus on AURORA therefore produced an immediate refusal, even when the user had not selected another target.

The AURORA audit found no `activateWindow()` call in ordinary log/subtitle signal handling. Explicit foreground-taking paths do exist when restoring from the tray and showing/restoring some UI and overlays. The physical report did not include simultaneous foreground/UIA snapshots, so it would be inaccurate to claim that AURORA focus stealing was conclusively observed in that run. The fix safely handles such a transient self-focus when it occurs; it does not assume it always occurs.

## Stable target design

A validated Windows target is identified by:

- process ID;
- top-level HWND obtained from the focused UIA element's same-process ancestor chain;
- UIA control type;
- automation ID;
- class name;
- a fresh editable/enabled/not-read-only validation.

The mutable UIA runtime ID remains diagnostic data but is no longer the security identity. This explicitly supports Windows 11 Notepad when its runtime ID changes after insertion.

After successful validation or writing, SafeTextEntry holds only a short-lived, in-memory target description. A cached target may be reacquired only when all of these conditions hold:

- it is less than 45 seconds old;
- the requested typing purpose is unchanged;
- current focus belongs to the running JARVIS process itself;
- Windows `GetLastInputInfo` proves that no new user keyboard/mouse input occurred;
- the previous top-level HWND still exists;
- bringing that already-proven HWND forward succeeds;
- the newly focused UIA element has the same stable identity;
- the new element again passes editable, enabled, focusable, and read-only checks.

The cache is discarded on expiry, purpose change, actual user input, another foreground application, destroyed window, failed reacquisition, identity mismatch, read-only transition, or focus change before/during/after writing.

## Security invariants

- SafeTextEntry never discovers an arbitrary replacement target from the cache.
- A Desktop, Chrome non-text area, another application, or a user-clicked AURORA panel invalidates the old target.
- A stale/destroyed/read-only target is refused.
- JARVIS/AURORA is never accepted as the typing target.
- The target is revalidated immediately before the batch and before every Unicode character. The latter now compares stable editor identity instead of mutable runtime ID, retaining immediate abort if focus changes during `SendInput`.
- Existing protected-process, desktop, browser address-bar, message-composer, and read-only restrictions remain unchanged.
- Unicode still uses native UTF-16 `SendInput`; no clipboard fallback or text logging was introduced.

Sanitized diagnostics now include `SAFE_TEXT target_validated`, `transient_focus_loss owner=jarvis`, `target_reacquired`, `target_invalidated reason=...`, and `write_complete chars=N verified=true/false`. Typed content is never logged.

## Files changed

- `actions/safe_text_entry.py`
- `tests/test_phy2_010_windows_focus_stability.py`
- `docs/audits/PHY2_010_WINDOWS_FOCUS_STABILITY_FIX.md`

## Deterministic tests added

Twelve new tests, using fakes/mocks only, cover:

- initial Notepad validation;
- second consecutive command without another click;
- changing Notepad runtime ID with stable editor identity;
- temporary JARVIS focus and safe reacquisition;
- real user input invalidating the cached editor;
- another application invalidating the target;
- destroyed, expired, and newly read-only targets;
- exact Unicode emission without duplication;
- immediate abort when focus changes during input;
- one reacquisition operation per request.

The pre-existing 19 Windows SafeTextEntry tests continue to cover first insertion, editable/read-only/desktop/protected targets, Unicode, multiline input, clipboard preservation, post-condition read-back, disappearance, and repeated calls.

## Automated results

- Focused SafeTextEntry/focus-stability: **31 passed**.
- Windows/Block 1 relevant group: **190 passed, 1 warning, 3 subtests passed**.
- Complete pytest suite: **1174 passed, 93 skipped, 1 warning, 49 subtests passed** in 33.87 seconds.
- `python -m compileall -q actions tests`: **PASS**.
- `git diff --check`: **PASS**; it emitted only pre-existing line-ending notices for unrelated dirty files.

The warning is the existing `google.genai` Python 3.17 deprecation warning. Automated success does not certify live Windows foreground/UIA behavior; the sequence below remains required.

## Exact physical retest

1. Start JARVIS from this committed revision.
2. Open Windows 11 Notepad with a blank document.
3. Click inside the editor **once**.
4. Say: **“Escribe: Primera prueba 5827”**.
5. Confirm `Primera prueba 5827` appears exactly once.
6. Without clicking Notepad or any other window again, say: **“Escribe: Segunda prueba, áéíóú ñ ¿Qué tal?”**.
7. PASS only if the second phrase appears exactly once in the same document, with exact accents, `ñ`, and inverted punctuation.
8. Confirm the sanitized log contains target validation and, if AURORA temporarily owned focus, `transient_focus_loss` followed by `target_reacquired`; it must not contain the spoken text.
9. Click the Windows Desktop.
10. Say: **“Escribe: ESTO NO DEBE APARECER”**.
11. PASS only if JARVIS refuses and sends no text or shortcut anywhere.
12. Optionally repeat step 9 with a Chrome non-text area and an AURORA panel; both must invalidate the former Notepad target and refuse.
