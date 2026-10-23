# JARVIS — PHYSICAL TEST PLAN

**Date prepared:** 2026-10-15  
**Purpose:** One ordered, owner-operated session for every remaining hardware, account, application and real-service validation.  
**Scope exclusion:** Avatar, visemes, lip-sync, facial/eye/mouth animation and related rendering are excluded.

## Session preparation

Use the real Windows checkout `C:\JARVIS`. Before starting:

1. Save unrelated work and ensure the microphone, speakers and camera are connected.
2. Have Gemini, LILITH, Home Assistant, Ollama, Gmail, Spotify/YouTube, Chrome, PowerPoint, VS Code, Codex and Claude Code credentials/applications available where applicable.
3. Choose one harmless Home Assistant light that can be restored to its initial state.
4. Create a disposable folder and harmless sample PDF, DOCX, XLSX, image and code project.
5. Open `C:\JARVIS\logs\jarvis.log` in a viewer capable of live refresh. Never paste secrets into the report.
6. Record the starting Git hash and Windows time. Run tests in the order below to minimize restarts.

Global PASS rule: the observable behavior must match the expected result and logs must contain no unhandled traceback, false success or duplicate side effect. A test not performed is **PHYSICAL TEST REQUIRED**, never PASS.

## Phase A — single startup and core voice session

### PHY-001

- **Area:** Startup / HUD / Gemini Live
- **Preparation:** LILITH and network available; JARVIS closed.
- **Action:** Launch JARVIS once from its normal Windows launcher. Say: **“JARVIS, dime qué día es hoy.”**
- **Expected result:** HUD opens once, reaches listening/online state, hears the phrase and answers aloud in Spanish with the correct local date.
- **Observable evidence:** One JARVIS process tree; HUD state sequence; audible Spanish response; startup/Live connection log.
- **PASS:** One clean startup and correct spoken answer.
- **FAIL:** Crash, duplicate window/process, no listening, wrong language/date, no audio or traceback.
- **Logs:** `logs/jarvis.log`, console startup output, `tmp/jarvis_status.json` if present.
- **Dependencies:** Gemini, microphone, speakers, Windows audio.

### PHY-002

- **Area:** HUD/UI/states
- **Preparation:** Continue PHY-001 without restart.
- **Action:** Exercise mute/unmute, compact mode, fullscreen, theme cycle, settings/shortcuts overlay, file drop zone and system tray minimize/restore.
- **Expected result:** Controls respond once; states IDLE/LISTENING/THINKING/SPEAKING/MUTED are coherent; no frozen or duplicated background work.
- **Observable evidence:** Visible state labels, changed layout/theme, tray restore, CPU/RAM/GPU metrics updating.
- **PASS:** Every control returns to a usable listening state without layout corruption.
- **FAIL:** Frozen UI, wrong state, unrecoverable mute, broken restore or rising duplicate jobs.
- **Logs:** `logs/jarvis.log`, Windows Task Manager.
- **Dependencies:** Running HUD.

### PHY-003

- **Area:** Microphone / audio / conversation context / Spanish
- **Preparation:** Continue same session.
- **Action:** Say: **“Recuerda durante esta conversación que mi palabra de prueba es NEBULA.”** Then: **“¿Cuál es mi palabra de prueba?”** Interrupt one longer reply with **“Para”** and continue with a follow-up pronoun/context question.
- **Expected result:** Correct same-session recall, natural Spanish, usable interruption and retained conversational context.
- **Observable evidence:** Input/output transcripts and audible responses.
- **PASS:** Correct recall/context with no duplicate reply or stuck speaking state.
- **FAIL:** Lost context, wrong language, echo loop, unusable barge-in or stale audio.
- **Logs:** `logs/jarvis.log` Live/session/audio entries.
- **Dependencies:** Gemini Live, microphone, speakers.

### PHY-004

- **Area:** Audio device loss/recovery
- **Preparation:** Continue same session; know how to restore the selected microphone.
- **Action:** Disconnect/disable the microphone, attempt one request, restore it, then say: **“JARVIS, confirma que vuelves a escucharme.”**
- **Expected result:** Explicit bounded error while unavailable; no reconnect storm; recovery after restoration without duplicate session.
- **Observable evidence:** Device error/recovery state and one final spoken answer.
- **PASS:** UI remains responsive and microphone use recovers cleanly.
- **FAIL:** Crash, infinite retry, duplicate sessions, permanent loss or false success.
- **Logs:** `logs/jarvis.log`, Windows audio device events.
- **Dependencies:** Removable/disableable microphone.

## Phase B — vision and local fallback, no restart

### PHY-005

