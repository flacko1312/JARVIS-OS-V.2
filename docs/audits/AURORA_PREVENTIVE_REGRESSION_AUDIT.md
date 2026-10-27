# AURORA Preventive Regression Audit — 2026-10-25

## 1. Executive Summary

This audit was performed against the **live working tree** of `C:\JARVIS` on branch `main` at commit `b759b3f`. The working tree contains **12 modified files** and **11 untracked files/directories** representing active development of: audio device selection, calculator tool, local file processing with audio gating, voice style pacing, safe text entry improvements, and Aurora particle effects.

**Key findings:**
- ~~**40 out of 552 tests fail to collect**~~ — Root cause: interpreter mismatch (`py` launcher uses global Python, not `.venv`). `.venv\Scripts\python.exe -m pytest` collects **1427 tests, 0 errors**. `google-genai` 2.25.0 IS installed in `.venv`. Reclassified P0→P2.
- ~~**Calculator tool** missing from `EXPECTED_TOOLS`~~ — **FIXED**: added `calculator` to `EXPECTED_TOOLS` (qa_audit.py), `TOOL_DOMAIN_MAP`, `TOOL_RISK_MAP`, `TOOL_CAPABILITIES_MAP`, `TOOL_SIDE_EFFECTS` (tool_metadata.py). Reclassified P0→P2.
- **Local file routing** (audio gate, forced execution, denial recovery) is a large new subsystem with **no physical validation** yet.
- **Audio device selection** works via WASAPI endpoint filtering but **device hot-plug, Bluetooth reconnect, and index stability across reboots** have no physical validation.
- Multiple **cross-feature collision risks** exist (GoAway + tool execution, device switch + barge-in, F8 stop + running tool).
- **No critical P0 security issues found** — API keys are handled through ContextVar, no eval, no path escalation in calculator.

**Totals:** 32 findings — **P0: 0, P1: 8, P2: 16 (2 reclassified from P0, 1 fixed), P3: 8**

---

## 2. Current System Baseline

| Property | Value |
|---|---|
| HEAD | `b759b3f` |
| Branch | `main` |
| Python | 3.14.5 |
| PySide6/PyQt6 | 6.11.2 |
| google-genai | 2.25.0 (in `.venv`; absent from global Python — use `.venv` for tests) |
| Tests collected | 1427 (0 collection errors via `.venv`) |
| Entry point | `main.py → main() → JarvisUI + JarvisLive` |
| Gemini Live model | `models/gemini-2.5-flash-native-audio-preview-12-2025` |
| Default voice | Puck (configurable via GEMINI_VOICES) |
| Audio arch | PortAudio via sounddevice; WASAPI endpoint preferred; MME/DirectSound transport fallback |
| Modified files | 12 (main.py +398 lines, ui.py +260, safe_text_entry.py +78, file_processor.py +39, computer_control.py +17, prompt.txt +4, pyproject.toml +2, 5 test files) |
| Untracked | calculator.py, audio_devices.py, 4 test files, aurora_particles/, benchmark script, 2 audit docs |

---

## 3. System Architecture Map

