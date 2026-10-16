# JARVIS Changelog

## 2026-10-14 — Gemini Live standby and conversation continuity

- Added true Gemini-disconnected `STANDBY` startup with a visible conversation control and F8 shortcut.
- Made F8 pause/resume the same logical conversation while closing microphone/audio forwarding and the Live transport during standby.
- Kept normal multi-turn `session.receive()` completion on one Live connection and limited reconnects to real transport/session failures and `go_away`.
- Added first-connection session resumption, latest-handle capture, sliding-window context compression, and local transcript/summary fallback for rejected or expired handles.
- Physically validated F8 continuity with the `88` -> pause -> resume -> `176` test and no repeated greeting.
- Added atomic, bounded local persistence for the logical conversation across standby, reconnect, `go_away`, rejected/expired native handles, process restart, and crash recovery. Runtime state excludes raw audio and Gemini resumption handles and is replaced only by explicit `new_conversation()`.
- Added write-through Live input/output transcripts, rolling summaries and bounded tool-result context, with restored continuity supplied before normal listening and no restore greeting.
- Separated active conversation, explicit local saved notes, and explicit LILITH long-term memory. Current/restored conversation has precedence, automatic saves are suppressed, and saved-memory searches require explicit intent.
- Physically validated full-restart continuity and direct immediate recall without `save_memory`, `local_memory_search`, or `lilith_memory_search`; explicit local-memory lookup remains available.
- Documented the current compatibility result: `google-genai 2.25.0` exposes `HistoryConfig`, but the tested Native Audio preview model/API rejects minimal initial-history use with API 1007. The current configuration therefore uses compact durable reconstruction in `system_instruction`, without treating this as a permanent Gemini limitation.
- Recorded three unrelated UI localization-contract failures that reproduce on clean pre-block `HEAD` (`MUTED`, `Quit AURORA`, and `ANALYSIS COMPLETE` expectations versus the committed Spanish UI).
- Left real forced network/`go_away` recovery and the 24-hour soak explicitly pending.

## 2026-10-08 — recovery and stabilization

- Reconciled the Windows-only local memory correction with two remote documentation commits.
- Established `C:\JARVIS` as the real Windows runtime/verified development checkout and `origin/main` as repository authority.
- Made root pytest collection deterministic and classified the never-implemented historical UI tour specification.
- Added current executable UI contract tests and repaired stale QA/self-test probes.
- Updated tool inventory to all 46 declarations (now 48 with `file_processor` and `open_capabilities_catalog`) and serialized every potentially mutating/mixed FunctionCall.
- Removed `shell=True` from the general Windows application launcher.
- Removed WebSocket bearer tokens from URLs, moved browser sessions to `sessionStorage`, and pinned a fixed Next.js release with a clean production audit.
- Reconciled active architecture, state, tasks, testing, integration, product, and design documentation.
- Added the complete recovery audit and technical-debt register.

Earlier Git history remains the authoritative detailed history.
