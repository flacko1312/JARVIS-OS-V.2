# JARVIS — Full Technical Audit

**Date**: 2026-10-16
**Branch**: main
**HEAD**: 500b14d
**Auditor**: automated from-scratch audit (Claude)
**Source of truth**: executable code > tests > config > git > metadata > docs

---

## 1. Executive Summary

JARVIS is a substantial Windows desktop assistant (main.py: 5222 lines, ui.py: 8701 lines) built on Gemini Live for voice interaction, PyQt6 for the GUI, and an extensible tool system with 48 declared tools. It includes a hosted web surface (FastAPI + Next.js), a typed LILITH boundary for persistent memory/routines/Home Assistant, and a GREEN observational infrastructure layer (18 components, 372 tests).

**Current automated state**: 1174 passed, 93 skipped, 0 failed, 49 subtests passed.
All tests green after fixing EXPECTED_TOOLS (commit 500b14d) and catalog tool reference (this follow-up).

---

## 2. Repository Structure

| Directory | Files | Purpose |
|-----------|-------|---------|
| `.` (root) | main.py, ui.py, ui_locale.py, runtime.py | Desktop entry point, GUI, locale, LILITH bridge |
| `actions/` | 27 .py | Tool action implementations (~19,142 lines) |
| `agent/` | 4 .py | Multi-step agent executor, planner, task queue (~1,687 lines) |
| `api/` | 14 .py | FastAPI hosted server, auth, DB, WebSocket |
| `lilith_client/` | 5 .py | Typed HTTP client for LILITH server |
| `router/` | 4 .py | Spanish-language intent classifier + routing |
| `memory/` | 6 .py | Memory manager, answer cache, conversation store |
| `core/` | 23 .py (non-green) | Gemini config, vision, QA, secrets, scheduling |
| `core/green/` | 18 .py | GREEN observational infrastructure |
| `core/green/tests/` | 18 .py | GREEN test suite (372 tests) |
| `tests/` | 73 .py | Root test suite |
| `web/` | 11 source files | Next.js 16 + React + Tailwind frontend |
| `scripts/` | 7 .py | QA, setup, soak monitor, E2E scripts |
| `config/` | 1 .py | OS detection, api_keys.json loader |
| `awareness/` | 1 .py | Context-awareness engine (current app, project) |
| `alembic/` | 1 migration | Hosted multi-tenant DB schema |

**Total Python files**: ~196 (excluding .venv, node_modules)
**Largest files**: ui.py (8701), main.py (5222), tests/test_lilith_gemini_tools.py (2520), actions/presentation_maker.py (2028), actions/send_message.py (1891)

---

## 3. Tool System Audit

### 3.1 Declarations

**48 tool declarations** in `main.py` TOOL_DECLARATIONS (lines 986–2177). All 48 have matching dispatch handlers in `_execute_tool`.

Complete tool inventory:

| # | Tool | Domain | Dispatch |
|---|------|--------|----------|
| 1 | date_time | System | Inline |
| 2 | open_app | Windows | _lazy_action |
| 3 | web_search | Knowledge | _lazy_action |
| 4 | weather_report | Knowledge | _lazy_action |
| 5 | check_messages | Communication | _lazy_action |
| 6 | prepare_message_reply | Communication | _lazy_action |
| 7 | send_message | Communication | _lazy_action |
| 8 | email_control | Communication | _lazy_action |
| 9 | reminder | Reminders | _lazy_action |
| 10 | youtube_video | Multimedia | _lazy_action |
| 11 | media_control | Multimedia | _lazy_action |
| 12 | screen_process | Vision | _lazy_action |
| 13 | computer_settings | System | _lazy_action |
| 14 | browser_control | Browser | _lazy_action |
| 15 | file_controller | Files | _lazy_action |
| 16 | desktop_control | Windows | _lazy_action |
| 17 | code_helper | Development | _lazy_action |
| 18 | dev_agent | Development | _lazy_action |
| 19 | agent_task | Development | Inline |
| 20 | computer_control | Windows | _lazy_action |
| 21 | game_updater | Windows | _lazy_action |
| 22 | flight_finder | Knowledge | _lazy_action |
| 23 | graphics_quality | System | Inline |
| 24 | jarvis_ui_control | UI | Inline |
| 25 | deep_research | Knowledge | _lazy_action |
| 26 | create_presentation | Presentations | _lazy_action |
| 27 | task_status | System | Inline |
| 28 | file_processor | Files | _lazy_action |
| 29 | save_memory | Memory | Inline (guarded) |
| 30 | local_memory_search | Memory | Inline (guarded) |
| 31 | lilith_memory_search | LILITH | Inline (guarded) |
| 32 | lilith_memory_store | LILITH | Inline (guarded) |
| 33 | lilith_memory_delete | LILITH | Inline (guarded) |
| 34 | lilith_home_action | LILITH/HA | Inline (guarded) |
| 35 | lilith_request_approval | LILITH | Inline |
| 36 | lilith_resolve_approval | LILITH | Inline |
| 37 | lilith_health | LILITH | Inline |
| 38 | lilith_runtime_status | LILITH | Inline |
| 39 | lilith_docs_list | LILITH | Inline |
| 40 | lilith_docs_read | LILITH | Inline |
| 41 | lilith_docs_search | LILITH | Inline |
| 42 | lilith_source_list | LILITH | Inline |
| 43 | lilith_source_read | LILITH | Inline |
| 44 | lilith_source_search | LILITH | Inline |
| 45 | lilith_git_status | LILITH | Inline |
| 46 | lilith_command_submit | LILITH | Inline |
| 47 | lilith_routine | LILITH | Inline (guarded) |
| 48 | open_capabilities_catalog | GREEN | Inline |

