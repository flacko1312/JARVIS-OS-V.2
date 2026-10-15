# JARVIS — Physical test plan V2

**Prepared:** 2026-10-15  
**Required checkout:** `C:\JARVIS` at the final local completion commit plus the explicitly preserved working-tree changes.  
**Rule:** unperformed tests remain **PHYSICAL TEST REQUIRED**. Automated PASS never certifies sound, image quality, external accounts, devices or visible desktop behavior.  
**Excluded:** avatar, visemes, lip-sync, Blender and GLB/GLTF are **DEFERRED BY USER — OUT OF CURRENT SCOPE**.

Record for every item: timestamp, HEAD, PASS/FAIL/NOT RUN, concise observable evidence and sanitized log timestamps. Never record credentials or personal message bodies.

## A. Startup, HUD and Live voice

1. **PHY2-001 — Startup/Spanish:** launch normally; ask the date. Expect one process/window and a correct audible Spanish answer.
2. **PHY2-002 — Standby cycles:** use the visible control and F8 for three start/stop cycles. In standby verify no mic upload, greeting, audio or reconnect loop; JARVIS/LILITH remain alive.
3. **PHY2-003 — HUD restore/metrics:** minimize, tray-hide, restore, compact/fullscreen/theme/settings. Verify metrics stop while hidden/minimized and resume once without duplicated polling.
4. **PHY2-004 — Voice/audio/context:** select multiple supported voices, test session recall, interruption and a contextual follow-up. Judge audible quality and coherent state transitions.
5. **PHY2-005 — Device loss:** disable/restore microphone and output device. Expect bounded errors, no storm and later recovery.

## B. Vision and local AI

6. **PHY2-006 — Screen/camera:** identify distinctive screen text and a camera object; verify accuracy, spoken Spanish and released camera handle.
7. **PHY2-007 — Ollama text:** with configured loopback model, ask explicitly for local AI; then stop Ollama, remove the configured model and restore it. Verify online/offline/model-missing states and later recovery, with no Gemini↔Ollama loop.
8. **PHY2-008 — Vision fallback:** make eligible Gemini vision providers unavailable using the documented safe method and verify one bounded Ollama fallback from the same capture; then test dual failure and cloud recovery.

## C. Windows, files and browser

9. **PHY2-009 — Apps/Unicode:** open Spotify, Notepad and an installed application whose name contains accents; focus and close the intended windows only. Confirm clipboard contents are restored after Unicode Start Menu search.
10. **PHY2-010 — Input/files:** in disposable targets, type accented text, click/scroll, screenshot, CRUD files and recoverably delete a copy. No unrelated window or source file may change.
11. **PHY2-011 — Documents:** process representative PDF, DOCX, XLSX, image and custom text instruction. Verify content and that the original custom instruction reaches the result.
12. **PHY2-012 — Browser lifecycle:** navigate/read/search/back/reload/screenshot and close controlled Chrome twice. Verify no `BrowserThread-*` or browser child remains; test unreachable URL then recovery.

## D. Gmail, media, reminders, presentations and development

13. **PHY2-013 — Gmail OAuth/read:** explicitly select one Desktop OAuth client, connect a test account, list/search/read a multipart thread and confirm no credential data in logs. Also verify ambiguous discovered client files are refused.
14. **PHY2-014 — Gmail attachments/drafts:** inspect attachment metadata, download to a disposable selected directory, save/list/read/delete a draft and prepare a message with an attachment. Verify no send before approval; cancel one, approve one safe test delivery, and confirm exactly one arrival.
15. **PHY2-015 — Media/volume:** play/pause/next/previous on installed media, then volume up/down, exact percentage, mute/unmute/toggle. Confirm audible/system state. Queue requests must say unsupported rather than claim success.
16. **PHY2-016 — Reminder lifecycle:** create Spanish relative and dated reminders, list, modify, reject a duplicate, cancel one, restart JARVIS and verify one remaining notification at the Europe/Madrid time. Confirm ambiguous “a las 5” asks for clarification and recurring language routes to LILITH routines.
17. **PHY2-017 — Presentation/research:** run source-backed research and create/open/edit/extend/export a disposable PPTX/PDF. Verify citations, progress and no source overwrite.
18. **PHY2-018 — Safe screen-debug:** on a disposable project, request screen-debug. Confirm only a proposal/diff is produced; test invalid/expired approval, source-change rejection, then explicit valid approval.
19. **PHY2-019 — Dev Git:** in a disposable repository only, exercise status/diff/branch/local commit and generated tests/fix loop. Confirm no push, auto-stage, reset, workspace escape or unrelated edit.
20. **PHY2-020 — Claude/Codex recovery:** in a disposable project, test available, unavailable/unauthenticated and restored CLI states with bounded subprocess cleanup.

## E. LILITH, HA, persistence and recovery

21. **PHY2-021 — Memory authority:** store/search/restart/delete one explicit persistent fact through LILITH; separately keep one session-only fact and verify it never reaches LILITH and disappears after restart.
22. **PHY2-022 — Routine lifecycle:** create daily 21:00 Europe/Madrid, list/get/history/modify/delete. Verify current-turn and FunctionCall ID guards and no immediate Home Assistant action.
23. **PHY2-023 — HA safe device:** with one owner-approved light, test resolution/approval/on/off/restore. During ambiguous or stale turn/ID state verify no real effect occurs.
24. **PHY2-024 — Service/network recovery:** stop/restore LILITH and briefly disconnect/restore network during harmless turns. Verify bounded recovery, no duplicate action/session and retained durable context.
25. **PHY2-025 — Shutdown/reopen:** request JARVIS shutdown, hear the farewell, verify worker/process cleanup, reopen once and verify durable conversation continuity.

## F. Extended stability

26. **PHY2-026 — 30–60 minute soak:** run `python scripts/soak_monitor.py --manual --interval 5` alongside normal voice turns, two browser cycles, mute/unmute and one vision request. Preserve the JSON output. PASS requires no harness warning, crash, reconnect storm, zombie browser or duplicate job. This still does not prove absence of every possible leak.

Total remaining supervised tests: **26**. The original 29-test plan is retained as historical evidence; V2 consolidates overlapping cases but does not mark them automatically passed.