- **Area:** Screen vision
- **Preparation:** Display a page with distinctive visible text.
- **Action:** Say: **“Describe exactamente lo que ves en mi pantalla.”**
- **Expected result:** One fresh capture and an accurate spoken Spanish description without invented details.
- **Observable evidence:** Capture log/provider/model and matching description.
- **PASS:** Description matches visible screen.
- **FAIL:** Wrong screen, hallucinated content, capture error or no spoken delivery.
- **Logs:** `logs/jarvis.log` entries for `screen_process` and vision provider.
- **Dependencies:** Gemini vision and screen permission.

### PHY-006

- **Area:** Camera
- **Preparation:** Camera unobstructed; place a harmless distinctive object in view.
- **Action:** Say: **“Mira por la cámara y dime qué objeto estoy mostrando.”**
- **Expected result:** Camera opens, one frame is analyzed, result is spoken, camera handle is released.
- **Observable evidence:** Preview/frame, correct object description, camera indicator turns off afterward.
- **PASS:** Correct result and camera reusable by another app afterward.
- **FAIL:** Wrong device, black frame, invented result, locked camera or crash.
- **Logs:** `logs/jarvis.log`, camera/vision entries.
- **Dependencies:** Camera, permission, Gemini vision.

### PHY-007

- **Area:** Ollama operational and full fallback
- **Preparation:** Ollama running with configured vision model. Temporarily use the documented safe method to make both eligible Gemini vision providers unavailable without changing secrets.
- **Action:** Repeat: **“Describe exactamente lo que ves en mi pantalla.”**
- **Expected result:** Captured bytes flow through bounded Gemini failures to loopback Ollama once; a coherent answer is returned.
- **Observable evidence:** Provider sequence in logs and Ollama request; no second capture.
- **PASS:** Ollama produces the response through the integrated JARVIS chain.
- **FAIL:** Remote Ollama URL accepted, endless retry, silent timeout, no fallback or false cloud attribution.
- **Logs:** `logs/jarvis.log`, local Ollama logs.
- **Dependencies:** Ollama/model, safe Gemini-failure setup.

### PHY-008

- **Area:** Ollama offline and cloud recovery
- **Preparation:** Restore Gemini availability; stop Ollama.
- **Action:** Run screen analysis once with Gemini available, then reproduce an eligible cloud failure while Ollama is stopped; finally restore the network and repeat.
- **Expected result:** Cloud path works; dual-provider failure is explicit and bounded; restored cloud works on a later request.
- **Observable evidence:** Correct provider/error sequence and recovery.
- **PASS:** No hang/reconnect storm and later request succeeds.
- **FAIL:** Silent failure, stale error after recovery or uncontrolled retries.
- **Logs:** `logs/jarvis.log`, Ollama service log.
- **Dependencies:** Ability to stop/start Ollama and safely change network/provider availability.

## Phase C — Windows, files and browser, same JARVIS session

### PHY-009

- **Area:** Windows application/window control
- **Preparation:** Spotify and Notepad installed; no unsaved documents.
- **Action:** Say **“Abre Spotify”**, **“Abre el Bloc de notas”**, **“Pon el foco en Spotify”**, then **“Cierra el Bloc de notas.”**
- **Expected result:** Intended applications only are launched/focused/closed.
- **Observable evidence:** Visible windows and process state.
- **PASS:** Correct target each time, no shell window or unrelated app.
- **FAIL:** Wrong app, duplicate launch, focus failure or false spoken success.
- **Logs:** `logs/jarvis.log` tool results.
- **Dependencies:** Installed apps.

### PHY-010

- **Area:** Keyboard / mouse / screenshot
- **Preparation:** Open a disposable text file in Notepad and position a safe target.
- **Action:** Ask JARVIS to type **“Prueba segura de JARVIS 2026”**, select/copy/paste it, take a screenshot to the disposable folder, and perform one safe click/scroll.
- **Expected result:** Exact Unicode-safe text and requested input actions; screenshot exists and opens.
- **Observable evidence:** Text/file contents and cursor behavior.
- **PASS:** Exact actions once, within intended window.
- **FAIL:** Wrong window, lost accents, repeated input, unsafe click or missing screenshot.
- **Logs:** `logs/jarvis.log` computer-control results.
- **Dependencies:** PyAutoGUI permissions, disposable file.

### PHY-011

