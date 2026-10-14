# JARVIS User-Facing Function Audit

Date: 2026-10-13

Repository: `C:\JARVIS`

Baseline before this uncommitted fix: `72483e3039adb28d29117218ccf62279cec83909` (`origin/main` remains `bbe95a8`)
Scope: current user-facing functions, validation state, actual missing functionality, and remaining roadmap boundaries.

## 1. Executive verdict

JARVIS has 46 declared Gemini tools. Every declared tool has a schema and a real dispatcher path; no declared tool is a name-only placeholder. The current codebase implements the desktop Gemini Live interface, hosted interface, local Windows actions, screen/camera analysis, browser automation, web research, files, presentations, local/session memory, and typed LILITH integration.

JL-A10 is **CLOSED — physical owner E2E PASS** based on the owner's 2026-10-13 evidence:

- recurring creation used only `lilith_routine`;
- “10 de la noche” persisted as `22:00`;
- timezone persisted as `Europe/Madrid`;
- list and delete used `lilith_routine`;
- no incorrect `reminder` or `lilith_home_action` routing occurred.

Screen vision is also **PHYSICAL E2E PASS for the Gemini primary path**. The
owner invoked `screen_process`, captured 142,430 bytes, received a
`gemini-3.8-flash` description that matched the visible screen, and heard the
spoken result. This does not certify the full Ollama failover path, because the
primary Gemini request succeeded and Ollama was not invoked.

AUT-8 and AUT-9 remain **NOT STARTED**. This audit did not start schedulers, autonomous executors, redesign work, or unrelated implementation.

There is no newly discovered missing function inside the advertised 46-tool surface. The main remaining gap is supervised/live certification of hardware-, account-, application-, and network-dependent tools. That is validation work, not proof that their implementation is absent.

## 2. Evidence collected in this audit