### 3.2 Guards

- **Memory mutation guard**: save_memory, lilith_memory_store, lilith_memory_delete — provenance, duplicate FC ID, ambiguous authority, authority classification
- **Memory lookup guard**: local_memory_search, lilith_memory_search — suppresses unless explicit user intent
- **Schedule guard**: lilith_home_action, reminder, lilith_routine — provenance, FC ID reuse, schedule semantics, rerouting, wrong-tool blocking
- **Cloud-safe filter**: 6 tools allowed in hosted mode (web_search, deep_research, create_presentation, flight_finder, email_control, youtube_video)
- **Batch serialization**: 29 mutating tools run sequential; read-only concurrent

### 3.3 Lazy Actions

23 `_lazy_action` wrappers from 15 unique action modules. Tools without lazy wrappers are handled inline in `_execute_tool`: date_time, save_memory, local_memory_search, agent_task, task_status, graphics_quality, jarvis_ui_control, open_capabilities_catalog, and all 17 lilith_* tools.

---

## 4. Gemini Live & Audio

- **SDK**: `google.genai` async Live API (main.py)
- **Live model**: `gemini-2.5-flash-native-audio-preview-12-2025` (env: `GEMINI_LIVE_MODEL`, then config, then default; model discovery with fallback)
- **Text model**: `gemini-3.8-flash` (desktop), `gemini-2.5-flash` (hosted chat default)
- **Vision model**: `gemini-3.8-flash` (fallback: `gemini-3.6-flash`)
- **Ollama fallback**: `qwen3-vl:4b-instruct` (vision), `qwen3:4b` (text)
- **Audio**: mono PCM16, 16kHz input / 24kHz output, sounddevice
- **Voice**: configurable (default: puck), unsupported voices fallback to puck
- **Continuity**: durable local conversation store across standby/reconnect/restart
- **Session resumption**: native Gemini handles when valid; compact durable context in system_instruction otherwise

---

## 5. Authority Chain

```
USER → Gemini Live → JARVIS Authority → guards → tool/LILITH → result
                                          ↓ (shadow)
                                    GREEN observability
```

- JARVIS owns: HUD/UI, microphone/audio, Gemini session, Spanish policy, tool dispatch, Windows actions, session memory
- LILITH owns: persistent personal memory, routines, Home Assistant, approvals
- Gemini owns: language/reasoning/tool selection (not authority for side effects)
- GREEN: passive observation only, never changes routing/authorization/results

---

## 6. Actions & Agents Audit

### 6.1 Action Modules (27 files, ~19,142 lines)

Largest: presentation_maker.py (2028), send_message.py (1891), email_control.py (1547), instagram_browser.py (1161), safe_text_entry.py (1076), game_updater.py (1050), file_processor.py (1044)

### 6.2 SDK Usage

**Old `google.generativeai`** (7 files): computer_settings, desktop, flight_finder, youtube_video, executor, planner, error_handler
**New `google.genai`** (8 files): computer_control, code_helper, deep_research, file_processor, web_search, screen_processor, presentation_maker, send_message

