# PHY2-009 Named Window Close Fix

Date: 2026-10-15

## Scope

This pass addresses the confirmed physical failure where “Cierra el Bloc de notas” reported success while Windows 11 Notepad remained open. No physical test was performed during implementation. No avatar code was changed.

## Confirmed root cause

The Gemini tool contract routed an OS-window close to `computer_settings`, but did not expose a dedicated `app_name` field. The Windows dispatcher recovered a name from `value` or `description` and then discarded it.

`actions.computer_settings.close_window()` sent `Ctrl+W` to the foreground window. It did not enumerate windows, identify an application, or verify a post-condition. Consequently:

- a foreground Chrome tab could receive the shortcut even when Notepad was requested;
- Windows 11 Notepad could not be found when its visible title was only `Sin título`;
- the dispatcher returned `Done: close_window` immediately after issuing the shortcut;
- Gemini could turn that unconditional tool result into a false spoken success.

## Implementation

`actions/windows_window_control.py` now provides the Windows-specific close lifecycle:

1. Normalize Spanish/English names and Unicode accents.
2. Resolve known aliases to executable identity (`Notepad.exe`, `Spotify.exe`, browser processes).
3. Enumerate visible top-level HWNDs and collect title, class, PID, and executable name.
4. Select the requested application independently of foreground focus.
5. Reject JARVIS/AURORA and ambiguous multiple matches.
6. Send `WM_CLOSE` only to the selected HWND.
7. Poll `IsWindow` with a bounded timeout.
8. Re-enumerate matching application windows before returning success.

Process identity is authoritative for known applications. A Chrome document title containing “Bloc de notas” does not match Notepad. Title matching remains a fallback for unknown application names when process identity is not otherwise mapped.

No force-kill operation was added. If graceful close is rejected or the HWND remains, the tool truthfully returns `No he podido cerrar ...`.

An absent target is verified from a fresh enumeration and returns `No hay ninguna ventana abierta de ...`. It is not inferred from prior tool history.

The `computer_settings` declaration now includes `app_name` and explicitly distinguishes `close_tab` from `close_window`. The Live system instruction treats observable tool results as authoritative and forbids spoken success after failure, ambiguity, or an unverified close.

## Files changed

- `actions/windows_window_control.py`
- `actions/computer_settings.py`
- `main.py`
- `tests/test_phy2_009_named_window_close.py`
- `docs/audits/PHY2_009_NAMED_WINDOW_CLOSE_FIX.md`

## Deterministic tests added

Twenty tests use mocked window inventories and Windows actions; no real application is closed. Coverage includes:

- Windows 11 Notepad with title `Sin título`
- full Spanish command extraction
- named Notepad success and correct HWND
- observable post-close verification
- accepted close message with window remaining
- rejected `WM_CLOSE`
- verified already-closed state
- unrelated foreground Chrome preserved
- browser-tab shortcut excluded from Notepad close
- `close_tab` remains separate
- Spotify process targeting
- ambiguous multiple Notepad windows
- unknown/no matching target
- protected JARVIS target
- Unicode/accented application name
- repeated close without repeated false success
- prior focus on another application
- process identity winning over misleading browser title
- tool declaration routing contract
- spoken response truthfulness rule

## Automated evidence

- Focused named-window tests: **20 passed, 1 warning** in 1.15 seconds.
- Windows-control and Block 1 tests: **251 passed, 1 warning** in 10.58 seconds.
- Complete pytest suite: **1143 passed, 93 skipped, 1 warning, 49 subtests passed** in 33.83 seconds.
- The warning is the existing `google.genai` Python 3.17 deprecation warning.
- `compileall`: **PASS**.
- `git diff --check`: **PASS** (only pre-existing Git line-ending notices on unrelated files).

## Physical retest procedure

1. Open Windows 11 Notepad with a blank untitled document; its visible title may be `Sin título`.
2. Keep Chrome and JARVIS open.
3. Focus Chrome.
4. Say exactly: **“Cierra el Bloc de notas.”**
5. PASS only if Notepad closes, Chrome remains open, no Chrome tab closes, JARVIS remains open, and spoken success occurs only after the Notepad HWND disappears.
6. Say again: **“Cierra el Bloc de notas.”**
7. PASS only if JARVIS reports that no Notepad window is open and does not issue another close against Chrome or JARVIS.
8. For ambiguity coverage, optionally open two separate Notepad windows and repeat the named command. JARVIS must request clarification and close neither.
9. Record the tested commit and physical result. Automated tests do not certify the actual Windows shell interaction.
