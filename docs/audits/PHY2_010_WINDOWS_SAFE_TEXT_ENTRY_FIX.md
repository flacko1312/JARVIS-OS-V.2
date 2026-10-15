# PHY2-010 Windows Safe Text Entry Fix

Date: 2026-10-15

## Scope

PHY2-010 physically demonstrated that `computer_control action=type` reached `SafeTextEntry` but was refused with `Safe text-field validation is only implemented on macOS.` This pass implements an equivalent fail-closed Windows path. No physical test was performed and no avatar code was changed.

## Confirmed root cause

`actions.safe_text_entry.validate_safe_text_target()` immediately rejected every operating system except macOS. Consequently, neither `computer_control type` nor `smart_type` could validate a Windows target, even when the focused element was the Windows 11 Notepad editor.

The downstream visible writer also relied on `pyautogui.write`, which is not a reliable Unicode input mechanism for characters such as `áéíóú`, `ñ`, `ü`, `¿`, and `¡`.

## Windows validation design

The new Windows path reads the actual focused element through Microsoft UI Automation without changing application or focus. It records:

- process ID and executable name;
- UIA runtime ID and automation ID;
- control type and class;
- enabled, keyboard-focusable, and currently-focused state;
- ValuePattern/TextPattern availability;
- read-only state where UIA or a standard Win32 edit style exposes it;
- current text only for optional in-memory post-condition comparison.

Accepted controls are UIA Edit or Document controls with stable process/runtime identity and a verified writable state. Modern Notepad is supported as a focused `Notepad.exe` Document exposing TextPattern. Standard edit controls and browser text inputs are supported when UIA ValuePattern reports them writable.

The implementation rejects:

- missing or unstable focused elements;
- disabled, non-focusable, or unfocused controls;
- non-text controls and the Windows desktop;
- read-only targets;
- targets whose writable state cannot be established;
- browser address bars;
- terminals, PowerShell, Command Prompt, and Visual Studio Code;
- message-purpose calls whose focused field cannot be identified as a message composer.

Focus is rechecked immediately before input and before every character. A changed/disappearing target stops input rather than continuing into the new foreground element.

## Unicode and clipboard safety

Windows input uses `SendInput` with `KEYEVENTF_UNICODE` over UTF-16 code units. Newlines use the native Enter virtual key. This preserves arbitrary Unicode without `pyautogui.write` and without temporarily replacing the clipboard.

Because the Windows path never opens or changes the clipboard, existing text and non-text clipboard formats remain untouched on success and failure.

When UIA permits text read-back, SafeTextEntry compares the focused element before and after insertion and refuses to claim success if no expected change is observable. Where a verified editable control does not expose read-back, the result explicitly states that insertion could not be reread instead of claiming verification.

SafeTextEntry's validation diagnostics record only the safety path and target identity; they do not add clipboard-content logging.

## Speech/transcription accent audit

No code-level accent stripping was found on the path into SafeTextEntry:

- Gemini Live input transcription passes through `_clean_transcript()`, which removes control characters only.
- `_merge_transcript_text()` collapses whitespace but preserves Unicode characters.
- tool arguments and `computer_control` pass the text unchanged to `safe_type_text()`.
- the new deterministic Unicode tests confirm that SafeTextEntry receives and emits the exact supplied string.

Therefore the physical transcription `A e I o u ñ` is consistent with provider speech-recognition normalization. Speech recognition was not modified because no code defect was confirmed.

## Files changed

- `actions/safe_text_entry.py`
- `actions/computer_control.py`
- `tests/test_phy2_010_windows_safe_text_entry.py`
- `docs/audits/PHY2_010_WINDOWS_SAFE_TEXT_ENTRY_FIX.md`

## Deterministic tests added

Nineteen tests use mocked UI Automation and input functions and do not interact with real applications. They cover:

- Windows 11 Notepad editable target;
- standard edit control and browser input;
- missing, read-only, desktop, non-text, protected-app, and browser-address targets;
- exact Unicode including accented vowels, `ñ`, `ü`, `¿`, and `¡`;
- UTF-16 native emission;
- multiline text;
- empty text;
- clipboard untouched after success and failure;
- focus change between validation and typing;
- target disappearance during input;
- failed read-back without fabricated success;
- repeated calls without internal duplication.

## Automated evidence

- Focused SafeTextEntry tests: **19 passed** in 0.41 seconds.
- Windows-control and Block 1 tests: **270 passed, 1 warning** in 10.52 seconds.
- Complete pytest suite: **1162 passed, 93 skipped, 1 warning, 49 subtests passed** in 32.72 seconds.
- The warning is the existing `google.genai` Python 3.17 deprecation warning.
- `compileall`: **PASS**.
- `git diff --check`: **PASS** (only pre-existing Git line-ending notices on unrelated files).

## Remaining limitations

- UI Automation providers vary by application. An unusual editor that exposes neither a writable ValuePattern nor the supported Notepad Document/TextPattern contract is deliberately refused.
- Read-back is not available from every valid UIA text provider. Those cases are reported as unverified read-back rather than verified insertion.
- Physical validation is still required for the installed Windows 11 Notepad/UIA version and the real audio-to-tool text produced by Gemini Live.

## Exact physical retest

1. Open Windows 11 Notepad with a blank document.
2. Click inside the empty document so the editor itself has keyboard focus.
3. Say exactly: **“Escribe: Prueba física JARVIS, áéíóú ñ ¿Qué tal? 5827”**.
4. PASS only if the exact text `Prueba física JARVIS, áéíóú ñ ¿Qué tal? 5827` appears in Notepad with accents, `ñ`, and inverted punctuation preserved.
5. Confirm the SafeTextEntry log reports a `windows_uia` safety path and does not expose clipboard contents.
6. Click a non-editable Notepad toolbar/background control or the Windows desktop.
7. Ask JARVIS to type another distinctive phrase.
8. PASS only if JARVIS refuses and no text or keyboard shortcut reaches the non-editable target.
9. Re-focus the Notepad editor and repeat once to confirm one request creates one insertion without duplication.
10. Record the tested commit and physical result; automated tests alone do not certify UI Automation behavior on the live desktop.
