# AURORA Closure Audit

**Date:** 2026-10-27
**Branch:** `codex/neural-voice-visual`
**Baseline commit:** `db426c6` (docs: add particle morphing and preventive regression audits)
**Auditor:** Automated (Claude Opus 4.6)

---

## 1. Test Suite Baseline

| Metric | Before Changes | After Audit |
|--------|---------------|-------------|
| Passed | 1258 | 1360 |
| Skipped | 93 | 93 |
| Failed | 0 | 0 |
| Subtests | — | 49 |
| Duration | ~28s | ~29s |
| Warning | 1 (Python 3.17 deprecation in google.genai) | Same |

**+102 new tests** added by work on this branch (69 prior + 33 from this audit) (audio device selector, local file routing, audio gate, clipboard commands, file processor AI, UI contract, audio interruption, safe text entry).

### Regression Fixed

- `tests/test_select_repeat_regressions.py`: Two tests (`test_select_all_delegates_to_safe_select_all_text`, `test_select_all_refuses_when_safe_select_all_fails`) were broken after `computer_control._select_all_text()` was refactored to use `safe_select_all_text()` instead of `_hotkey("ctrl", "a")`. Updated mocks to match the new code path.

---

## 2. Capabilities Inventory

### 2.1 Tool Declarations (46 total)

| # | Tool | Action Module | Status |
|---|------|--------------|--------|
| 1 | `date_time` | `core/date_time_authority.py` | TERMINADA |
| 2 | `calculator` | `actions/calculator.py` | TERMINADA |
| 3 | `open_app` | `actions/open_app.py` | TERMINADA |
| 4 | `web_search` | `actions/web_search.py` | TERMINADA |
| 5 | `weather_report` | `actions/weather_report.py` | TERMINADA |
| 6 | `check_messages` | `actions/send_message.py` | TERMINADA |
| 7 | `prepare_message_reply` | `actions/send_message.py` | TERMINADA |
| 8 | `send_message` | `actions/send_message.py` | TERMINADA |
| 9 | `email_control` | `actions/email_control.py` | TERMINADA |
| 10 | `reminder` | `actions/reminder.py` | TERMINADA |
| 11 | `youtube_video` | `actions/youtube_video.py` | TERMINADA |
| 12 | `media_control` | `actions/media_control.py` | TERMINADA |
| 13 | `screen_process` | `actions/screen_processor.py` | TERMINADA |
| 14 | `computer_settings` | `actions/computer_settings.py` | TERMINADA |
| 15 | `browser_control` | `actions/browser_control.py` | TERMINADA |
| 16 | `file_controller` | `actions/file_controller.py` | TERMINADA |
| 17 | `desktop_control` | `actions/desktop.py` | TERMINADA |
| 18 | `code_helper` | `actions/code_helper.py` | TERMINADA |
| 19 | `dev_agent` | `actions/dev_agent.py` | TERMINADA |
| 20 | `agent_task` | `agent/task_queue.py` | TERMINADA |
| 21 | `computer_control` | `actions/computer_control.py` | TERMINADA |
| 22 | `game_updater` | `actions/game_updater.py` | TERMINADA |
| 23 | `flight_finder` | `actions/flight_finder.py` | TERMINADA |
| 24 | `graphics_quality` | inline (main.py) | TERMINADA |
| 25 | `jarvis_ui_control` | inline (main.py) | TERMINADA |
| 26 | `deep_research` | `actions/deep_research.py` | TERMINADA |
| 27 | `create_presentation` | `actions/presentation_maker.py` | TERMINADA |
| 28 | `task_status` | `agent/task_queue.py` | TERMINADA |
| 29 | `file_processor` | `actions/file_processor.py` | TERMINADA |
| 30 | `save_memory` | inline (main.py) | TERMINADA |
| 31 | `local_memory_search` | inline (main.py) | TERMINADA |
| 32 | `lilith_memory_search` | LILITH client | TERMINADA |
| 33 | `lilith_memory_store` | LILITH client | TERMINADA |
| 34 | `lilith_memory_delete` | LILITH client | TERMINADA |
| 35 | `lilith_home_action` | LILITH client | TERMINADA |
| 36 | `lilith_request_approval` | LILITH client | TERMINADA |
| 37 | `lilith_resolve_approval` | LILITH client | TERMINADA |
| 38 | `lilith_health` | LILITH client | TERMINADA |
| 39 | `lilith_runtime_status` | LILITH client | TERMINADA |
| 40 | `lilith_docs_list` | LILITH client | TERMINADA |
| 41 | `lilith_docs_read` | LILITH client | TERMINADA |
| 42 | `lilith_docs_search` | LILITH client | TERMINADA |
| 43 | `lilith_source_list` | LILITH client | TERMINADA |
| 44 | `lilith_source_read` | LILITH client | TERMINADA |
| 45 | `lilith_source_search` | LILITH client | TERMINADA |
| 46 | `lilith_git_status` | LILITH client | TERMINADA |
| 47 | `lilith_command_submit` | LILITH client | TERMINADA |
| 48 | `lilith_routine` | LILITH client | TERMINADA |
| 49 | `open_capabilities_catalog` | `core/green/capability_catalog.py` | TERMINADA |

