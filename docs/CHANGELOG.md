# JARVIS Changelog

## 2026-10-14 — Gemini Live standby and conversation continuity

- Added true Gemini-disconnected `STANDBY` startup with a visible conversation control and F8 shortcut.
- Made F8 pause/resume the same logical conversation while closing microphone/audio forwarding and the Live transport during standby.
- Kept normal multi-turn `session.receive()` completion on one Live connection and limited reconnects to real transport/session failures and `go_away`.
- Added first-connection session resumption, latest-handle capture, sliding-window context compression, and local transcript/summary fallback for rejected or expired handles.
- Physically validated F8 continuity with the `88` -> pause -> resume -> `176` test and no repeated greeting.
- Left real forced network/`go_away` recovery and the 24-hour soak explicitly pending.

## 2026-10-08 — recovery and stabilization

- Reconciled the Windows-only local memory correction with two remote documentation commits.
- Established `C:\JARVIS` as the real Windows runtime/verified development checkout and `origin/main` as repository authority.
- Made root pytest collection deterministic and classified the never-implemented historical UI tour specification.
- Added current executable UI contract tests and repaired stale QA/self-test probes.
- Updated tool inventory to all 46 declarations and serialized every potentially mutating/mixed FunctionCall.
- Removed `shell=True` from the general Windows application launcher.
- Removed WebSocket bearer tokens from URLs, moved browser sessions to `sessionStorage`, and pinned a fixed Next.js release with a clean production audit.
- Reconciled active architecture, state, tasks, testing, integration, product, and design documentation.
- Added the complete recovery audit and technical-debt register.

Earlier Git history remains the authoritative detailed history.