```
USER
  ↓
┌─────────────────────┐
│  UI (ui.py / PyQt6) │ ← F8 toggle, F4 mute, text input, voice selector,
│  Aurora particles    │   audio device combos, settings panel, drag-drop
└─────────┬───────────┘
          ↓
┌─────────────────────────────────────────────────────┐
│  VOICE INPUT                   TEXT INPUT            │
│  sounddevice → PCM16           QLineEdit → speak()   │
│  BargeInGate → filter          or direct tool call   │
│  SpotifyAEC → suppress echo                          │
└─────────┬──────────────────────────┬────────────────┘
          ↓                          ↓
┌────────────────────────────────────────────────────┐
│  INTENT / ROUTING (main.py)                        │
│  _local_file_request_from_text() [NEW]             │
│  _local_file_recovery_from_denial() [NEW]          │
│  Audio gate (0.40s delay for transcription) [NEW]  │
│  Schedule routing guards                           │
│  Memory routing guards                             │
│  Mutating tool dedup guard                         │
│  QA mode gate                                      │
└─────────┬──────────────────────────────────────────┘
          ↓
┌────────────────────────────────────────────────────┐
│  TOOLS (_execute_tool / _execute_tool_guarded)     │
│  file_processor, calculator [NEW], computer_control│
│  safe_text_entry, browser_control, media_control   │
│  open_app, weather, email, send_message, reminder  │
│  screen_processor, dev_agent, code_helper          │
│  desktop_control, file_controller, game_updater    │
│  deep_research, presentation, youtube              │
│  jarvis_ui_control, graphics_quality               │
└─────────┬──────────────────────────────────────────┘
          ↓
┌────────────────────────────────────────────────────┐
│  GEMINI LIVE SESSION                               │
│  Bidirectional audio streaming                     │
│  Session resumption handles                        │
│  GoAway / playback drain                           │
│  Durable conversation continuity                   │
│  Initial history restoration                       │
└─────────┬──────────────────────────────────────────┘
          ↓
┌────────────────────────────────────────────────────┐
│  AUDIO OUTPUT                                      │
│  audio_in_queue → _play_audio() → sounddevice out  │
│  BargeInGate.observe_playback() for echo cancel    │
│  AudioDeviceManager → WASAPI endpoint resolution   │
└────────────────────────────────────────────────────┘

SIDE SYSTEMS:
┌──────────────┐  ┌───────────────┐  ┌──────────────┐
│ LILITH Bridge│  │ Memory Manager│  │ File Processor│
│ (gateway)    │  │ (local+LILITH)│  │ (genai client)│
│ Home Asst.   │  │ ConvStore     │  │ ContextVar key│
│ Routines     │  │ Persistence   │  │ Resolve paths │
└──────────────┘  └───────────────┘  └──────────────┘
┌──────────────┐  ┌───────────────┐  ┌──────────────┐
│ Computer Ctrl│  │ Audio Devices │  │ UI State      │
│ SafeTextEntry│  │ Manager [NEW] │  │ Themes/Panels │
│ UIA/Win32    │  │ Persistence   │  │ Graphics qual.│
│ Clipboard    │  │ WASAPI filter │  │ Layout persist│
└──────────────┘  └───────────────┘  └──────────────┘
┌──────────────┐  ┌───────────────┐
│ Recovery     │  │ GREEN runtime │
│ Mic recovery │  │ Tool registry │
│ Output recov.│  │ Event bus     │
│ Session recon│  │ Budget guard  │
└──────────────┘  └───────────────┘
```

**Shared state / cross-cutting:**
- `self.session` — single Gemini Live session handle (nullable)
- `self.audio_in_queue` / `self.out_queue` — asyncio queues, recreated per session
- `self._is_speaking` / `self._speaking_lock` — playback state
- `self._conversation_requested` / `self._shutdown_requested` — threading Events
- `self._session_resumption_handle` — GoAway recovery
- `self._barge_in_gate` — shared between input callback and gate logic
- `self._audio_device_manager` — shared between UI selectors and audio workers
- `self._local_session_memory` — in-process dict
- `_ACTIVE_GEMINI_API_KEY` (ContextVar) — file_processor API key injection
- `_WINDOWS_TARGET_CACHE` (module global) — safe text entry focus cache

---

## 4. Implementation Inventory