- **Area:** Files / PDF / DOCX / XLSX / image
- **Preparation:** Disposable samples and folder.
- **Action:** Ask JARVIS to list/read/copy/rename a sample; summarize the PDF; explain the DOCX; analyze the XLSX; describe the image; then delete only a disposable copy.
- **Expected result:** Correct content/result files; original samples preserved; deletion is recoverable.
- **Observable evidence:** Files on disk, Recycle Bin item, accurate summaries/statistics.
- **PASS:** Every requested result matches the source and paths stay scoped.
- **FAIL:** Original overwritten/deleted, path escape, wrong content, AI model error or false success.
- **Logs:** `logs/jarvis.log`, generated output paths.
- **Dependencies:** Sample files, Gemini text/vision, Office parsers.

### PHY-012

- **Area:** Controlled browser
- **Preparation:** Chrome closed or safe to open with JARVIS profile.
- **Action:** Ask JARVIS to open `example.com`, read its heading, open a second tab, search for a harmless query, go back/forward/reload, take a screenshot and close all controlled sessions.
- **Expected result:** One controlled session performs each action and all `BrowserThread-*` workers terminate on close.
- **Observable evidence:** Correct pages/screenshot; no leftover controlled browser/thread after close.
- **PASS:** Actions succeed and cleanup is complete.
- **FAIL:** Profile error, wrong page, timeout hang, zombie browser/thread or personal tab damage.
- **Logs:** `logs/jarvis.log`, Task Manager.
- **Dependencies:** Chrome, network, Playwright channel.

### PHY-013

- **Area:** Browser failure/recovery
- **Preparation:** Continue after PHY-012.
- **Action:** Request an invalid/unreachable address, then request `https://example.com` again.
- **Expected result:** First request returns a bounded explicit error; next request starts/uses a healthy session.
- **Observable evidence:** Error duration and successful recovery page.
- **PASS:** No 60-second-plus runaway, stuck worker or stale error.
- **FAIL:** Hang, crash, reconnect storm or no recovery.
- **Logs:** `logs/jarvis.log`, Task Manager.
- **Dependencies:** Browser control.

## Phase D — accounts, media, reminders, presentations and developer tools

### PHY-014

- **Area:** Web/research
- **Preparation:** Network available.
- **Action:** Say: **“Investiga las novedades oficiales de Python y dame las fuentes; no guardes nada fuera de la sesión.”**
- **Expected result:** Current source-backed answer, progress visible, citations usable, no unsolicited file write.
- **Observable evidence:** Sources opened/returned and research result.
- **PASS:** Relevant current sources and explicit completion.
- **FAIL:** Fabricated sources, stale unsupported claims, hang or unwanted write.
- **Logs:** `logs/jarvis.log`, research progress/task result.
- **Dependencies:** Network/providers.

### PHY-015

- **Area:** Gmail authentication/read
- **Preparation:** Test Gmail account available.
- **Action:** Connect/sign in, list unread messages, search a known test subject and read its multipart body.
- **Expected result:** OAuth/login completes visibly; correct account content is returned; credentials are not logged.
- **Observable evidence:** Known message data and authenticated status.
- **PASS:** Correct mailbox results with no secret exposure.
- **FAIL:** Wrong account, login loop, missing body, token in logs or false success.
- **Logs:** Sanitized `logs/jarvis.log`; Gmail OAuth/browser errors.
- **Dependencies:** Gmail account/OAuth, browser, network.

### PHY-016

- **Area:** Gmail compose/approval/send/cancel/recovery
- **Preparation:** Safe recipient controlled by owner.
- **Action:** Prepare an email with unique subject; inspect it; cancel. Prepare again, explicitly approve and send. Then revoke/expire auth and verify explicit unauthenticated behavior before reconnecting.
- **Expected result:** No send before approval; cancellation discards; approved mail arrives once; auth failure is explicit and recovery works.
- **Observable evidence:** Visible fields, Sent/recipient inbox, no duplicate.
- **PASS:** Exact recipient/subject/body and one approved delivery only.
- **FAIL:** Premature/duplicate send, wrong fields, hidden auth failure or leaked token.
- **Logs:** Sanitized email/browser logs.
- **Dependencies:** Gmail test account/recipient.

### PHY-017

- **Area:** Spotify / YouTube / system media
- **Preparation:** Logged-in media apps and harmless playback volume.
- **Action:** Ask to play a known track, pause, resume, next and previous; then search/play one YouTube item.
- **Expected result:** Intended player and media respond once.
- **Observable evidence:** Visible player state and audible media.
- **PASS:** Correct provider/track and controls.
- **FAIL:** Wrong app/content, duplicate windows or unsupported action claimed as success.
- **Logs:** `logs/jarvis.log` media results.
- **Dependencies:** Spotify/YouTube login, network.

### PHY-018