- Verified `HEAD == origin/main == bbe95a8` before testing.
- Inspected canonical `docs/TASKS.md` and `docs/PROJECT_STATE.md`.
- Inspected the tool registry and `_execute_tool()` dispatch in `main.py`.
- Inspected `actions/screen_processor.py`, `actions/computer_control.py`, `actions/computer_settings.py`, `actions/browser_control.py`, `actions/web_search.py`, and `actions/deep_research.py`.
- Verified required local packages for screen capture, camera, vision, computer control, Playwright, web retrieval, HTML parsing, and HTTP requests.
- Verified Google Chrome exists at `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- After the local Ollama vision fallback, ran the focused vision/action/UI slice: **59 passed, 4 subtests passed, 0 failed**.
- After the `file_processor` text-model fix, ran its focused slice: **42 passed, 0 failed**.
- Ran the complete Windows Python suite: **455 passed, 77 skipped, 19 subtests passed, 0 failed**, with one third-party Python 3.14 deprecation warning.
- Ran automated QA: **5/5 checks passed**, P0=0, P1=0, P2=3.
- Ran capability self-test: **7 PASS, 1 WARN, 0 FAIL**. The warning is the missing live Gemini check in the test process; no Gemini API key was exposed or read by this audit.
- Ran `pip check`: no broken requirements.

The 77 skips are the documented historical first-run/tour specification, not 77 current-function failures.

## 3. Status definitions

| Status | Meaning in this audit |
|---|---|
| Fully implemented | Real schema, dispatcher and implementation exist, with meaningful automated evidence; physical evidence is included where the function inherently requires it. |
| Implemented, human/live validation pending | Code and automated contracts exist, but the real hardware, account, installed application, browser session, network provider, or physical device was not exercised end-to-end in this audit. |
| Partially implemented | A current advertised function has a known missing execution branch or only a placeholder implementation. |
| Not implemented | Explicitly deferred functionality with no current production implementation. |

## 4. Fully implemented functions

### Physically validated

| Function | Current evidence |
|---|---|
| Gemini Live microphone-to-tool path | Owner-operated spoken JL-A10 flow passed on the real runtime. |
| `lilith_routine` | Real voice create/list/delete passed; `22:00 Europe/Madrid` persisted correctly; wrong-tool routes were absent. |
| `screen_process` screen path | Real capture, Gemini primary analysis, accurate visible-content description, and spoken response passed. Camera and real Ollama failover remain separately gated. |

### Code-complete with automated functional evidence

| Functions | Evidence boundary |
|---|---|
| `file_controller`, `file_processor` | Scoped path checks, file-type handling, real isolated filesystem operations, recoverable deletion and dispatcher coverage. `file_processor extract_text` is live PASS; AI `explain` is source-fixed but requires owner retest. |
| `graphics_quality`, `jarvis_ui_control` | Enum/action validation plus current offscreen UI contract tests. |
| `agent_task`, `task_status` | Real task queue IDs, state, cancellation and failure handling. |
| `create_presentation` | Background workflow, editable PPTX production, source handling, progress/cancel semantics and output validation have dedicated tests. Microsoft PowerPoint PDF export remains environment-dependent. |
| `save_memory`, `local_memory_search` | In-process session-only storage/search and authority guards are implemented; restart intentionally clears this memory. Spoken local-only routing still belongs to supervised validation. |
| `lilith_memory_search`, `lilith_memory_store`, `lilith_memory_delete` | Persistent-authority routing, canonical keys, lifecycle contracts, duplicate suppression and zero-local-write regressions are implemented. |
| `lilith_health`, `lilith_runtime_status` | Typed client and dispatcher paths return real backend responses or explicit unavailability. |
| `lilith_docs_list`, `lilith_docs_read`, `lilith_docs_search` | Bounded typed read/search routes with server-side path policy. |
| `lilith_source_list`, `lilith_source_read`, `lilith_source_search` | Bounded typed source inspection routes with server-side allowlisting. |
| `lilith_git_status` | Read-only typed Git-status route. |
| `lilith_command_submit` | Correlation/idempotency fields and authoritative completion semantics are implemented. |

These LILITH tools are code-complete, but only `lilith_routine` received new owner-operated physical certification in the present acceptance report. Backend availability remains an operational dependency.

`file_processor` has a split live-validation state. Owner testing proved
`extract_text` can access and parse the real Markdown file. The same file with
`action=explain` failed twice with `404 NOT_FOUND` because its AI branch still
selected retired `gemini-2.5-flash`; it also emitted the no-tools AFC warning.
The source now resolves a dedicated non-Live text model through
`GEMINI_TEXT_MODEL` -> `config/api_keys.json:text_model` ->
`gemini-3.8-flash`, which the configured API enumerated with
`generateContent`. File-processing requests explicitly disable AFC. Automated
regressions pass, but `file_processor explain` remains **RETEST REQUIRED** until
the owner repeats the real file test.

## 5. Implemented but awaiting supervised human/live validation

All functions below have executable implementations and dispatch paths. The pending item is real-world certification, not basic construction.

| Area | Functions | What still needs supervised proof |
|---|---|---|
| Applications and Windows | `open_app`, `computer_settings`, `computer_control`, `desktop_control` | Launch/focus the intended app; real keyboard/mouse/window/settings effects; explicit shutdown/restart confirmation; display scaling and multimonitor behavior. |
| Camera vision | `screen_process` with `angle=camera` | Real camera selection/frame, analysis, spoken result and resource release. Screen vision has passed physically. |
| Controlled browser | `browser_control` | Real Chrome profile startup plus navigation, click, typing, form fill, read, screenshot, tabs and closure under the owner's installed browser/session state. |
| Web and external data | `web_search`, `weather_report`, `flight_finder`, `deep_research` | Live provider/network behavior, current-result quality, source traversal, quota/fallback behavior and visible/background browser experience. |
| Messaging and email | `check_messages`, `prepare_message_reply`, `send_message`, `email_control` | Real account OAuth/session state, correct recipient/draft verification, explicit approval and actual platform send/cancel behavior. |
| Media | `youtube_video`, `media_control` | Real installed browser/player behavior, playback controls and optional save behavior. |
| Local reminders | `reminder` | Real Windows notification at the requested one-shot time; recurring requests are already prevented from using this route. |
| Development tools | `code_helper`, `dev_agent` | Supervised generation/run/build against an owner-approved workspace and installed toolchain. Hosted mode correctly excludes arbitrary `code_helper`. |
| Game management | `game_updater` | Real Steam/Epic installation discovery, update/schedule behavior and high-impact shutdown boundary. |
| LILITH Home Assistant | `lilith_home_action`, `lilith_request_approval`, `lilith_resolve_approval` | One safe owner-approved device action, approval flow and restored final state on the real HA installation. |
| Local-memory voice authority | `save_memory`, `local_memory_search` through Gemini Live | Speak an explicit local/session-only request and prove zero `lilith_memory_store` calls, then retrieve it in the same session. The deterministic guard is implemented and tested. |

Additional live-quality gates remain: echo behavior, barge-in, audio-device loss/reconnect, display scaling and a 30-minute soak.

## 6. Partially implemented functions

No declared Gemini tool is currently identified as a placeholder or as missing its principal dispatch implementation.

There are, however, bounded capability limitations that must not be overstated:

- `screen_process` captures one screen image or one camera frame for analysis; this is not continuous autonomous visual monitoring.
- `computer_control` and `computer_settings` can confirm that an input/subprocess action was issued, but cannot universally prove the final semantic state of every third-party Windows application.
- `browser_control` controls a dedicated Playwright-managed session/profile; it is not arbitrary control of every already-open personal browser window.
- `web_search` and `deep_research` depend on network/provider availability and may use documented fallbacks.
- PDF export from presentation creation depends on Microsoft PowerPoint being available.
- Provider-specific messaging support depends on the user's installed applications, login state and platform UI remaining compatible.

These are scope/dependency limits, not evidence that the current implementation is a stub.

## 7. Not implemented or deliberately deferred

The following are not part of the current production feature set:

- AUT-8 and AUT-9.
- A new autonomous scheduler/executor loop.
- LILITH-native wake word, Whisper/local STT or LILITH-native production voice.
- The historical cinematic first-run/tour UI specification retained in skipped tests.
- A new GUI redesign.
- New memory stores, Home Assistant clients or duplicate routine systems.

They must not be reported as regressions because the canonical scope explicitly defers or excludes them.

## 8. Specific verification: screen vision / screen analysis

**Status: screen capture, Gemini primary analysis, and spoken response physically validated; camera and real Ollama failover remain gated.**

The first owner-operated physical test proved that real screen capture works,
producing a 177,473-byte image. Analysis then failed explicitly with
`404 NOT_FOUND` because `actions/screen_processor.py` selected the retired
`gemini-2.5-flash` model. The Gemini API recommended `gemini-3.8-flash`.

The source now resolves the analysis model as
`GEMINI_VISION_MODEL` -> `config/api_keys.json:vision_model` ->
`gemini-3.8-flash`. The owner repeated the physical test after that fix. The obsolete-model 404 and
the AFC warning were both gone, and screen capture again passed (103,142 bytes),
but two real analysis requests failed with upstream `503 UNAVAILABLE` high
demand responses. The source now applies bounded SDK retry for 503 and then a
single configurable stable multimodal fallback (`gemini-3.6-flash`). It does
not retry or fall back for 429 or permanent 4xx failures.

Ollama 0.40.3 is now locally reachable on loopback and its API reports
`qwen3-vl:4b` with vision capability. An isolated local smoke used a synthetic
image and correctly read its visible test text. The integrated final chain now
reuses the already captured/compressed bytes and original question:
`gemini-3.8-flash` -> eligible `gemini-3.6-flash` fallback -> one bounded local
`qwen3-vl:4b` request -> explicit error. Local configuration is centralized,
defaults to a credential-free loopback URL, and rejects remote endpoints.

The owner then repeated the microphone/screen test on the real runtime:
`screen_process` captured a 142,430-byte image, selected
`gemini-3.8-flash`, and returned a description matching the visible ChatGPT
browser session and AURORA terminal. JARVIS spoke that result. This establishes
physical PASS for screen capture, Gemini primary visual analysis, and spoken
delivery. It does not establish physical PASS for Ollama inside the full
provider chain because Gemini primary succeeded, so neither cloud fallback nor
Ollama was invoked in this owner test.

Actual implementation found:

- `screen_process` is declared and dispatched from Gemini Live.
- Screen capture uses `mss`; camera capture uses OpenCV.
- Images are resized/compressed and sent to `google.genai` vision generation.
- Eligible Gemini availability failures can reuse those exact bytes with local Ollama; no second capture is taken.
- The prompt explicitly forbids guessing unreadable UI details.
- Capture and analysis errors are returned/spoken instead of inventing a visual answer.
- The GUI provides a source-aware camera/screen preview with bounded placement and graphics-quality-dependent refresh cadence.
- Automated tests cover compression, result-to-speech handoff, capture failure and preview lifecycle.

What remains unproved after the successful owner retest:

- actual camera selection/frame;
- local Ollama failover inside the complete real JARVIS provider chain;
- multimonitor expectations beyond the implementation's chosen screen;
- long-running resource/reconnect behavior.

Verdict: physical screen capture, Gemini primary visual analysis, and spoken
visual response are **PASS**. The obsolete-model and AFC regressions are
**FIXED**. Cloud 503 resilience is **AUTOMATED PASS**, and the isolated local
Ollama visual smoke is **PASS**. Ollama as the final fallback inside the
complete real provider chain is **NOT YET PHYSICALLY EXERCISED**.

## 9. Specific verification: Windows/computer control

**Status: implemented; supervised real-action validation pending.**

Actual implementation found:

- Direct keyboard, text, click, double-click, right-click, mouse move/drag, hotkey, key press, scrolling, clipboard, screenshot, wait, field clearing and window focus.
- AI-assisted `screen_find` and `screen_click` based on a fresh screenshot.
- System settings include volume, brightness, window management, tabs/navigation shortcuts, screenshot, lock, settings, Explorer, display sleep, dark mode, Wi-Fi and explicit power actions.
- Screenshots are constrained to safe paths.
- PyAutoGUI failsafe is enabled.
- Restart/shutdown require an explicit computer/system target and a separate confirmation; requests to shut down JARVIS do not power off the PC.
- QA mode blocks unsafe real side effects during automated testing.

The self-test reports SYSTEM PASS with live check required. No keyboard/mouse, Wi-Fi, power or window mutation was performed by this audit.

Verdict: code-complete control surface with meaningful safety contracts, but not a blanket guarantee that every command works against every real Windows application.

## 10. Specific verification: browser/web capabilities

**Status: implemented; live network/session certification remains partly pending.**

Controlled browser:

- Playwright implementation supports browser selection, sessions, navigation/search, selector or text click, typing, scrolling, form fill, smart visual click/type, page text/URL, key presses, tabs, screenshot, history, reload and close.
- Chrome is installed on this Windows machine and the Python Playwright dependency is present.
- No Playwright cache is installed, but the implementation can use the installed Chrome channel; absence of that cache alone is not a missing function.
- The capability self-test reports BROWSER PASS.
- Dedicated real-profile/session behavior was not driven interactively in this audit.

Web access:

- `web_search` uses Gemini grounded search first and installed DuckDuckGo search fallback.
- `deep_research` performs multiple searches, deduplicates valid URLs, can browse sources visibly, synthesizes cited Markdown, retains results in memory until explicitly saved, supports fallback synthesis, progress and cancellation.
- Tests cover planning, results, citations, fallback, visible/background choice, save/read actions and cancellation, but network/Gemini calls are mocked for determinism.

Verdict: browser and web functions exist and pass automated contracts; current live account/profile/network behavior still needs a supervised smoke before being called universally certified.

## 11. Actual remaining work separated by type

### A. Actual missing functionality

None found inside the current advertised 46-tool contract. Deliberately deferred AUT-8/AUT-9, native LILITH voice, autonomous execution and redesign work remain outside scope.

### B. Human/live tests

1. Camera analysis and a deliberately induced full-provider Ollama failover on the owner's hardware; the Gemini primary screen path has passed physically.
2. Supervised Windows keyboard/mouse/window/settings actions.
3. Controlled browser against the installed Chrome/profile.
4. Live web/search/research provider smoke.
5. Real messaging/email OAuth, approval and send/cancel flows.
6. Real media, reminder, game-launcher and flight workflows as applicable.
7. One safe HA action with state restoration and approval if required.
8. Explicit local-memory voice override.
9. Echo, barge-in, device reconnect, display scaling and 30-minute soak.

### C. P2 technical debt / refactoring

- Migrate nine secondary modules from deprecated `google.generativeai` to `google.genai`.
- Reduce 492 broad `except Exception` handlers and improve structured error/correlation reporting.
- Separate legacy JSON memory compatibility from active prompt construction under an approved migration plan.
- Constrain remaining frontend `latest` ranges and address development-only transitive advisories without breaking production.
- Split large `main.py`/`ui.py` responsibilities only with behavioral parity tests.
- Replace the remaining fixed-candidate VS Code `shell=True` compatibility launcher.

These are maintainability/security-observability improvements, not missing user-facing features.

### D. P3 UI/accessibility and test-hygiene work

- Add accessible names to lesser-used controls.
- Expand display-scaling and second-monitor coverage.
- Replace hard-coded colors progressively with theme tokens.
- Separate test logs from runtime logs.
- Retire/archive the historical first-run/tour specification so its 77 skips are not misread.

## 12. Canonical documentation reconciliation

The source code and owner evidence establish JL-A10 as closed. This validation
block reconciles the active canonical documents accordingly:

- `docs/TASKS.md`
- `docs/PROJECT_STATE.md`
- `docs/TECHNICAL_DEBT.md` (`TD-001` moved to resolved)
- `docs/TESTING.md` human-gate evidence

The dated 2026-10-08 recovery audit remains unchanged as historical evidence.
AUT-8/AUT-9 remain not started. Camera validation and physical Ollama failover
remain open human-quality gates, not P1 blockers or missing implementations.

## 13. Strengths

- Every advertised tool has an actual route and implementation.
- High-impact routine and memory effects are guarded by turn/session/FunctionCall provenance and duplicate suppression.
- JL-A10 now has owner-operated physical evidence, including semantic time correctness.
- QA and tests are green on the real Windows checkout.
- Browser, vision and Windows-control code fails with explicit diagnostics instead of pretending success in the inspected principal paths.
- Current architecture keeps persistent state and HA authority in LILITH while preserving explicit session-only local memory.

## 14. Problems and severity

| Severity | Finding |
|---|---|
| P2 validation | Powerful Windows/browser/account/device tools remain supervised-integration pending. |
| P2 observability | 492 broad exception handlers can hide actionable failure detail. |
| P2 dependency | Nine secondary modules still use deprecated `google.generativeai`. |
| P2 maintainability | `main.py` and `ui.py` remain large and coupled. |
| P2/P3 UI | Accessibility names, scaling proof and theme-token consistency are incomplete. |

## 15. Final verdict

**Machine baseline: PASS.**

**JL-A10 physical E2E: PASS / CLOSED.**

**Current advertised tool surface: implemented; no name-only tools found.**

**Universal live certification: not yet complete for camera/Ollama failover, Windows control, browser/network, accounts, HA and long-running hardware quality.**
**AUT-8/AUT-9: NOT STARTED.**

The correct next step is documentation reconciliation plus narrowly scoped supervised smokes for the existing tools. It is not new feature development.