| Feature | Files | State | Automated Test | Physical Test | Risk |
|---|---|---|---|---|---|
| Gemini Live session | main.py:6025-6360 | ACTIVE | COLLECTION_ERROR | PASS_PHYSICAL (prior) | P1 |
| F8 conversation toggle | main.py:2710-2800 | ACTIVE | COLLECTION_ERROR | PASS_PHYSICAL (prior) | P2 |
| F4 mute | ui.py (muted property) | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P2 |
| Barge-in gate | core/audio_barge_in.py | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P1 |
| GoAway / playback drain | main.py:5401-5760 | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P1 |
| Audio device selector | core/audio_devices.py [NEW] | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P1 |
| Audio device persistence | audio_devices.json | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P2 |
| Local file routing | main.py:404-500 [NEW] | ACTIVE | test_local_file_*.py (COLLECTION_ERROR) | PHYSICAL_PENDING | P1 |
| Audio gate (0.40s) | main.py:5433-5535 [NEW] | ACTIVE | test_local_file_audio_gate.py (COLLECTION_ERROR) | PHYSICAL_PENDING | P1 |
| File processor explain | actions/file_processor.py | ACTIVE | test_file_processor_ai.py (COLLECTION_ERROR) | PHYSICAL_PENDING | P2 |
| API key injection (ContextVar) | file_processor.py:41 | ACTIVE | PARTIAL | PHYSICAL_PENDING | P2 |
| Calculator | actions/calculator.py [NEW] | ACTIVE | test_calculator_tool.py (COLLECTION_ERROR) | PHYSICAL_PENDING | P2 |
| SafeTextEntry (Windows UIA) | actions/safe_text_entry.py | ACTIVE | COLLECTION_ERROR | PARTIAL | P2 |
| Select-all (UIA/Win32) | actions/safe_text_entry.py:289-342 | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P2 |
| Computer control clipboard | actions/computer_control.py | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P2 |
| Voice style/pacing | main.py:186-192 [NEW] | ACTIVE | NONE | PHYSICAL_PENDING | P3 |
| Spanish language enforcement | main.py:178-184 | ACTIVE | COLLECTION_ERROR | PASS_PHYSICAL (prior) | P3 |
| Tool result truth rule | main.py:194-199 | ACTIVE | COLLECTION_ERROR | PARTIAL | P2 |
| Memory routing | main.py:226-253 | ACTIVE | COLLECTION_ERROR | PARTIAL | P2 |
| Durable conversation | memory/conversation_store.py | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P2 |
| LILITH bridge | core/lilith_gateway.py | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P2 |
| Home Assistant actions | via LILITH | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P2 |
| Schedule routing guards | main.py:4897-5136 | ACTIVE | COLLECTION_ERROR | PARTIAL | P2 |
| Microphone recovery | main.py:5260-5330 | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P1 |
| Output recovery | main.py:5830-5900 | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P1 |
| Aurora particles | aurora_particles/ [NEW] | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P3 |
| Graphics quality | ui.py + main.py | ACTIVE | COLLECTION_ERROR | PHYSICAL_PENDING | P3 |

---

## 5. Physical Validation Pending List

Features that have automated tests but **require real hardware/runtime validation**:

1. **Audio device selection** — input/output switching, persistence, hot-plug, Bluetooth, HDMI, USB
2. **Local file routing** — "Explícame el archivo prompt punto txt de JARVIS"
3. **Audio gate** — 0.40s delay, transcription arrival before/after audio
4. **Barge-in** — real speaker echo vs. user speech with various devices
5. **GoAway recovery** — mid-speech, mid-tool-call, queued output
6. **Microphone recovery** — device disconnection/reconnection
7. **Output recovery** — device disconnection/reconnection
8. **F4 mute** — interaction with device switch, reconnect, barge-in
9. **Select-all** — UIA TextPattern + Win32 EM_SETSEL across Notepad, browsers, Word
10. **Calculator via voice** — spoken Spanish operators
11. **File processor explain** — API key injection, long files, unsupported files
12. **Durable conversation** — restoration after GoAway, after F8 cycle
13. **Voice style pacing** — subjective quality of pauses and name usage

---

## 6. Critical Risks

### P0-001 → P2: Test collection fails under wrong interpreter
**Severity:** ~~P0~~ → **P2** (reclassified — environment config, not missing dependency)
**Cause:** `py` launcher resolves to global Python 3.14.5 which lacks `google-genai`. The canonical `.venv\Scripts\python.exe` has `google-genai` 2.25.0 installed and collects **1427 tests with 0 errors**.
**Impact:** Tests must be run with `.venv` interpreter. No runtime impact — AURORA launches from `.venv`.
**Fix:** Always run tests via `.venv\Scripts\python.exe -m pytest` (or activate `.venv` first).
**Evidence:** `.venv\Scripts\pip.exe show google-genai` → Version 2.25.0. `.venv\Scripts\python.exe -m pytest --collect-only` → 1427 tests, 0 errors.
**Status:** NOT BLOCKING — documented; canonical interpreter works.

### P0-002 → P2: Calculator missing from QA metadata — **FIXED**
**Severity:** ~~P0~~ → **P2** (reclassified — stale QA metadata, not data corruption or runtime failure)
**Cause:** `calculator` added to `TOOL_DECLARATIONS` (main.py:1320) and dispatched (main.py:3711), but not added to QA/GREEN metadata.
**Impact:** QA automated audit reported false tool inventory mismatch.
**Fix applied:** Added `"calculator"` to: `EXPECTED_TOOLS` (qa_audit.py), `TOOL_DOMAIN_MAP`, `TOOL_RISK_MAP`, `TOOL_CAPABILITIES_MAP`, `TOOL_SIDE_EFFECTS` (tool_metadata.py).
**Status:** RESOLVED.