- **Area:** Reminders / persistence
- **Preparation:** Choose a time 3–5 minutes ahead; Task Scheduler accessible.
- **Action:** Ask: **“Recuérdame a las HH:MM comprobar la prueba física.”** Restart JARVIS before the time.
- **Expected result:** One OS task persists; one notification appears at the correct local time; helper cleans itself as designed.
- **Observable evidence:** Task Scheduler entry, notification and cleanup.
- **PASS:** Exactly one timely notification survives JARVIS restart.
- **FAIL:** Wrong time, duplicate, missing notification, unsafe command or stale helper.
- **Logs:** `logs/jarvis.log`, Task Scheduler history.
- **Dependencies:** Windows Task Scheduler/notifications.

### PHY-019

- **Area:** Presentations
- **Preparation:** PowerPoint installed; disposable source document.
- **Action:** Ask JARVIS to create a short presentation from the source, open it, edit one title, extend it by one slide and export PDF.
- **Expected result:** Valid editable PPTX, visible modifications, valid PDF, progress/cancel UI coherent.
- **Observable evidence:** Files open successfully in PowerPoint/PDF viewer.
- **PASS:** Content matches request and source is not overwritten.
- **FAIL:** Corrupt deck, missing edit/slide, invalid PDF, source overwrite or false completion.
- **Logs:** `logs/jarvis.log`, presentation task/result artifacts.
- **Dependencies:** Gemini, PowerPoint, source file.

### PHY-020

- **Area:** Codex / code helper
- **Preparation:** Disposable Git-free project; owner-approved command only.
- **Action:** Ask JARVIS/Codex to generate and run a tiny Python program, introduce a deterministic test failure, then request a fix.
- **Expected result:** Work remains inside disposable project; command output and failure/fix are accurately reported.
- **Observable evidence:** Files, test output and bounded subprocess lifetime.
- **PASS:** Correct working program after fix with no unrelated edits/processes.
- **FAIL:** Workspace escape, destructive command, false PASS, timeout leak or unrelated modification.
- **Logs:** `logs/jarvis.log`, project output.
- **Dependencies:** Codex/toolchain as configured.

### PHY-021

- **Area:** Claude Code
- **Preparation:** Same disposable project; Claude Code authenticated.
- **Action:** Request a harmless explanation/edit, then temporarily make the CLI unavailable or unauthenticated and repeat; restore it and retry.
- **Expected result:** Success when available, explicit bounded failure when unavailable, recovery after restoration.
- **Observable evidence:** CLI output and scoped diff.
- **PASS:** No false success or stale process; recovery works.
- **FAIL:** Hang, credential exposure, unrelated edits or no recovery.
- **Logs:** `logs/jarvis.log`, sanitized CLI output.
- **Dependencies:** Claude Code CLI/auth.

## Phase E — LILITH, Home Assistant and persistence/recovery

### PHY-022

- **Area:** JARVIS ↔ LILITH / persistent memory
- **Preparation:** LILITH online; choose a unique harmless fact.
- **Action:** Say **“Guarda de forma persistente en LILITH que mi código de prueba es 6427.”** Search it, restart JARVIS, search again, then explicitly delete it.
- **Expected result:** One LILITH store, retrieval before/after restart and confirmed deletion; no competing local persistent write.
- **Observable evidence:** FunctionCall IDs/correlation and LILITH response.
- **PASS:** Exactly-once lifecycle with post-delete absence.
- **FAIL:** Duplicate write, local JSON write, lost restart state or false delete.
- **Logs:** `logs/jarvis.log` sanitized tool/correlation entries; LILITH logs.
- **Dependencies:** LILITH integration.

### PHY-023

- **Area:** Local session memory authority
- **Preparation:** New JARVIS session; LILITH online for observing that it is not called.
- **Action:** Say **“No lo guardes en LILITH; recuerda solo durante esta sesión que mi número temporal es 88.”** Retrieve it; restart JARVIS; ask again.
- **Expected result:** Same-session retrieval succeeds, zero LILITH store calls, value absent after restart.
- **Observable evidence:** Tool logs and answers.
- **PASS:** Authority boundary is exact.
- **FAIL:** LILITH write, persistence across restart or inability to retrieve in-session.
- **Logs:** `logs/jarvis.log` memory guard/tool calls; LILITH request log.
- **Dependencies:** Gemini Live.

### PHY-024