### 6.3 shell=True Usage

3 locations:
- actions/computer_settings.py (2 occurrences) — system commands
- actions/dev_agent.py (1 occurrence) — VS Code launcher (tracked as TD-008)

### 6.4 Agent System

- **executor.py** (595 lines): multi-step plan execution with tool calls and file-save detection
- **planner.py** (467 lines): Gemini-powered step-by-step plan generation
- **task_queue.py** (428 lines): priority-based concurrent task queue with cancel
- **error_handler.py** (197 lines): failure analysis with retry/skip/replan/abort strategy

---

## 7. API & Hosted Surface

### 7.1 FastAPI Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /health | No | Health check |
| POST | /auth/signup | No | User registration (rate-limited 5/hr) |
| POST | /auth/login | No | Authentication (rate-limited 10/5min) |
| GET | /auth/me | Yes | Current user profile |
| POST | /auth/logout | Yes | Logout (no-op) |
| POST | /me/gemini-key | Yes | Store/verify Gemini key (rate-limited 8/hr) |
| DELETE | /me/gemini-key | Yes | Delete Gemini key |
| GET | /status | Yes | Live session status |
| GET | /actions | Yes | Cloud-safe tool list |
| POST | /chat | Yes | Text chat (rate-limited 30/min) |
| WS | /ws | Yes | Gemini Live audio/text streaming |

### 7.2 Database

Single Alembic migration: users, user_secrets, memory_entries tables. SQLAlchemy ORM with parameterized queries (no SQL injection risk observed).

### 7.3 Web Frontend

Next.js 16 + React + Tailwind + Radix UI. 11 source files:
- layout.tsx, page.tsx — app shell
- auth-screen.tsx, onboarding.tsx — auth flow
- jarvis-console.tsx — main chat interface
- reactor.tsx — visual reactor component
- use-jarvis-socket.ts — WebSocket hook (PCM audio, JSON events)
- api.ts — HTTP API client

### 7.4 Infrastructure

- **Docker**: postgres:17-alpine, redis:7-alpine, Python API, Node web
- **CI**: GitHub Actions on ubuntu-latest with postgres+redis (3 test modules)
- **Deploy**: Manual workflow_dispatch — Fly.io (API) + Vercel (web)
- **Render**: render.yaml with auto-generated JWT/encryption keys

---

## 8. LILITH Integration

`LilithClient` — async httpx client with bearer auth, retry, structured errors. Methods cover: health, runtime, docs (list/read/search), source (list/read/search), git, commands, memory (search/context/store/delete), Home (entity/action/resolve), approvals (request/resolve), notifications.

Router classifier: 15 domains, regex-based Spanish intent classification. MEMORY and HOME require LILITH; other domains pass through to Gemini.

---

## 9. Memory System

| Store | Classification | Scope |
|-------|---------------|-------|
| LILITH memory API | ACTIVE CANONICAL | Persistent personal facts |
| JarvisLive._local_session_memory | SESSION-ONLY | Explicit local notes |
| memory/long_term.json | LEGACY COMPAT | Older prompt paths |
| Hosted SQL | ACTIVE CANONICAL | Per-user hosted accounts |
| conversation_store.py | ACTIVE LOCAL | Durable conversation state |

Memory authority: explicit persistent → LILITH, explicit local → session, ambiguous → nowhere (request clarification).

---

## 10. GREEN Foundation

18 components across foundation (10) and runtime (8) layers. **3541 total lines** (documentation previously claimed 2763 — stale by +778 lines). 372 tests across 18 test files (verified accurate). All feature-flagged OFF by default.

8 feature flags: JARVIS_EXECUTION_TRACE_ENABLED, JARVIS_EVENT_BUS_ENABLED, JARVIS_TOOL_REGISTRY_ENABLED, JARVIS_RAG_ENABLED, JARVIS_CAPABILITIES_RUNTIME_ENABLED, JARVIS_BUDGET_GUARD_ENABLED, JARVIS_SKILLS_RUNTIME_ENABLED, JARVIS_RAG_RUNTIME_ENABLED.

All GREEN components follow shadow/passive integration: observe only, never authorize or change dispatch. Exceptions isolated from user-facing execution. Rollback = set flags to "0".

---

## 11. GUI