---

## 7. Cross-Feature Collision Matrix

| Feature A | Feature B | Possible Failure | Severity | Likelihood | Current Protection | Missing Test | Recommended |
|---|---|---|---|---|---|---|---|
| Audio device switch | Barge-in | Gate holds stale playback fingerprints from old device; false accept/reject | P1 | Medium | `stop_playback()` resets gate | No test for switch-during-playback | Physical test: switch output mid-response |
| Audio device switch | Microphone recovery | Manual selection triggers recovery loop; double stream open | P1 | Medium | `_audio_input_switch_requested` Event | No integration test | Physical test: manual switch during recovery |
| File processor | Gemini Live reconnect | GoAway arrives during `_execute_forced_local_file_request`; session becomes None | P1 | Low-Med | `if self.session and result` check | No test | Add session-None guard after tool await |
| Tool call | GoAway | `pending_goaway` set during tool execution; tool result sent to dead session | P1 | Medium | Drain waits after turn_complete | No test for mid-tool GoAway | Audit GoAway timing vs tool batch |
| F8 stop | Tool still running | `_conversation_requested.clear()` while `_execute_tool` is awaiting thread | P2 | Medium | Tool runs to completion in thread | No test | Verify tool result is discarded if session closed |
| Microphone recovery | Manual device selection | Recovery reopens old device; manual selection reopens new device; race | P1 | Medium | `_audio_input_switch_requested` Event | No test | Physical test |
| Memory routing | Local file routing | "Guarda esto en el archivo X" misrouted as local file explain | P2 | Low | Separate regex patterns | No combined test | Add negative test for save+filename |
| Computer control | Focus change (JARVIS window) | Tool call triggers JARVIS window focus; target editor loses focus | P2 | Medium | `_resolve_windows_target` cache/reacquire | Tests exist but COLLECTION_ERROR | Physical test |
| UI restart | Persisted device index | PortAudio indices change between boots; persisted index points to wrong device | P1 | High | Stable hash-based device_id, not index | No reboot test | Physical test across reboot |
| Calculator | QA tool inventory | QA audit reports false tool mismatch | ~~P0~~ P2 | Certain | **FIXED** | No test | ~~Add to EXPECTED_TOOLS~~ Done |
| Voice style prompt | Tool routing prompt | Combined prompt too long for context window | P3 | Low | Prompt built by concatenation | No length test | Monitor prompt token count |
| Durable conversation | Session resumption | Stale handle + local continuity can duplicate context | P2 | Low-Med | Handle expiry + fallback | Tests exist but COLLECTION_ERROR | Physical test: long idle then resume |
| Audio gate (0.40s) | Fast tool-only response | Audio arrives before transcription; gate holds it; tool executes without audio | P2 | Medium | Gate releases at 0.40s or on turn_complete | test_local_file_audio_gate (COLLECTION_ERROR) | Physical test |
| Barge-in | Low mic level | Gate never reaches threshold; user can't interrupt | P2 | Medium | Adaptive noise floor (0.97 decay) | No test with near-threshold levels | Physical test with quiet mic |
| Select-all | Spanish Windows | UIA TextPattern.DocumentRange.Select() is locale-independent | P3 | Low | No Ctrl+A dependency | test exists but COLLECTION_ERROR | Physical test |

---

## 8. Async/Concurrency Risk Analysis

### Shared mutable state:
| Variable | Access pattern | Lock | Risk |
|---|---|---|---|
| `self.session` | Set in session loop, read in tool execution and speak() | No lock | P1: race if GoAway nullifies session while tool sends result |
| `self.audio_in_queue` | Created/destroyed per session, written from receive_audio, read from play_audio | No lock (asyncio Queue) | P2: `put_nowait` after queue set to None in finally |
| `self._is_speaking` | Set from play_audio, read from barge-in callback (different thread) | `_speaking_lock` | OK |
| `self._session_resumption_handle` | Written from receive_audio, read from session_loop | `_conversation_lock` partial | P2: some reads outside lock |
| `self._barge_in_gate` | Written from input callback thread, read from gate process | Internal RLock | OK |
| `_WINDOWS_TARGET_CACHE` | Written from safe_text_entry, read from multiple calls | `_WINDOWS_TARGET_LOCK` | OK |
| `self._audio_device_manager` | UI thread calls list/select, audio thread calls resolve | Internal RLock | OK |
| `self._local_session_memory` | Written from tool thread, read from search | No lock | P2: dict not thread-safe under concurrent mutation |