- **Area:** Routines
- **Preparation:** LILITH online; no conflicting routine.
- **Action:** Say **“Crea una rutina para encender la bombilla del mueble todos los días a las 9 de la noche en Madrid.”** Then list, inspect history and delete it.
- **Expected result:** Only `lilith_routine` is used; schedule is daily 21:00 Europe/Madrid; lifecycle is confirmed.
- **Observable evidence:** FunctionCall ID, `SCHEDULE_GUARD`, correlation and LILITH list/delete.
- **PASS:** Exact schedule and one create/delete, no `reminder` or immediate home action.
- **FAIL:** Wrong time/timezone/tool, duplicate side effect or false confirmation.
- **Logs:** `logs/jarvis.log` `SCHEDULE_GUARD` and `TOOL_CALL`; LILITH routine logs.
- **Dependencies:** Gemini Live, LILITH routines.

### PHY-025

- **Area:** Home Assistant action/approval
- **Preparation:** Record initial state of one harmless light; LILITH/HA online.
- **Action:** Say **“Enciende [nombre exacto de la luz].”** Exercise approval if requested, verify state, then say **“Apaga [nombre].”**
- **Expected result:** LILITH resolves one entity, executes only after required approval and verifies/restores state.
- **Observable evidence:** Physical light state plus HA/LILITH state response.
- **PASS:** Intended entity only, correct final restored state.
- **FAIL:** Wrong entity, bypassed approval, scheduled misroute, false state or duplicate action.
- **Logs:** JARVIS tool/correlation logs, LILITH and HA logs.
- **Dependencies:** Owner-approved HA device.

### PHY-026

- **Area:** LILITH/HA offline and recovery
- **Preparation:** Continue after restoring the light; ability to stop LILITH or disconnect its API safely.
- **Action:** Make LILITH unavailable; request a read-only health/status and a harmless HA read/resolve. Restore LILITH and repeat.
- **Expected result:** Explicit offline errors with bounded retry/backoff and no claimed action; later calls recover.
- **Observable evidence:** Retry timing, no HA mutation, successful post-restore response.
- **PASS:** No reconnect storm/duplicate job and recovery succeeds.
- **FAIL:** False success, uncontrolled retries, stale client or mutation during uncertainty.
- **Logs:** JARVIS and LILITH service logs.
- **Dependencies:** Safe service stop/start access.

## Phase F — shutdown, restart and soak

### PHY-027

- **Area:** Gemini/WebSocket/network recovery
- **Preparation:** JARVIS active with a completed conversation turn.
- **Action:** Briefly disconnect network during an active but harmless request; wait through bounded reconnect; restore network and ask a context-dependent follow-up.
- **Expected result:** RECONNECTING is visible, no storm/duplicate session, connection returns and durable context is retained.
- **Observable evidence:** Attempt/delay logs, one recovered answer.
- **PASS:** Recovery within configured attempts with retained context.
- **FAIL:** Infinite loop, duplicate answer/session, lost context or frozen HUD.
- **Logs:** `logs/jarvis.log` `LIVE_SESSION`/reconnect entries.
- **Dependencies:** Controllable network, Gemini.

### PHY-028

- **Area:** Graceful shutdown/reopen
- **Preparation:** Complete one conversation fact and ensure no task is writing a file.
- **Action:** Say **“JARVIS, apágate.”** Wait for farewell and process exit. Reopen normally and ask about the last durable conversation context.
- **Expected result:** Farewell finishes, processes/threads/browser sessions close, state persists as designed, reopen starts one healthy instance.
- **Observable evidence:** Task Manager, logs and restored-context answer.
- **PASS:** Clean exit/reopen without zombie process or corrupt state.
- **FAIL:** PC shutdown, forced hang, orphan process, duplicate instance or lost/corrupt continuity.
- **Logs:** shutdown/startup and persistence entries in `logs/jarvis.log`.
- **Dependencies:** Running JARVIS.

### PHY-029

- **Area:** Long-duration stability
- **Preparation:** Fresh reopened instance; Task Manager columns for CPU, memory, handles and threads visible.
- **Action:** Run JARVIS for 30 minutes with several voice turns, two browser open/close cycles, mute/unmute and one vision request. Do not test high-impact actions.
- **Expected result:** Stable responsiveness; no monotonic runaway in memory/handles/threads; no duplicate background jobs.
- **Observable evidence:** Start/end resource snapshot and logs.
- **PASS:** No crash, unbounded growth, reconnect storm, zombie browser or repeated task.
- **FAIL:** Sustained runaway, deadlock, crash or resource leak symptoms.
- **Logs:** `logs/jarvis.log`, Task Manager screenshots/measurements.
- **Dependencies:** All normal runtime services.

## Result recording

For every ID record: date/time, HEAD, PASS/FAIL/NOT RUN, concise evidence, relevant sanitized log timestamps and any issue ID. Never include API keys, OAuth tokens, authorization headers or personal email content.
