# AUT-06 — Gmail complete

## Outcome

Completed the automatically testable Gmail software surface without accessing a real account or sending mail.

- Thread retrieval and normalized multi-message display.
- Recursive attachment metadata and safe attachment download into an existing selected directory.
- MIME composition with local attachments and a 25 MB aggregate safety limit.
- Approval-gated API delivery for messages with attachments; no send occurs during preparation.
- Draft-only create, list, read and delete operations.
- OAuth discovery gives explicit/configured paths precedence and refuses ambiguous automatic candidates.
- OAuth tokens and client contents are never logged.

## Validation

Command:

`python -m pytest tests/test_aut06_gmail_complete.py tests/test_action_helpers.py tests/test_block2_integrations.py -q`

Result: **154 passed, 7 skipped, 1 warning**.

All Gmail API behavior in this block was exercised through mocks. Real OAuth, browser login, attachment download and delivery remain physical/account validation items. No real email was sent.