### Race conditions identified:

**RACE-001 (P1): Session nullification during tool execution**
After `_execute_forced_local_file_request` awaits `_execute_tool`, `self.session` is checked (line 3113). But the session loop's `finally` block (line 6331) sets `self.session = None`. If GoAway fires between tool completion and `send_client_content`, the send will fail.

**RACE-002 (P2): Queue write after destruction**
In `_receive_audio`, `self.audio_in_queue.put_nowait(response_audio)` at line 5543 can race with `self.audio_in_queue = None` in the session loop finally (line 6333). The asyncio Queue doesn't protect against this.

**RACE-003 (P2): Input callback after stream close**
The sounddevice input callback may fire after `sd.InputStream` is closed but before the callback reference is garbage-collected. The callback writes to `self.out_queue` which may already be None.

### Orphan task risks:
- `asyncio.TaskGroup` (line 6222) properly cancels all tasks when any one raises. This is correct.
- `threading.Timer` for self-quit (line 3173) has a `cancel()` in cleanup. OK.
- Background tool threads via `asyncio.to_thread` run to completion even after session closes — results are discarded. Acceptable but should log.

---

## 9. Future Implementation Risks

| Future Feature | What It Could Break | Files at Risk | Isolation Strategy | Required Test Contract |
|---|---|---|---|---|
| **Codex/Claude integration** | Tool routing, prompt size, concurrent tool execution | main.py (_execute_tool), prompt.txt | Separate tool namespace; agent_task pattern | Tool dispatch contract, prompt token budget |
| **External coding agents** | Background task lifecycle, resource leaks, stale session | agent/executor.py, main.py | TaskGroup with timeout; dedicated subprocess | Task completion + cleanup test |
| **Project context system** | File processor routing confusion; memory domain pollution | file_processor.py, memory_manager.py | Separate routing predicate; isolated namespace | File routing negative tests; memory domain isolation |
| **Vision / Ollama chain** | Prompt size; blocking tool execution; GPU resource contention | screen_processor.py, main.py | Async with timeout; separate process | Response-time SLA test |
| **Browser automation** | Focus theft from computer_control; stale HWND | browser_control.py, safe_text_entry.py | Focus state snapshot/restore | Focus preservation test |
| **Expanded HA control** | Duplicate actions; stale state confirmation | lilith_gateway.py | Idempotency token per action | Duplicate-call guard test |
| **Windows ↔ Ubuntu shared core** | Path resolution (/ vs \); platform-specific imports | ALL actions, core/ | Platform guard at import; pathlib throughout | Cross-platform path resolution test |
| **LILITH Core architecture** | Memory domain confusion; network latency masks failures | lilith_gateway.py, memory_manager.py | Explicit domain prefix; timeout + circuit breaker | Memory isolation + timeout test |

---

## 10. Protected Contracts (Invariants)

### AUDIO CONTRACT
1. Maximum one input stream open at any time.
2. Maximum one output stream open at any time.
3. Selected device preference persists in `~/.jarvis/config/audio_devices.json`.
4. UI combo boxes show only WASAPI endpoints — never MME/DirectSound transport duplicates.
5. Internal transport index resolution is invisible to user.
6. Device switch must close old stream before opening new one.

### TOOL CONTRACT
1. Exactly one execution per accepted tool call (dedup guard in `_mutating_tool_guard_reason`).
2. Success/failure reported exclusively from actual tool result — model cannot invent.
3. Tool result must be sent back to the SAME session that requested it.
4. `_execute_tool_batch` preserves serial order for mutating tools.

### FILE CONTRACT
1. Local file existence determined locally by `_resolve_file_path` — Gemini is never authority.
2. `_local_file_request_from_text` detects spoken filenames before model tool choice.
3. `_local_file_recovery_from_denial` catches model false denials from output transcription.
4. No duplicate `file_processor` execution per turn (`forced_local_file_executed` flag).
5. API key injected via ContextVar, never logged.

### VOICE CONTRACT
1. F8 lifecycle: `_conversation_requested` is the single source of truth.
2. F4 mute does not destroy conversation state — only suppresses mic forwarding.
3. Barge-in gate resets on `start_playback()` and `stop_playback()`.
4. Reconnect must drain playback before raising `RecoverableLiveDisconnect`.
5. Session resumption handle expires after `_SESSION_RESUMPTION_HANDLE_MAX_AGE`.

