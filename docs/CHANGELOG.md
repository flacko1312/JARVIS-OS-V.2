# JARVIS Changelog

## 2026-10-23 - voice turn timing, transcript assembly, and Spotify isolation

- Made Gemini Live end-of-turn silence configurable with `JARVIS_LIVE_VAD_SILENCE_MS`, bounded to 250-3000 ms. Owner physical testing selected **2500 ms** as the current natural-conversation value after 320/650/1000/2000 ms proved too aggressive.
- Fixed Live input-transcription assembly so provider token deltas preserve real word boundaries instead of producing artificial splits such as `Ex plí ca me` and `di ferencia`.
- Added explicit pending-user-turn state so repeated speech while the first request is still unanswered is absorbed without executing duplicate actions; the same request remains valid after response start.
- Added isolated Spotify process-loopback analysis with `pywebrtc-audio` AEC3 and rollback modes `off`, `shadow_v1`, `shadow_v2`, `shadow_v3`, and current `shadow_v4`.
- `shadow_v4` dynamically aligns Spotify loopback to microphone audio over a 0-160 ms search window, then combines correlation, AEC residual/retention and VAD while preserving original accepted microphone PCM.
- Offline replay of the saved physical Spotify-only capture produced **0 false gate-open sequences** under `shadow_v4`; final owner physical acceptance against a real spoken Spotify advertisement remains pending.
- Updated VAD QA expectations from a hard-coded legacy 320 ms value to the bounded configurable runtime contract.
- Full repository suite after the current checkpoint: **1235 passed, 93 skipped, 1 third-party warning, 49 subtests passed, 0 failures**.
- Stored a recoverable checkpoint at `docs/audits/VOICE_SPOTIFY_CHECKPOINT_2026-10-23.md` plus recovery material under `tmp/checkpoints/`. No commit was created because unrelated dirty work is present.
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