**ui.py**: 8701 lines, 23 widget classes including:
- MainWindow (QMainWindow) — primary window
- HudCanvas — holographic HUD display
- HolographicCoreCanvas — core visualization
- MissionControlPanel — metrics/control panel
- ChatBubbleWidget, FocusDialogueWidget — conversation display
- ResearchProgressWidget, ToolProgressWidget — progress indicators
- FileDropZone — file upload handling
- VisionPreviewWindow — vision preview
- SetupOverlay — initial setup
- Various metric/sparkline/agent grid widgets

**ui_locale.py**: Spanish locale strings for UI labels.

---

## 12. Test Suite Summary

| Category | Passed | Skipped | Failed |
|----------|--------|---------|--------|
| Root tests/ | 801 | 93 | 1 |
| GREEN core/green/tests/ | 372 | 0 | 0 |
| Subtests | 49 | — | — |
| **Total** | **1173** | **93** | **1** |

**No failures** after commit 500b14d (EXPECTED_TOOLS fix) — 1174 passed, 0 failed

**93 skips**: 77 historical UI spec (first-run/tour never existed), remainder platform/config skips.

**1 warning**: Python 3.14 google.genai typing deprecation.

---

## 13. Configuration & Environment

### Feature Flags (GREEN)

All default OFF via `os.environ.get("JARVIS_*_ENABLED", "0") == "1"` pattern.

### Runtime Config

| Variable | Purpose | Default |
|----------|---------|---------|
| GEMINI_API_KEY | Primary API key | Required |
| GEMINI_LIVE_MODEL | Live model override | gemini-2.5-flash-native-audio-preview |
| GEMINI_VOICE_NAME | Voice selection | puck |
| JARVIS_ENV | Environment mode | development |
| JARVIS_QA_MODE | QA safety mode | off |
| LILITH_API_URL | LILITH server URL | unset |
| LILITH_API_KEY | LILITH bearer token | unset |
| DATABASE_URL | Hosted Postgres | (hosted only) |
| REDIS_URL | Rate limiting Redis | (hosted only) |
| JWT_SECRET | API auth signing | (hosted only) |
| JARVIS_ENCRYPTION_KEY | Secret encryption | (hosted only) |

---

## 14. Security Findings

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| S-1 | Low | Default JWT secret in non-production (production validates) | api/config.py:29 |
| S-2 | Low | Dev-only compose credentials (marked change-before-deploy) | docker-compose.yml |
| S-3 | P2 | shell=True in 3 locations (fixed paths, not arbitrary input) | computer_settings.py, dev_agent.py |
| S-4 | P2 | 492+ broad except Exception handlers | TD-003 |
| S-5 | OK | No SQL injection: SQLAlchemy ORM throughout | — |
| S-6 | OK | WebSocket tokens not in URLs (fixed) | — |
| S-7 | OK | Rate limiting on all auth/write endpoints | — |
| S-8 | OK | Secret redaction in conversation persistence | conversation_store.py |
| S-9 | OK | GREEN RAG excludes secrets from indexing | rag_runtime.py |

---

## 15. Technical Debt (Current)

| ID | P | Description |
|----|---|-------------|
| TD-001 | P3 | Optional robustness checks not physically validated |
| TD-002 | P2 | Deprecated google.generativeai in 7 files |
| TD-003 | P2 | 492+ broad except Exception handlers |
| TD-004 | P2 | Legacy JSON memory coexists with LILITH canonical |
| TD-005 | P2 | Frontend `latest` dependency ranges |
| TD-006 | P2 | main.py (5222) and ui.py (8701) are very large |
| TD-007 | P2 | Hard-coded color literals, partial accessibility |
| TD-008 | P2 | shell=True in VS Code launcher |
| TD-009 | P3 | 77 skipped historical UI tour tests |
| TD-010 | P3 | Test log entries mix with runtime logs |
| TD-011 | P3 | Python 3.14 google.genai deprecation warning |

---

## 16. Bugs Found