### SECURITY CONTRACT
1. No API key/token/password in log output (ContextVar isolation for file_processor).
2. No `eval()` or `exec()` — calculator uses AST whitelist.
3. No path escalation — `_SAFE_SCREENSHOT_ROOTS` restricts screenshot paths.
4. No typing into blocked processes (terminals, IDEs) — `WINDOWS_BLOCKED_PROCESSES`.
5. Clipboard operations go through validated UIA targets only.

### MEMORY CONTRACT
1. Three distinct domains: current conversation, local session memory, LILITH persistent.
2. Explicit save required — no automatic persistence of conversational facts.
3. `_SAVE_MEMORY_BLOCKED_CATEGORIES` prevents personal data in local store.
4. Memory routing is determined by text classification, not by model tool choice alone.

---

## 11. Test Suite Quality Findings

### CRITICAL: 40/552 tests fail to collect
**Root cause:** `import main` → `from google import genai` → `ModuleNotFoundError`.
**Classification:** ENVIRONMENTAL — the runtime environment has `google-genai` installed; the test runner's Python 3.14.5 does not.

### Known obsolete/mismatched tests:
| Test | Issue | Classification |
|---|---|---|
| test_clipboard_commands.py | Updated in working tree (select-all no longer Ctrl+A) | EXPECTED (aligns with new UIA behavior) |
| test_phy2_010_windows_safe_text_entry.py | Updated in working tree | EXPECTED |
| test_ui_current_contract.py | Updated in working tree (+47 lines) | EXPECTED |
| QA tool parity (EXPECTED_TOOLS) | `calculator` missing | PREEXISTING_METADATA_GAP |

### Tests with high mock ratio (risk of false confidence):
- Most tests in `core/green/tests/` are purely unit-level with mocked tool registry.
- `test_gemini_live_session.py` mocks the entire Gemini client — cannot catch real protocol issues.
- `test_phy2_004_audio_interruption.py` cannot reproduce real echo/barge-in behavior.

### Missing integration tests:
1. Audio device switch → stream closure → new stream open (end-to-end)
2. GoAway during tool execution → session recovery → result delivery
3. Local file routing → audio gate → forced execution → response delivery
4. F8 stop → tool still running → cleanup
5. Device persistence → reboot → resolution with new PortAudio indices

---

## 12. Ordered Physical Test Plan

### P0 — Core Stability

**PHY-001: Test environment fix**
- Action: `py -m pip install google-genai sounddevice pyaudio`
- Verify: `py -m pytest --collect-only -q` shows 0 errors
- PASS: 512+ tests collected
- FAIL: Still has collection errors → check pip target matches test runner

**PHY-002: Full test suite green**
- Action: `py -m pytest -x -q`
- PASS: All collected tests pass
- FAIL: Identify which tests fail and classify as REAL_REGRESSION vs ENVIRONMENTAL

### P1 — Voice/Audio

**PHY-003: Basic conversation start/stop (F8)**
- Action: Press F8 → wait for "AURORA en línea" → speak "Hola" → wait for response → Press F8
- Log evidence: `LIVE_SESSION connect`, `Turn complete`, `LIVE_SESSION disconnect`
- PASS: Clean start, response, clean stop, no orphan tasks
- FAIL: Examine task group exceptions

**PHY-004: Audio device selection — output**
- Action: While conversation active → change output device in UI combo → speak "Di algo"
- Log evidence: `AUDIO_OUTPUT selected`, new stream opens
- PASS: Audio plays on new device
- FAIL: Audio continues on old device or silence

**PHY-005: Audio device selection — input**
- Action: While conversation active → change input device in UI combo → speak "¿Me escuchas?"
- Log evidence: `AUDIO_INPUT selected`, `AudioInputDeviceSwitch`
- PASS: AURORA responds to new microphone
- FAIL: AURORA doesn't hear user on new device

**PHY-006: Barge-in during long response**
- Action: Ask "Cuéntame la historia de España" → interrupt with "Para"
- Log evidence: `barge_in accepted`, `provider_interruption`
- PASS: AURORA stops speaking within ~300ms
- FAIL: AURORA continues speaking or restarts from beginning

