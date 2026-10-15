# AUT-07 — Multimedia controls

## Outcome

- Added volume up/down, exact volume percentage, mute, unmute and toggle mute.
- Windows exact controls use the installed Core Audio interface; step controls use media keys.
- macOS uses bounded AppleScript and Linux uses `pactl` when available, with an explicit media-key fallback.
- Invalid percentages are rejected before touching the system.
- Queue operations are explicitly reported as unsupported because the current architecture has no stable provider queue abstraction.

## Validation

`python -m pytest tests/test_aut07_multimedia_complete.py tests/test_action_helpers.py tests/test_block2_integrations.py -q`

Result: **158 passed, 7 skipped, 1 warning**.

Tests mock system endpoints. Audible output and real device state remain **PHYSICAL TEST REQUIRED**.
