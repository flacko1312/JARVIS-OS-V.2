# AUT-08 — Small known bugs

## Fixed

1. Unknown text-document actions now preserve the original action/instruction in the model prompt instead of replacing it with the word `custom`.
2. Windows Start Menu fallback uses clipboard-backed entry for Unicode application names and restores the prior clipboard value; ASCII keeps direct typing.
3. Duplicate `UI_TEXT` dictionary entries were removed without changing their translated values.

## Validation

`python -m pytest tests/test_aut08_known_bugs.py tests/test_block1_windows_files_browser.py tests/test_block2_integrations.py tests/test_block5_hud_states_avatar.py -q`

Result: **299 passed, 13 skipped, 1 warning**.

Actual Start Menu interaction with accented names remains **PHYSICAL TEST REQUIRED**.
