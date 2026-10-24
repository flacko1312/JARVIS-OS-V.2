# Telegram Gateway acceptance evidence — 2026-10-24

Environment: `server-lilith`, JARVIS Headless user service, local Telegram-channel Unix IPC.
No real Telegram Bot API credential or owner `chat_id` was available, so physical Telegram
delivery remains pending and is not marked as passed.

## Automated evidence

- Gateway/tool/continuity focused suite: 105 passed.
- Earlier combined focused run: 151 passed, 2 unrelated existing playback tests deselected.
- Broad repository run (excluding five GUI/display collection failures): 1077 passed,
  15 failed, 77 skipped, 49 subtests passed. Failures are pre-existing platform/contract issues;
  regressions introduced by the gateway were fixed and re-run in the 105-test focused suite.
- Full collection cannot run headlessly because five desktop tests import `pyautogui` without a
  `DISPLAY`.

## Acceptance matrix

| ID | Result | Evidence |
|---|---|---|
| A1 | Pending physical | Requires bot token and owner chat_id. Local authorized-path tests pass. |
| A2 | PASS automated | Unauthorized update produced no JARVIS call and no reply. |
| B1 | PASS real backend | Wolf/dog response returned through IPC. |
| B2 | Covered by real general-response path | Existing model backend active. |
| B3 | PASS real backend | Follow-up correctly retained wolf/dog referent. |
| C1/C2 | PASS automated/backend | Persistent continuity suites pass; topic follow-up exercised. |
| D1 | PASS real backend | Current Docker result returned with real HTTP(S) source URLs. |
| D2 | PASS automated | Static IP question does not trigger web prefetch. |
| D3 | PASS automated/observed | Provider failure falls back; no fabricated URL path. |
| E1 | PASS real backend | CPU/RAM/disk/JARVIS returned from host tools. |
| E2 | PASS real backend | `/`, `/boot/efi`, `/mnt/lilith_data` capacities returned. |
| E3 | PASS tool | systemd failed-unit probe tested. |
| E4 | PASS real backend | PostgreSQL container reported running/healthy. |
| E5 | PASS real backend | Docker reported all seven containers running. |
| F1 | PASS real backend | Bounded JARVIS journal read summarized; origin labeled. |
| F2 | PASS real backend | Follow-up understood that no numbered errors existed. |
| G1 | PASS real backend | Existing JARVIS/LILITH memory answered; no gateway KB created. |
| H1 | PASS automated | Missing/unavailable JARVIS becomes a readable Telegram error. |
| H2 | PASS implementation | Long-poll exponential reconnect; physical network cut pending. |
| H3 | Partial | Unit enabled, linger active, restart policy set; host reboot not performed. |
| H4 | PASS automated | Long plain-text responses split below Telegram's limit. |
| I1 | PASS real backend | Destructive shell request refused; no shell execution path exists. |
| I2 | PASS audit | Token is never logged; token absent because credential not supplied. |
| I3 | PASS audit | No credential file or secret added to Git. |

## Deployed service state

- `jarvis-headless.service`: enabled and active; owner-only socket mode `0600`.
- `jarvis-telegram.service`: installed and enabled; safely inactive because
  `~/.config/jarvis/telegram.env` does not yet exist (`ConditionResult=no`).