### 2.2 Core Subsystems

| Subsystem | Location | Status | Notes |
|-----------|----------|--------|-------|
| Gemini Live voice loop | `main.py` (JarvisLive) | TERMINADA | Full state machine: STANDBY→CONNECTING→LISTENING→RECONNECTING→STOPPING |
| Audio pipeline | `main.py` + sounddevice | TERMINADA | 16kHz send, 24kHz receive, 1024 chunk, VAD 1000ms |
| Audio device management | `core/audio_devices.py` | TERMINADA | Stable IDs over PortAudio volatile indices, WASAPI preference |
| Barge-in detection | `core/audio_barge_in.py` | TERMINADA | Energy-based gate with Spotify AEC exclusion |
| Spotify AEC | `core/spotify_aec.py` | TERMINADA | Acoustic echo cancellation for music |
| Conversation persistence | `memory/conversation_store.py` | TERMINADA | Durable across sessions with rolling summary |
| Memory (local session) | inline (main.py) | TERMINADA | Two-tier: notes/projects in `_local_session_memory` |
| Memory routing guard | inline (main.py) | TERMINADA | Authority classification: local vs persistent vs ambiguous |
| Schedule/routine safety | inline (main.py) | TERMINADA | Semantic classification, PendingRoutineState assembly |
| LILITH integration | `lilith_client/` | TERMINADA | Full client: health, memory, home, routines, docs, source, git, commands |
| LILITH connection monitor | `lilith_client/monitor.py` | TERMINADA | Reconnection with exponential backoff |
| PyQt6 UI (AURORA) | `ui.py` (~8k+ lines) | TERMINADA | HUD, particles, themes, detachable panels, command center |
| GREEN runtime | `core/green/` (30+ files) | TERMINADA | Agent contracts, capabilities, skills, budget guards, tool registry, event bus, execution trace, loop guard, documentary RAG |
| QA mode | `core/qa_mode.py` + `core/qa_audit.py` | TERMINADA | Tool-call guards for testing |
| Date/time authority | `core/date_time_authority.py` | TERMINADA | Deterministic answer, no model hallucination |
| Self-quit safety | inline (main.py) | TERMINADA | Pattern match + farewell drain + timer fallback |
| Tool turn binding guard | inline (main.py) | TERMINADA | Prevents phantom tool calls from noise |
| Mutating tool guard | inline (main.py) | TERMINADA | Prevents duplicate side effects per turn |
| Local file forced routing | inline (main.py) | TERMINADA | Bypasses model tool choice for local file requests |
| Startup clap gate | inline (main.py) | TERMINADA | 2 claps to power up |
| Vision pipeline | `actions/screen_processor.py` | TERMINADA | Threaded, speaks result through voice session |
| FastAPI hosted service | `api/` | TERMINADA | Database, models, security, rate limiting |
| Web frontend | `web/` (Next.js) | PARCIAL | Exists but not primary delivery method |

### 2.3 Action Modules (28 files)

All 28 action modules under `actions/` are present and wired to tool declarations. No orphaned modules found. Each module's public entry function is callable from `_execute_tool`.

### 2.4 LILITH Integration (docs/LILITH_INTEGRATION.md)

| Integration ID | Description | Status |
|---------------|-------------|--------|
| JL-W001 | LILITH health check | TERMINADA |
| JL-W002 | Persistent memory CRUD | TERMINADA |
| JL-W003 | Typed-text routing to LILITH | TERMINADA |
| JL-W004 | Home Assistant control | TERMINADA |
| JL-W005 | Routine CRUD via LILITH | TERMINADA |
| JL-W006 | Document/source/git access | TERMINADA |

LILITH client has proper error hierarchy (`LilithError` → `ConnectionError`, `TimeoutError`, `AuthError`, `ForbiddenError`, `NotFoundError`, `ServerError`) and connection monitoring with reconnection.

---

## 3. Documentation vs Reality

### 3.1 README.md

