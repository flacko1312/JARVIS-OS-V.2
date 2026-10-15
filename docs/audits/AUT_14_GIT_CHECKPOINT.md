# AUT-14 — Git checkpoints

## Local commits created

1. `581b626` — `feat: complete intent routing and local AI`
2. `855f97d` — `feat: complete reminders Gmail and media controls`
3. `193b21e` — `feat: harden Gemini and development agents`
4. `5f1d7cb` — `chore: improve HUD observability and quality gates`

No push, amend, reset, checkout, stash or history rewrite was performed.

## Deliberately uncommitted paths

The following tracked files were already modified when this pass began and therefore were not added wholesale to an autonomous commit:

- `actions/browser_control.py` — pre-existing browser lifecycle work, unchanged semantically by this pass.
- `actions/file_processor.py` — pre-existing work plus the narrow AUT-08 custom-action preservation fix; clean separation was considered ambiguous.
- `api/websocket_client.py` — pre-existing queue-close work plus AUT-10 log sanitization; clean separation was considered ambiguous.
- `tests/test_screen_processor.py` — pre-existing audit change.

Pre-existing untracked Block 1–8 reports/tests and the historical final audit/physical plan also remain uncommitted and preserved. This report and the final Block O documents are committed separately after creation; their documentation commit is reported by the final handoff rather than circularly embedded here.