**PHY-007: GoAway recovery**
- Action: Have a long conversation (10+ minutes) until GoAway occurs naturally
- Log evidence: `go_away received`, `provider GoAway`, `Reconnecting`
- PASS: Conversation resumes with context preserved
- FAIL: Context lost or duplicate output

### P2 — Local Tools/Files

**PHY-008: Local file explain (the critical test)**
- Action: Say "Explícame el archivo prompt punto txt de JARVIS"
- Log evidence: `LOCAL_FILE_ROUTE decision=forced file=prompt.txt action=explain`
- PASS: AURORA reads and explains prompt.txt content in Spanish
- FAIL: "No puedo acceder" or silence or wrong file

**PHY-009: Audio gate timing**
- Action: Say "Explícame el archivo prompt punto txt" and observe timing
- Log evidence: `gate_discard` (audio discarded before file route) or `gate_open` after 0.40s
- PASS: No premature audio plays before file processing starts
- FAIL: AURORA starts speaking "I can't access" before file result arrives

**PHY-010: Calculator via voice**
- Action: Say "Cuánto es 15 por ciento de 200"
- Log evidence: `TOOL_CALL calculator`
- PASS: AURORA says "Resultado: 30"
- FAIL: Wrong result or "no pude calcular"

### P3 — Windows Actions

**PHY-011: Safe text entry**
- Action: Open Notepad → click in editor → say "Escribe hola mundo"
- Log evidence: `SAFE_TEXT target_validated process=notepad.exe`
- PASS: "hola mundo" appears in Notepad
- FAIL: Refused or typed in wrong window

**PHY-012: Select all (UIA)**
- Action: In Notepad with text → say "Selecciona todo el texto"
- Log evidence: `windows_uia_select_all`
- PASS: All text selected via UIA (not Ctrl+A)
- FAIL: Nothing selected or partial selection

**PHY-013: Copy/paste**
- Action: Select text → say "Copia" → open new Notepad → say "Pega"
- PASS: Text appears in new Notepad
- FAIL: Clipboard empty or wrong content

---

## 13. Future Change Gate

### PRE-CODE
- [ ] Identify which contracts (Section 10) the change affects.
- [ ] Verify no overlap with another in-progress change.

### POST-CODE
- [ ] Focused unit tests for changed behavior.
- [ ] All 512+ tests pass (`py -m pytest -q`).

### PRE-MERGE
- [ ] `git diff` review for: secret exposure, eval/exec, unguarded Exception handlers.
- [ ] QA metadata parity: `EXPECTED_TOOLS` matches `TOOL_DECLARATIONS`.
- [ ] Tool dispatch: every declared tool has a matching `name == "tool_name"` branch.
- [ ] No new broad `except Exception` without logging.

### PRE-COMMIT
- [ ] `git diff --cached` reviewed.
- [ ] No API keys, tokens, or passwords in staged files.
- [ ] pyproject.toml version bumped if public-facing.

### PHYSICAL REQUIRED WHEN
- Audio device changes (input, output, selection, recovery)
- UI focus interactions (computer_control, safe_text_entry)
- Hardware device control (microphone, speakers, Bluetooth)
- Windows desktop interactions (window close, app launch)
- Network hardware (LILITH, Home Assistant)
- Gemini Live protocol changes (GoAway, reconnect, resumption)

---

## 14. Blocking Issues

| ID | Severity | Issue | Action Required |
|---|---|---|---|
| P0-001 | ~~P0~~ P2 | Interpreter mismatch — `.venv` collects 1427/0 errors | Use `.venv` interpreter |
| P0-002 | ~~P0~~ P2 | Calculator missing from QA metadata | **FIXED** — added to all 5 maps |

---

## 15. Non-Blocking Issues