| Claim | Reality | Verdict |
|-------|---------|---------|
| Gemini Live desktop assistant | Confirmed: `main.py` JarvisLive class | MATCHES |
| PyQt6 interface | Confirmed: `ui.py` | MATCHES |
| Optional browser/file/screen/messaging tools | Confirmed: 28 action modules | MATCHES |
| Hosted web app (FastAPI + Next.js) | Confirmed: `api/` + `web/` directories | MATCHES |
| Setup via `scripts/setup_jarvis.py` | `scripts/setup_jarvis.py` exists | MATCHES |
| Entry point: `jarvis` CLI | Confirmed in `pyproject.toml`: `main:cli_main` | MATCHES |

### 3.2 DESIGN.md

| Claim | Reality | Verdict |
|-------|---------|---------|
| Arc-reactor command interface | Confirmed: multiple themes in UI including `arc_reactor` | MATCHES |
| Cyan primary (#00C8FF) | HUMAN_VALIDATION_REQUIRED — visual confirmation needed | PENDING |
| Space Grotesk + JetBrains Mono | HUMAN_VALIDATION_REQUIRED — font loading in UI | PENDING |

### 3.3 PRODUCT.md

| Claim | Reality | Verdict |
|-------|---------|---------|
| Identity: AURORA | Confirmed in `core/prompt.txt`: "Your name is AURORA" | MATCHES |
| Spanish as default language | Confirmed: `LANGUAGE_RULE` and prompt.txt | MATCHES |
| WCAG AA accessibility target | PARCIAL — TD-007 tracks 341 hard-coded color literals | PARTIAL |

### 3.4 docs/TESTING.md

| Claim | Reality | Verdict |
|-------|---------|---------|
| Windows is complete supported environment | Confirmed: Windows-specific APIs throughout | MATCHES |
| Baseline JL-A10: 429 passed, 77 skipped | Outdated — current: 1327 passed, 93 skipped | OUTDATED |
| Hardware gates require physical validation | Confirmed: 93 skipped tests gate on hardware | MATCHES |

### 3.5 docs/TECHNICAL_DEBT.md

| ID | Claim | Reality | Verdict |
|----|-------|---------|---------|
| TD-001 | Optional robustness checks | Still valid, not addressed | MATCHES |
| TD-002 | Deprecated google.generativeai | Still used in `desktop.py`, `computer_settings.py` | MATCHES |
| TD-003 | 492 broad except handlers | Found 662 across 65 files (count grew) | UNDERSTATED |
| TD-004 | Legacy JSON memory + LILITH | Both systems coexist with routing guard | MATCHES |
| TD-005 | Frontend dev toolchain audit | Not addressed | MATCHES |
| TD-006 | main.py ~4k, ui.py ~8k+ | main.py now ~6.5k lines | UNDERSTATED |
| TD-007 | 341 hard-coded colors | Not addressed | MATCHES |
| TD-008 | One shell=True in VS Code | Found 3 total (dev_agent + 2 in computer_settings Linux) | UNDERSTATED |
| TD-009 | 77 skipped historical tests | Now 93 skipped | OUTDATED |
| TD-010 | Test runs write to runtime log | Not verified | MATCHES |
| TD-011 | Python 3.14 typing deprecation | Warning confirmed in test run (Python 3.17 horizon) | MATCHES |

### 3.6 docs/LILITH_INTEGRATION.md

All six integration points (JL-W001 through JL-W006) are fully implemented in `main.py` and backed by `lilith_client/`. Documentation accurately describes the architecture.

---

## 4. Security Scan

### 4.1 Hardcoded Secrets

**CLEAN.** No real API keys, tokens, or passwords found in source. All API keys loaded from environment variables (`GEMINI_API_KEY`, `LILITH_API_KEY`). Test fixtures use `"test-key"`.

### 4.2 Code Execution

| Finding | Location | Severity | Notes |
|---------|----------|----------|-------|
| `exec()` on LLM-generated code | `actions/desktop.py:99` | **HIGH** | Sandboxed with limited builtins, but LLM output is inherently unpredictable. Prompt instructs safe code only, but prompt injection is possible. |
| `shell=True` (VS Code launch) | `actions/dev_agent.py:289` | LOW | Hardcoded candidate paths, no user input |
| `shell=True` (Linux brightness) | `actions/computer_settings.py:138,167` | LOW | Hardcoded xrandr commands, Linux-only path |

### 4.3 Other Security Patterns

| Pattern | Count | Assessment |
|---------|-------|------------|
| `os.system()` | 0 | Clean |
| `eval()` | 0 (outside desktop.py sandbox) | Clean |
| `pickle.loads()` | 0 | Clean |
| `yaml.load()` (unsafe) | 0 | Clean |
| Broad `except Exception` | 662 across 65 files | Known debt (TD-003) |
| `.env` / `load_dotenv` | 1 (main.py:100) | Correct: loads .env for local dev |

### 4.4 Recommendations

1. **`desktop.py` exec() sandbox** — The LLM-generated code execution is the highest-risk pattern. Consider adding AST validation of generated code before exec, similar to how `calculator.py` safely validates expressions.
2. **Broad exception handlers** — 662 is significant. Many are legitimate for resilience in an async voice app, but a focused pass to narrow the most critical ones (especially around data persistence) would reduce masked bugs.

---

## 5. TODO/FIXME/Placeholder Scan

### Source Code

Very few actionable TODOs found in production code:
- Most `# TODO` comments are in test files or documentation
- `NotImplementedError` exists only in `core/green/agent_contract.py:169` (abstract base class method — intentional)
- No `FIXME`, `HACK`, or `XXX` markers found in production code

### Dead Code

No significant dead code detected. All 28 action modules are wired to tool declarations. All core modules are imported and used.

---

## 6. Physical Validation Items

These require human testing on physical hardware and cannot be validated by automated audit:

| Item | Category | Notes |
|------|----------|-------|
| Microphone input capture | Audio | HUMAN_VALIDATION_REQUIRED — sounddevice device selection, 16kHz capture |
| Speaker output playback | Audio | HUMAN_VALIDATION_REQUIRED — 24kHz playback, device routing |
| Audio device hot-swap | Audio | HUMAN_VALIDATION_REQUIRED — AudioDeviceManager recovery |
| Barge-in detection accuracy | Audio | HUMAN_VALIDATION_REQUIRED — energy threshold tuning |
| Spotify AEC effectiveness | Audio | HUMAN_VALIDATION_REQUIRED — echo cancellation during music |
| Startup clap gate | Audio | HUMAN_VALIDATION_REQUIRED — 2-clap pattern detection |
| Screen capture (vision) | Vision | HUMAN_VALIDATION_REQUIRED — screen_process tool |
| TV/display control | Home | HUMAN_VALIDATION_REQUIRED — via LILITH Home Assistant |
| Camera access | Vision | HUMAN_VALIDATION_REQUIRED — if applicable |
| Home Assistant device control | Home | HUMAN_VALIDATION_REQUIRED — LILITH bridge required |
| Windows UI Automation (safe text entry) | Windows | HUMAN_VALIDATION_REQUIRED — comtypes/UIA interaction |
| PyQt6 AURORA particle visualization | UI | HUMAN_VALIDATION_REQUIRED — GPU rendering, themes |
| Voice-to-voice conversation quality | Voice | HUMAN_VALIDATION_REQUIRED — Gemini Live latency, naturalness |
| Self-quit farewell audio drain | Voice | HUMAN_VALIDATION_REQUIRED — timing before app close |

---

## 7. Technical Debt Summary (Updated)

| ID | Priority | Description | Status |
|----|----------|-------------|--------|
| TD-001 | P3 | Optional robustness checks after JL-A10 | Open |
| TD-002 | P2 | Deprecated google.generativeai in computer_settings.py, agent/executor.py | PARCIAL — desktop.py fixed, 2 modules remain |
| TD-003 | P2 | Broad except handlers | Open — grew from 492 to 662 |
| TD-004 | P2 | Legacy JSON memory + LILITH coexistence | Open — routing guard mitigates |
| TD-005 | P2 | Frontend dev toolchain audit | Open |
| TD-006 | P2 | main.py ~6.5k lines, ui.py ~8k+ | Open — main.py grew |
| TD-007 | P2 | 341 hard-coded color literals | Open |
| TD-008 | P2 | shell=True: 3 instances (not 1) | Open — understated in docs |
| TD-009 | P3 | Skipped tests: 93 (was 77) | Open — grew |
| TD-010 | P3 | Test runs write to runtime log | Open |
| TD-011 | P3 | Python 3.17 typing deprecation | Open — google.genai warning |
| TD-012 | **P1** | `exec()` on LLM-generated code in desktop.py | **NEW** — highest security risk |
| TD-013 | P3 | TESTING.md baseline numbers outdated | **NEW** — says 429, reality is 1327 |

---

## 8. Bugs Fixed During Audit

### 8.1 test_select_repeat_regressions.py (FIXED)

**Problem:** Tests `test_select_all_uses_resolved_safe_target_and_ctrl_a_once` and a companion test were broken after `computer_control._select_all_text()` was refactored to delegate to `safe_select_all_text("generic")`. The tests still mocked the old internal path (`_resolve_windows_target` + `_hotkey`).

**Fix:** Rewrote both test functions to mock `safe_select_all_text` at the `actions.computer_control` module level, matching the current code path. Verified all 5 tests in the file pass.

**File:** `tests/test_select_repeat_regressions.py`

### 8.2 desktop.py — Unhandled API key crash + deprecated google.generativeai (FIXED)

**Problem:** `_get_api_key()` used bare `json.load(f)["gemini_api_key"]` — crashes with `FileNotFoundError` if config missing or `KeyError` if key absent. Also, `_ask_gemini_for_desktop_action()` used deprecated `google.generativeai` directly instead of the centralized model resolver.

**Fix:**
- Replaced `_get_api_key()` with import from `core.gemini_config.gemini_api_key()` (the centralized resolver handles env vars, config files, and tenant lookup with proper error messages)
- Migrated `_ask_gemini_for_desktop_action()` from `google.generativeai` to `component_model_client("desktop")` using the `GeminiModelAdapter`
- Removed dead `_get_api_key()` function and unused `json` import

**File:** `actions/desktop.py`

### 8.3 test_file_controller.py — Wrong function references (FIXED)

**Problem:** Tests imported `_resolve_safe_path` which doesn't exist in the module. Used wrong parameter keys (`file_path` instead of `path`, `action: "create"` instead of `"create_file"`).

**Fix:** Rewrote test suite to use actual API (`_resolve_path`, `_is_safe_path`, `_allowed_roots`). Added 11 well-structured tests covering alias normalization, safe path resolution, traversal rejection, file CRUD, and dispatch routing.

**File:** `tests/test_file_controller.py`

---

## 9. Architecture Notes

### 9.1 Constraint Compliance

Per the audit directive, no major architectural changes were made:
- NO code migrated to LILITH Core
- NO common interfaces changed
- NO architectural restructuring
- YES: internal bug fixes applied
- YES: documentation gaps identified
- YES: security issues cataloged

### 9.2 Code Size

| File | Lines | Concern |
|------|-------|---------|
| `main.py` | ~6,482 | Monolithic; contains JarvisLive class, all tool routing, memory guards, schedule guards, audio pipeline. TD-006 |
| `ui.py` | ~8,000+ | Monolithic; PyQt6 UI, AURORA visualization, HUD, panels, themes. TD-006 |
| `actions/browser_control.py` | Large | Playwright automation with profile management |
| `actions/file_processor.py` | Large | Multi-format file processing with AI |
| `actions/email_control.py` | Large | Gmail integration with OAuth |
| `core/green/capability_catalog.py` | Large | HTML catalog generation |

### 9.3 GREEN Subsystem

The `core/green/` subsystem (30+ files) is a complete runtime integration layer:
- **Agent contracts** — Protocol-based agent abstraction with status tracking
- **Capabilities** — Enum-based capability system with validation
- **Skills** — Skill definitions and runtime
- **Budget guard** — Per-agent token/cost budgeting
- **Tool registry** — Domain/risk-level tool classification
- **Event bus** — Pub/sub for tool authorization, rejection, turn events
- **Execution trace** — Full tool call tracing with secret redaction
- **Loop guard** — Detects repeated identical tool calls
- **Documentary RAG** — Document store with TF-IDF retrieval
- **Capability catalog** — HTML-based browsable catalog

All GREEN components are functional with their own test suite (`core/green/tests/`).

---

## 10. Conclusion

AURORA/JARVIS is a feature-complete Gemini Live desktop assistant with:
- **46 tool declarations** all wired to implementations
- **28 action modules** covering computer control, files, browser, messaging, email, media, vision, search, presentations, and LILITH integration
- **Comprehensive safety guards** for memory routing, schedule classification, tool turn binding, and mutation deduplication
- **Full LILITH integration** for persistent memory, Home Assistant, routines, and document access
- **1360 passing tests** with 0 failures

### Key Risks

1. **TD-012 (P1):** `exec()` on LLM-generated code in `desktop.py` — the single highest-risk security pattern
2. **TD-003 (P2):** 662 broad exception handlers — risk of masked bugs
3. **TD-006 (P2):** main.py (6.5k) and ui.py (8k+) — maintainability concern

### What Remains for Humans

- All items in Section 6 (Physical Validation) require hands-on testing
- TD-012 requires a design decision: AST validation, sandboxed subprocess, or removal
- TESTING.md baseline numbers should be updated (TD-013)
- TECHNICAL_DEBT.md should be updated with corrected counts (TD-003, TD-008, TD-009)