| # | Severity | Description | Location | Status |
|---|----------|-------------|----------|--------|
| B-1 | P1 | EXPECTED_TOOLS set missing `open_capabilities_catalog` — causes test failure | core/qa_audit.py:12 | ✅ FIXED (commit 500b14d) |
| B-2 | P2 | Capability catalog entry missing `tools=["open_capabilities_catalog"]` — catalog counted 47 not 48 | core/green/capability_catalog.py:689 | ✅ FIXED (this follow-up) |
| B-3 | Info | Hosted chat model default (`gemini-2.5-flash`) differs from desktop text model (`gemini-3.8-flash`) | api/config.py:36 vs core/text_model.py:8 | Unresolved inconsistency — separate env vars (`JARVIS_CHAT_MODEL` / `GEMINI_TEXT_MODEL`), likely stale API default. Not a runtime bug — review when deploying. |

---

## 17. Documentation Reconciliation

| Document | Issue | Status |
|----------|-------|--------|
| ARCHITECTURE.md | Tool count 46→48 | ✅ FIXED this audit |
| PROJECT_STATE.md | Tool count 46→48, date 10-14→10-16 | ✅ FIXED this audit |
| CHANGELOG.md | Tool count annotation | ✅ FIXED this audit |
| JARVIS_CAPABILITIES.md | Regenerated at 500b14d, now 48 tools | ✅ FIXED this follow-up |
| GREEN_FOUNDATION.md | Line counts updated (3541 total) | ✅ FIXED prior audit |
| GREEN_RUNTIME_INTEGRATION_HANDOFF.md | HEAD updated to f625583 | ✅ FIXED prior audit |
| TESTING.md | Date 10-13, still accurate | ✅ OK |
| TECHNICAL_DEBT.md | Accurate, no new entries needed | ✅ OK |
| TASKS.md | Accurate, no changes needed | ✅ OK |
| LILITH_INTEGRATION.md | Accurate for LILITH contract | ✅ OK |
| QA.md | References macOS; Windows is primary | ⚠️ Minor |
| PHYSICAL_TEST_PLAN_V2.md | 27 tests, accurate | ✅ OK |

---

## 18. Physical Test Status

**27 supervised tests** in PHYSICAL_TEST_PLAN_V2.md. None performed by this audit (machine audit only).

Previously validated physically:
- JL-A10: CLOSED / PHYSICAL E2E PASS
- F8 pause/resume continuity: PASS
- Screen vision: PASS
- Full-restart conversation continuity: PASS

Pending physical validation:
- Forced Gemini transport recovery
- 24-hour soak
- Camera/Ollama failover chain
- All 27 tests in V2 plan

---

## 19. Dirty Worktree

8 modified tracked files (pre-existing, NOT from this audit):
- actions/browser_control.py (1811 lines changed — near-complete rewrite)
- actions/file_processor.py (8 lines)
- api/websocket_client.py (10 lines)
- docs/JARVIS_CAPABILITIES.md (4 lines)
- docs/audits/AUTONOMOUS_COMPLETION_STATE.md (4 lines)
- docs/audits/AUT_14_GIT_CHECKPOINT.md (3 lines)
- docs/audits/JARVIS_POST_AUTONOMOUS_AUDIT.md (11 lines)
- tests/test_screen_processor.py (4 lines)

16 untracked files: audit block docs (BLOCK_01–08, JARVIS_FINAL_AUDIT, PHYSICAL_TEST_PLAN) and block test files (test_block1–6).

---

## 20. CI/CD

- **CI**: GitHub Actions on push/PR to main. Ubuntu + postgres:17 + redis:7. Runs 3 backend test modules + frontend lint/typecheck/build.
- **Deploy**: Manual workflow_dispatch. API → Fly.io (sjc region, 1GB shared VM). Web → Vercel.
- **Render**: render.yaml available as alternative.
- **Note**: CI runs only 3 of 73 test files. Full test suite is a local-only operation.

---

## 21. Verdict

JARVIS is a feature-rich, well-guarded desktop assistant with a healthy automated baseline (1173/1174 tests passing). The architecture is real and executable — docs largely match code with the tool-count discrepancies now fixed. The GREEN observational layer is complete, tested, and properly isolated. The single test failure (B-1) is a minor contract gap, not a functional bug. Security posture is reasonable for a desktop application with hosted capability. The 11 tracked technical debt items are accurate and prioritized.

**Remaining work for full audit completion**:
1. Fix B-1 (add `open_capabilities_catalog` to EXPECTED_TOOLS)
2. Regenerate JARVIS_CAPABILITIES.md from current 48-tool metadata
3. Verify GREEN line counts and instrumentation line numbers against current main.py
4. Complete physical test plan execution (27 tests, owner-operated)