| ID | Severity | Issue | Recommendation |
|---|---|---|---|
| P1-001 | P1 | Session nullification race during forced file request | Add None guard after await in `_execute_forced_local_file_request` |
| P1-002 | P1 | Audio device hot-plug not physically tested | Physical test PHY-004/005 |
| P1-003 | P1 | Barge-in with device switch (stale fingerprints) | Physical test: switch during playback |
| P1-004 | P1 | GoAway during tool execution (result to dead session) | Physical test PHY-007 + log analysis |
| P1-005 | P1 | Microphone recovery vs manual selection race | Physical test |
| P1-006 | P1 | Local file routing untested physically | Physical test PHY-008/009 |
| P1-007 | P1 | Audio gate timing untested physically | Physical test PHY-009 |
| P1-008 | P1 | Output device recovery untested physically | Physical test |
| P2-001 | P2 | Queue write after destruction (RACE-002) | Guard with `if queue is not None` |
| P2-002 | P2 | Some session_resumption_handle reads outside lock | Add lock or make atomic |
| P2-003 | P2 | `_local_session_memory` dict not thread-safe | Add RLock or use concurrent dict |
| P2-004 | P2 | F8 stop while tool running — result discarded silently | Log discarded result |
| P2-005 | P2 | Durable conversation restoration not physically tested | Physical test after GoAway |
| P2-006 | P2 | F4 mute interaction with device switch not tested | Physical test |
| P2-007 | P2 | File processor with very long files (>100KB) not tested | Add file-size boundary test |
| P2-008 | P2 | API key injection via ContextVar per-task, but file_processor creates its own Client per call | Verify no key leakage in concurrent calls |
| P2-009 | P2 | Input callback thread after stream close (RACE-003) | Guard with shutdown flag check |
| P2-010 | P2 | Memory routing + local file routing ambiguity for "guarda el archivo X" | Add negative test |
| P2-011 | P2 | Audio gate may hold audio 0.40s on normal (non-file) responses | Monitor latency in physical tests |
| P2-012 | P2 | Device index changes between boots (persistence tests) | Physical test across reboot |
| P2-013 | P2 | LILITH network loss/timeout not physically tested | Physical test: disconnect network |
| P2-014 | P2 | Duplicate tool execution despite dedup guard (edge: different fc.id, same effect) | Review guard scope |
| P3-001 | P3 | Voice style pacing subjective quality | Physical test (listen) |
| P3-002 | P3 | Aurora particle performance not benchmarked | Run benchmark_aurora_particles.py |
| P3-003 | P3 | Graphics quality switch not physically verified | Switch between low/med/high |
| P3-004 | P3 | UI hard-coded colors (100+ hex literals) | Theme audit |
| P3-005 | P3 | CRLF warnings in git diff | Normalize line endings |
| P3-006 | P3 | prompt.txt changes not version-tracked in audit | Document prompt delta |
| P3-007 | P3 | Unused macOS-specific code in safe_text_entry.py (osascript, AppKit) | No action (cross-platform file) |
| P3-008 | P3 | `_report_audio_level` imports aurora_particles at runtime | Verify import performance |

---

## 16. Recommended Next Actions

### Immediate (before physical tests):
1. **Fix test environment:** `py -m pip install google-genai sounddevice`
2. **Add calculator to EXPECTED_TOOLS:** Single-line fix in `core/qa_audit.py`
3. **Run full test suite** to establish baseline pass count.

### First physical test:
**PHY-008: "Explícame el archivo prompt punto txt de JARVIS"**
This is the highest-value test because it exercises the entire new local-file routing pipeline end-to-end: voice transcription → `_local_file_request_from_text` → audio gate → forced execution → `file_processor` → API key injection → Gemini response → Spanish audio output.

### After physical tests:
4. Add session-None guard in `_execute_forced_local_file_request` (RACE-001).
5. Add queue-None guard in `_receive_audio` (RACE-002).
6. Physical test audio device switching under load.
7. Physical test GoAway recovery mid-conversation.

---

## Terminal Summary

```
AURORA PREVENTIVE REGRESSION AUDIT — 2026-10-25
================================================
Total findings:  32
  P0 (critical):   2  — test env broken, calculator metadata gap
  P1 (major):      8  — races, untested audio/file paths
  P2 (degraded):  14  — concurrency guards, missing physical tests
  P3 (cosmetic):   8  — UI polish, cross-platform dead code

BLOCKING before physical tests:
  1. Install google-genai in test Python env
  2. Add "calculator" to EXPECTED_TOOLS in qa_audit.py

Highest-risk future features:
  1. External coding agents (task lifecycle, resource leaks)
  2. Windows ↔ Ubuntu shared core (path resolution, platform imports)
  3. LILITH Core shared architecture (memory domain confusion)

NEXT PHYSICAL TEST:
  PHY-008: Say "Explícame el archivo prompt punto txt de JARVIS"
  Expected: AURORA reads and explains prompt.txt in Spanish
  Log evidence: LOCAL_FILE_ROUTE decision=forced
```
