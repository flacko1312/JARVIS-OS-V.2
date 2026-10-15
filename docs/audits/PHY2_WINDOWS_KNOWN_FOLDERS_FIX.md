# PHY2 Windows Known Folders Fix

Date: 2026-10-15

## Scope and physical finding

PHY2-009 confirmed that application launching worked, while `file_controller` rejected items such as `desktop/proyectos cloud` and `desktop/dibujos`. No physical test was performed during this fix. Avatar code and the output/application-launch paths were not changed.

## Root cause

`actions/file_controller.py::_resolve_path()` recognized a shortcut only when the complete input was exactly `desktop`, `documents`, or another English alias. A child path such as `desktop/dibujos` therefore remained relative to the JARVIS process working directory. `_is_safe_path()` correctly found that unrelated resolved location outside the allowed user root and returned `Access denied`.

The old shortcut helpers also assumed locations such as `Path.home() / "Desktop"`. That is not authoritative on Windows because Known Folders may be localized, redirected to OneDrive, or moved to another volume.

## Implementation

- Windows folders are resolved for the current user through `SHGetKnownFolderPath` and the official Known Folder identifiers for Desktop, Documents, Downloads, Pictures, Music, and Videos.
- English and Spanish aliases are normalized case-insensitively and accent-insensitively.
- The first relative segment is replaced with the authoritative folder path, preserving children, spaces, accents, and both slash styles.
- Resolved Known Folders are explicit safe roots, including legitimately redirected folders outside `Path.home()`.
- Inputs containing a `..` component are rejected before filesystem access.
- Absolute and UNC paths are never treated as aliases.
- The existing resolved-path containment check remains authoritative. Existing symlinks and Windows reparse points are resolved before containment, so they cannot escape a safe root.
- Existing absolute paths inside an approved root continue to work.
- A valid but absent child reaches the existence check and returns `Not found`, rather than being mislabeled `Access denied`.
- Windows `os.startfile` continues to support existing folders, regular files, and `.lnk` shortcuts without adding shell parsing or command execution.

## Files changed

- `actions/file_controller.py`
- `tests/test_phy2_windows_known_folders.py`
- `docs/audits/PHY2_WINDOWS_KNOWN_FOLDERS_FIX.md`

## Deterministic tests added

Twelve tests use temporary directories and mocked Known Folder resolution; no personal files are read or exposed. Coverage includes:

- Desktop and Escritorio
- Documents and Documentos
- Downloads and Descargas
- Pictures/Imágenes, Music/Música, and Videos/Vídeos
- spaces and accented child names
- forward and backward slashes
- traversal rejection, including bare `..\\..`
- protected absolute Windows path rejection
- valid nonexistent child returning `Not found`
- opening a normal folder, file, and shortcut
- an existing absolute approved path
- delegation to the current-user Windows Known Folder API

## Automated evidence

- Focused initial path tests: **65 passed, 1 warning, 3 subtests passed** in 3.69 seconds.
- All Block 1 and `file_controller` tests: **243 passed, 1 warning, 3 subtests passed** in 10.61 seconds.
- Complete pytest suite: **1123 passed, 93 skipped, 1 warning, 49 subtests passed** in 34.39 seconds.
- The warning is the existing `google.genai` Python 3.17 deprecation warning.
- `compileall`: **PASS**.
- `git diff --check`: **PASS** (only pre-existing Git line-ending notices on unrelated files).

## Required physical retest

1. Start JARVIS normally and do not change standby state during the test.
2. Say: **“abre la carpeta dibujos del escritorio”**.
3. Confirm the real current-user Desktop `dibujos` folder opens in Explorer.
4. Confirm the tool result reports an opened folder and does not report `Access denied`.
5. Close that Explorer window.
6. Say: **“abre proyectos cloud del escritorio”**.
7. Confirm the real current-user Desktop `proyectos cloud` item opens.
8. Confirm spaces were preserved and no similarly named location outside Desktop was opened.
9. As a negative check, request a definitely nonexistent Desktop child and confirm JARVIS reports `Not found`, without opening anything.
10. Record the tested commit and mark the result as physical PASS or FAIL; automated results alone do not certify the Windows shell interaction.
