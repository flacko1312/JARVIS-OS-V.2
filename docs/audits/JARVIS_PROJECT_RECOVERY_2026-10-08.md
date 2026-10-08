# JARVIS Project Recovery, Audit, Reconciliation and Stabilization

Date: 2026-10-08

Scope: real Windows `C:\JARVIS`, Linux clone, integration documentation, remote Git state, runtime, tests, security, dependencies, and active docs.

Status: machine recovery complete; JL-A10 owner-operated spoken Gemini Live / persistent routine lifecycle certification passed after fix.

## 1. Executive Summary

The real running JARVIS is the PyQt/Gemini Live application installed from `C:\JARVIS`; the observed process tree used `C:\JARVIS\.venv\Scripts\jarvis.exe` and the same checkout's Python entry point. The Linux `/home/flako1312/JARVIS-OS-V2` directory is a clean clone of the same remote, not proof of Windows behavior. At audit start Windows contained one unpushed code commit (`59c6413`) while `origin/main` contained two documentation commits. They had a common merge base and no file conflict, so both histories were preserved by a normal merge.

The initial root pytest command failed during collection because an ignored `tmp/jl_a10_lilith` snapshot was discovered. The canonical `tests/` run collected 496 and produced 421 passes and 75 failures: 71 were a first-run/tour UI specification whose symbols never existed in `ui.py`; four were stale contract/environment tests. Recovery constrained discovery, retained the historical specification with an explicit reason, moved six valid UI tests into a current contract, repaired QA probes, and fixed real security/consistency defects. Final recovery pytest collected 502: 425 pass, 77 classified skips, zero failures/errors, 10 subtests pass, and one third-party warning. JL-A10 owner retest on HEAD `bbe95a8d3abcdbbab130e46a3ac336bd47f5c374` reported 429 passed, 77 skipped, 0 failed, 0 errors, 1 warning, and 15 subtests passed.

No LILITH source was modified. AUT-8 and AUT-9 were not started. JL-A10 is PASS / CLOSED after owner-operated Windows retest.

## 2. Repository / Runtime Identity

| Copy | Identity at baseline | Role / evidence |
|---|---|---|
| `C:\JARVIS` | Git `main`, HEAD `59c6413`, origin `git@github.com:flacko1312/JARVIS-OS-V.2.git`; one local commit ahead and two remote commits behind | Real Windows runtime and verified development checkout. `jarvis.exe` process started 2026-10-07 19:03:27 from this venv. |
| `/home/flako1312/JARVIS-OS-V2` | `main`/`origin/main` at `89d7a80`, clean | Linux audit/reference clone of the same repository. |
| `/home/flako1312/INTEGRACION` | `main`/origin at `5ce1944`, clean | Cross-project integration state/task documentation. |
| `/home/flako1312/jarvis` | separate remote `flacko1312/jarvis.git`, HEAD `db5c25f`, clean | Historical integration library source/reference imported into the main repository. |
| `origin/main` | GitHub `flacko1312/JARVIS-OS-V.2` | Repository authority after validated push. |
| `upstream` | `MAL19INDUSTRIES/JARVIS-OS-V.2`, push disabled | Reference only. |

Baseline ignored Windows state included `.env`, `.venv`, logs, private config, local memory/state and `tmp/`; values were not read or disclosed. There were no baseline tracked modifications beyond the committed divergence.

## 3. Reconstructed Development History

- June 2026: repository preparation, local-memory removal from Git, UI control and public setup.
- August 2026: initial private release, cross-platform setup, PortAudio/microphone resilience, desktop UI and action expansion.
- September/October: imported LILITH client/router/runtime; added health, memory, HOME, approvals, docs/source/Git, command gateway and routine tools.
- `897afbc`–`4da6f7d`: FunctionCall-scoped idempotency and natural-language routine integration.
- `1df901f`–`523ae92`: recurring routing, scheduled-effect turn provenance and pending routine conversation state.
- `39d286b`–`59c6413`: persistent memory authority, rerouting, fragmented local-control recognition, and truly session-only local memory.
- `fb4364d`/`89d7a80`: canonical combined voice architecture and Windows validation procedure.
- Recovery merge `45892ae`: preserved local memory code and remote docs before stabilization edits.

The UI tour test file originated in the initial release, but Git search shows `FirstRunIntroOverlay` and its related symbols never existed in `ui.py`. It was an unimplemented specification, not a regression from deployed code.

## 4. Current Architecture

The canonical flow is USER → JARVIS interface → Gemini Live → JARVIS deterministic guards → JARVIS-local action or LILITH authoritative API → verified result → Gemini audio → USER. `docs/ARCHITECTURE.md` is the maintained authority.

JARVIS owns interface, microphone/audio, Live session, Spanish prompt, tool registry, Windows actions, presentation/local tasks, and natural-language translation. LILITH owns persistent personal memory/context, persistent routines, Home Assistant, approvals and authoritative persistent cognitive state. Gemini is a language/reasoning/tool-selection component, not system authority.

## 5. Gemini Live Architecture

- SDK: `google.genai`; async `client.aio.live.connect`, API version `v1beta`.
- Model precedence: `GEMINI_LIVE_MODEL` → ignored local config `live_model` → native-audio default; available Live models are enumerated and a compatible model selected.
- System instruction: Spanish language rule first and last, current time, routine rules, memory authority rules, optional LILITH context, filtered local compatibility memory, then `core/prompt.txt`.
- Session: queues and a TaskGroup run realtime send, microphone input, response receive, playback and startup announcement. Reconnect occurs around the complete Live context; shutdown exits.
- FunctionCalls are converted to responses with the original ID and sent through `send_tool_response`.
- Duplicate IDs, cross-turn/stale scheduled effects, incomplete routine state and ambiguous memory authority fail closed.
- Credential: desktop Live code requires `GEMINI_API_KEY`; it never logs the value. Hosted mode injects an encrypted per-user key.
- Spanish is deterministic prompt policy; actual spoken-language behavior remains a human gate.

Gemini-required functions are conversation, transcription, synthesis, language reasoning and tool selection. Tool implementation/guards are conventional JARVIS code. Persistent state/HA/routines are LILITH functions.

## 6. Voice / Audio Architecture

Microphone → `sounddevice.RawInputStream` → mono PCM16 16 kHz / 1024 frames → Live realtime input → Gemini input transcription/reasoning → audio PCM → 24 kHz mono playback or hosted WebSocket frames. JARVIS suppresses mic forwarding while it marks itself speaking. Device enumeration/fallback and unsupported-voice fallback exist; reconnect wraps the Live session. There is no active local production STT. Optional external TTS and old LILITH-native voice experiments are not canonical.

Machine tests validate configuration, extraction, streams and control flow. Physical device selection, echo, barge-in, device loss, Spanish STT/TTS quality and full duplex behavior are expected hardware gates.

## 7. GUI Architecture

- Real Windows UI: PyQt6 `ui.MainWindow`, launched through `main:cli_main`.
- Hosted UI: separate Next.js interface consuming authenticated HTTP/WebSocket API.
- State surfaces: LISTENING/THINKING/SPEAKING/MUTED, logs, progress, settings, detachable panels, shutdown path.
- Current UI executable contract is tested offscreen. The first-run/tour design specification is historical and explicitly excluded.
- Remaining risks: very large `ui.py`, broad exceptions, hard-coded colors, incomplete accessibility/scaling/soak evidence. No visual redesign was performed.

## 8. Tool / Function Architecture

Caller for all rows is Gemini through `JarvisLive`; implementation dispatch is `_execute_tool()` unless noted. `RO` means read-only, `M` mutating, `Mixed` operation-dependent. Every potentially mutating/mixed tool is serialized in a FunctionCall batch after recovery.

| Tool | Class / mode | Schema parameters (required marked *) | Target / implementation | Authorization, verification and failure semantics |
|---|---|---|---|---|
| `open_app` | JARVIS Windows M | `app_name*` | `actions.open_app` / OS launcher | User intent through Gemini; resolved executable, no general shell; returns failure instead of assumed launch. |
| `web_search` | OTHER RO/mixed | `query*`, mode, aspect, items | search action | Prompt requires permission for live search; tool result is returned, failures surfaced. |
| `weather_report` | OTHER RO | `city*` | weather action | Network result only; errors returned. |
| `check_messages` | OTHER RO | platform, max_messages, include_contacts, contact_query | message monitor | Read-only; untrusted contents must not become instructions. |
| `prepare_message_reply` | OTHER M | `action*`, platform, receiver, message_text | reply draft lifecycle | Prepare/explicit approve/cancel; exact pending draft verified before send. |
| `send_message` | OTHER M | `platform*`, action, receiver, message_text | platform senders | Platform-specific safeguards; Instagram approval lifecycle; failures stop retries. |
| `email_control` | OTHER Mixed | `action*`, provider/browser/query/id/to/cc/bcc/subject/body/credentials | Gmail/Apple Mail | Authenticated account; outgoing prepare then later approve; visible draft verification; errors are not success. |
| `reminder` | JARVIS LOCAL M | `date*`, `time*`, `message*` | OS one-shot reminder | Schedule guard allows only one-shot future intent; creation failure reported; never used for recurring routines. |
| `youtube_video` | OTHER Mixed | action, query, region, save, url | browser/API/file | URL/query validation; open/save failures returned. |
| `media_control` | JARVIS LOCAL M | `action*`, platform, query | desktop media | QA opt-in in tests; OS result returned. |
| `screen_process` | JARVIS LOCAL RO/privacy | `text*`, angle | capture + Gemini vision | One capture; permission/capture/analysis errors spoken, no invented vision. |
| `computer_settings` | JARVIS WINDOWS M | action, description, value | OS-specific settings | Power target must be explicit; allowed actions; subprocess result/error used. |
| `browser_control` | JARVIS LOCAL Mixed | `action*`, URL/query/selectors/text/keys/path | controlled Playwright browser | Controlled profile, action-specific validation; QA opt-in; errors returned. |
| `file_controller` | JARVIS LOCAL Mixed | `action*`, path/name/destination/content/etc. | scoped filesystem | Safe-root checks, protected paths and recoverable trash; operation result verified. |
| `desktop_control` | JARVIS WINDOWS M | `action*`, mode/path/task/url | desktop automation | Local only; QA restriction; subprocess/automation errors returned. |
| `code_helper` | JARVIS LOCAL M | `action*`, code/file/output/language/args/timeout | local generation/execution | Excluded from hosted/cloud allowlist; QA blocks unsupervised writes; actual subprocess output determines success. |
| `dev_agent` | JARVIS LOCAL M | `description*`, language/project_name/timeout | local project generation | QA blocked by default; writes stamped files and reports install/run output. |
| `agent_task` | JARVIS LOCAL M | `goal*`, priority | background task queue | Task ID/status is authoritative; no immediate completion claim. |
| `computer_control` | JARVIS WINDOWS M | `action*`, coordinates/keys/text/window/etc. | pyautogui/OS | Safe text-entry/window rules; QA blocks unsafe actions; result returned. |
| `game_updater` | JARVIS LOCAL Mixed | action/game/platform/schedule/shutdown | launcher/scheduler | Status reads versus explicit update/schedule; shutdown is high impact and QA-blocked. |
| `flight_finder` | OTHER RO/mixed | `origin*`, `destination*`, `date*`, return/cabin/passengers/save | network + optional file | Network evidence; optional save only after tool result. |
| `graphics_quality` | JARVIS UI M | `quality*` | UI settings | Enum validation; persisted/applied value returned. |
| `jarvis_ui_control` | JARVIS UI M | `action*`, theme, graphics_quality | UI command handler | Action/theme allowlists. Self-quit is deliberately not a Gemini tool action and uses verified local transcript path. |
| `deep_research` | OTHER M/background | question/mode/depth/sources/output/result action | dedicated background workflow | Ask/confirm execution-mode lifecycle; task/result state is authoritative. |
| `create_presentation` | JARVIS LOCAL M/background | topic/title/files/URLs/template/style/export/etc. | presentation maker | Task ID and output existence determine result; web use requires permission. |
| `task_status` | OTHER Mixed | action, task_id | task queue | Status/cancel by real task ID. |
| `file_processor` | JARVIS LOCAL Mixed | action/file/destination/instruction/format/etc. | document/media processors | Safe paths/type-specific validation; subprocess/file output checked. |
| `save_memory` | JARVIS SESSION M | `value*`, key, category | in-process session dict | Only explicit local/session authority; persistent requests rerouted; ambiguous writes blocked; never writes legacy JSON. |
| `local_memory_search` | JARVIS SESSION RO | key/category/query | in-process session dict | Same-instance only; empty result after restart is expected. |
| `lilith_memory_search` | LILITH MEMORY RO | `query*`, limit | `/memory/search` | LILITH response is authoritative; offline/error returned. |
| `lilith_memory_store` | LILITH MEMORY M | `value*`, key/category/description/confidence | `/memory/store` | Persistent-authority guard, canonical key, duplicate ID suppression; success only on confirmed created/updated response. |
| `lilith_memory_delete` | LILITH MEMORY M | key, reason | `/memory/{key}` delete contract | Explicit delete intent and canonical stored-key alias; confirmed response required. |
| `lilith_home_action` | LILITH HOME M | `target*`, `action*`, parameters | resolve/entity/action APIs | Current-turn schedule guard; on/off allowlist; LILITH resolves authority and action; state readback attempted; no false success. |
| `lilith_request_approval` | LILITH HOME M | `entity_id*`, `action*` | approval API | Only after approval-required result; token returned, no execution claim. |
| `lilith_resolve_approval` | LILITH HOME M | `token*`, `resolution*` | approval resolution API | Explicit user resolution; confirmed execution/result only. |
| `lilith_health` | LILITH RUNTIME RO | none | `/health` | Real response or unavailable. |
| `lilith_runtime_status` | LILITH RUNTIME RO | none | `/runtime/status` | Real response only. |
| `lilith_docs_list` | LILITH DOCS RO | prefix | docs API | Safe server allowlist; errors returned. |
| `lilith_docs_read` | LILITH DOCS RO | `path*`, max_bytes | docs API | Server path validation/size bound. |
| `lilith_docs_search` | LILITH DOCS RO | `query*`, limit | docs API | Bounded results. |
| `lilith_source_list` | LILITH SOURCE RO | prefix | source API | Server allowlist. |
| `lilith_source_read` | LILITH SOURCE RO | `path*`, max_bytes | source API | Server path/size validation. |
| `lilith_source_search` | LILITH SOURCE RO | `query*`, limit | source API | Bounded results. |
| `lilith_git_status` | LILITH GIT RO | none | Git status API | Read-only response. |
| `lilith_command_submit` | LILITH COMMAND M | `intent*`, parameters/request/correlation/idempotency IDs | `/commands/submit` | Structured IDs and authoritative status; no completion claim unless response confirms it. |
| `lilith_routine` | LILITH ROUTINES Mixed | `operation*`, routine/name/schedule/timezone/action fields/limit | command gateway routine intent | Read operations allowed after validation; writes current-turn guarded; create requires complete recurring state; duplicate/stale calls blocked; correlation/result required. |

False-success review found explicit confirmation semantics for authority-critical LILITH mutations and task-based local workflows. Some generic local OS tools can only verify subprocess acceptance, not the final semantic desktop state; this is documented debt rather than represented as external authority.

## 9. Windows Action Architecture

Local actions are invoked only in desktop mode; hosted `cloud_safe` advertises a narrow allowlist and now excludes arbitrary `code_helper` execution. Capabilities include app launch, browser, keyboard/mouse, screen, clipboard, file operations, media, system settings, process/game launchers, reminders and background code/presentation work.

Path operations use safe roots/protected paths and recoverable deletion. Message/email flows use approval where supported. Power operations require explicit computer intent and are QA-blocked. `open_app` was hardened to launch resolved executables without general `shell=True`; the only URI special case is validated `ms-settings:`. One fixed-candidate VS Code compatibility launcher still uses `shell=True` and is P2 debt.

## 10. LILITH Integration

`LilithClient` uses `/api/v1/integration`, bearer auth, default 10-second timeout, two retries, exponential backoff capped at five seconds, and structured error mapping. Endpoints/contracts cover health, runtime status, docs/source list/read/search, Git status, command submit, memory search/context/store/delete, Home entity/action/resolve, and approval request/resolve. Routine operations are structured commands rather than a second JARVIS scheduler.

Typed messages can route through `LilithBridge`; voice actions use FunctionCalls. HOME offline is handled and reported so Gemini cannot invent success. Other offline typed domains may pass through with an explicit notice only when no physical effect was claimed.

## 11. Memory Authority

LILITH is the only authoritative persistent personal memory. Explicit persistence phrases route or reroute once to `lilith_memory_store`. Explicit negative-LILITH/local/session signals route to in-process `save_memory`. Control-only STT normalization repairs fragmented authority tokens without changing key/value content. Ambiguous authority writes nowhere. Canonical keys and aliases allow natural delete wording. Duplicate FunctionCall IDs cannot write twice.

Legacy `memory/long_term.json` helpers remain compatibility code. When LILITH context is injected, local personal categories are removed from the prompt. Local session state does not survive `JarvisLive` reconstruction. This eliminates a silent competing persistent write path but does not yet remove legacy read compatibility.

## 12. Routines

Recurring intent, including “todos los días” and “nueve de la noche,” builds pending state containing recurrence, 21:00, `Europe/Madrid`, action and target. A wrong Gemini selection (`reminder` or `lilith_home_action`) is rerouted exactly once to `lilith_routine`. Incomplete intent blocks and asks for missing data. List/get/history are read-only; update/enable/disable/delete use the same current-turn and duplicate protections. Confirmed LILITH correlation/result is required.

Automated exact-path tests cover recurring create, fragmented/pending turns, wrong-tool reroute, stale/cross-turn calls, duplicate IDs, read operations and management operations. Real persistent create/list/delete remains a human gate.

## 13. Home Assistant

JARVIS contains no independent authoritative HA client. It asks LILITH to resolve a spoken target, rejects unknown/ambiguous/not-allowed targets, calls LILITH Home action for allowed on/off operations, and queries state for verification when possible. Scheduled requests cannot bypass the routine/reminder guard. Safe real-device testing is owner-gated.

## 14. API / WebSocket State

Live routes: `GET /health`; auth signup/login/me/logout; Gemini-key set/delete; authenticated status/actions/chat; authenticated `/ws`. HTTP uses bearer tokens, rate limits, tenant scoping and encrypted per-user secret persistence. Production startup rejects default JWT secret, missing encryption key and non-Postgres database.

Recovery removed bearer tokens from WebSocket query strings. The browser now supplies `['jarvis', token]` subprotocols; the server validates the second protocol and accepts `jarvis`. Browser tokens use `sessionStorage`, not persistent `localStorage`. CORS is explicit. No `/api/health/live` route exists; active health is `/health`.

## 15. Configuration

Values were checked by name/existence only; secrets were not printed.

| Setting | Real precedence |
|---|---|
| Desktop Gemini key | injected constructor key in hosted mode; desktop `_get_api_key` requires `GEMINI_API_KEY`; older UI helpers may load ignored `config/api_keys.json` |
| Live model | `GEMINI_LIVE_MODEL` → `config/api_keys.json:live_model` → native-audio default → discovered compatible fallback |
| Voice | `GEMINI_VOICE_NAME` → `config/api_keys.json:voice_name` → `puck`; unsupported API response falls back to `puck` |
| Timezone | `JARVIS_TIMEZONE` → `Europe/Madrid` |
| LILITH | `LILITH_API_URL`, `LILITH_API_KEY`, optional timeout/retry env → integration disabled if incomplete |
| Hosted DB/Redis/JWT/encryption/CORS/model | environment → development defaults; production validation rejects unsafe critical defaults |
| Clap gate | platform defaults plus `JARVIS_ENABLE_CLAP_GATE`, `JARVIS_REQUIRE_CLAP_GATE`, `JARVIS_SKIP_CLAP_GATE` |
| QA | `JARVIS_QA_MODE`, isolated workspace and per-capability opt-ins |

Hard-coded LAN LILITH address appeared only through private environment/runtime logging, not tracked configuration. It was not copied into docs.

## 16. Dependencies

- Python project requires 3.11+; real venv ran Python 3.14 on Windows.
- PyQt6, sounddevice/PortAudio, FastAPI/SQLAlchemy, Playwright, Google GenAI, httpx, presentation/document libraries and Windows marker packages are declared.
- `pip check`: clean.
- Canonical Live/hosted chat uses `google.genai`; nine secondary modules still use deprecated `google.generativeai` (P2).
- Node 22.19.0/npm 10.9.3 were used. Lockfile exists. Next was advanced only to the audit-recommended fixed 16.4.0 release; production audit is clean.
- Development-only ESLint transitive graph retains five high advisories; a forced fix proposes an incompatible downgrade and was not applied.

## 17. Security

| Severity | Finding / disposition |
|---|---|
| P0 | None found. |
| P1 | Hosted arbitrary code execution exposure: `code_helper` was in `CLOUD_SAFE_ACTIONS`. Fixed by removing it and adding regression coverage. WebSocket bearer tokens in URLs were also eliminated. |
| P2 | One fixed-candidate VS Code `shell=True`; deprecated SDK modules; broad exception swallowing; powerful desktop tools depend on authenticated/local user intent and tool-specific validation; legacy JSON memory compatibility. Tracked in debt register. |
| P3 | Test/runtime log co-location, hard-coded UI colors and third-party Python warning. |

Tracked secret scan passed. Ignored `.env` and private config were not read. Production API validates JWT/encryption/database configuration. File paths and hosted tenants are scoped. Remote prompt/content is explicitly untrusted in active prompt rules, though model-based tool selection can never be treated as a sole security boundary; deterministic action guards are required for high-impact paths.

## 18. Test Infrastructure

- A. Pure Python: root pytest.
- B. JARVIS-LILITH: mocked HTTP/runtime plus optional real safe E2E.
- C. Gemini mocked: Live FunctionCall/guard tests.
- D. Gemini real network: model discovery/connect startup; classified external service.
- E. Windows-only: real venv and local action contracts.
- F. GUI: offscreen current UI contract and QA screenshots.
- G. Microphone/audio: mocked streams plus expected hardware gate.
- H. API/WebSocket: TestClient/tenant/auth/subprotocol coverage.
- I. Tools: 46 declaration/dispatch contract plus family tests.
- J. Human: spoken Live, routine lifecycle, HA, display scaling and soak.

`pyproject.toml` now limits discovery to `tests` and ignores `tmp`; no data was deleted. `scripts/qa.py automated` runs pytest without globally changing product behavior, and `qa_ui_probe.py` uses only current UI symbols. `self_test.py` uses UTF-8 subprocess capture and does not globally enable QA mode over functional contracts.

Skipped classification: 77 `STALE TEST`/historical unimplemented UI specification cases. They remain visible and explained, while six applicable checks execute in the current suite. No platform exclusion is disguised as a pass.

## 19. Baseline Tests

Before recovery changes:

- `python -m pytest -q`: collection aborted with one error from ignored `tmp/jl_a10_lilith/core/tests/test_jarvis_home_resolve.py` (`ModuleNotFoundError: routers`).
- `python -m pytest tests --collect-only -q`: 496 collected, one warning.
- `python -m pytest tests -q`: 421 passed, 75 failed, 0 skipped, 0 errors after collection, 3 warnings, 10 subtests passed.
- Failure root causes: 71 stale UI specification, stale tool inventory, prompt/farewell constant mismatch, platform-specific app alias expectation, and clap-gate environment leakage.
- Frontend lint could not initially run in a clean dependency state; dependency install exposed one critical and production high vulnerabilities before Next/security lock update.

## 20. Final Tests

Final evidence is recorded after all code/document changes:

- Root pytest: 502 collected; 425 passed; 77 skipped with explicit reason; 0 failed; 0 errors; 10 subtests passed; one external `google.genai`/Python 3.14 deprecation warning.
- Automated QA: 5/5 checks passed (compile, pip consistency, full pytest, offscreen UI evidence, tracked-secret scan); P0=0/P1=0; three P2 audit findings.
- Capability self-test: automated health 100%; seven PASS, one WARN (`AI / VOICE` contracts and 13 input/12 output devices detected, but the isolated self-test process did not receive a Gemini key), zero FAIL; four supervised groups remain.
- Web: ESLint pass; TypeScript pass; Next 16.4.0 production build pass; production dependency audit 0 vulnerabilities.
- `pip check`: no broken requirements.
- `git diff --check`: required before commits.

## 21. Contradiction Matrix

| Claim | Actual evidence | Status | Resolution |
|---|---|---|---|
| Linux clone is canonical development; Windows is deployment only | Real code-only commit and active `jarvis.exe` were in `C:\JARVIS`; Linux matched remote docs only | CONTRADICTORY | Repository remote is authority; Windows is verified runtime/development checkout, Linux audit clone |
| 74 pre-existing failures are normal | Root suite had 75 failures plus a collection error | STALE | Classified causes, deterministic discovery, historical skips/current tests, zero failures |
| Mandatory first-run cinematic/tour exists | Symbols never existed in `ui.py` history | CONTRADICTORY | Design/product/docs corrected; test spec retained historical |
| Persistent user memory can use local JSON | Current guard and commit `59c6413` make explicit local state in-process only | STALE/UNSAFE | LILITH documented as sole persistent authority |
| Gemini-selected storage/tool is authoritative | Guard reroutes or blocks based on current user turn | FALSE | Deterministic authority documented/tested |
| Recurring phrase can become Home action/reminder | Schedule guard reroutes exactly once to LILITH routine | FALSE | Current tests/log schema are canonical |
| Gemini/LILITH may be blamed for guard block | Guard responses identify JARVIS validation/routing failure | RESOLVED | Active code and docs agree |
| JARVIS is a second HA authority | All HA resolution/action goes through LILITH client | FALSE | Architecture clarified |
| `config/api_keys.json` always supplies desktop Live key | `_get_api_key` requires env; UI helpers have legacy file path | PARTIAL/CONTRADICTORY | Real precedence documented; legacy config tracked as debt |
| Hosted WebSocket uses safe auth | Token was in query URL | SECURITY CONTRADICTION | Subprotocol auth and session storage implemented |
| Hosted cloud-safe tools cannot execute host code | `code_helper` was advertised | SECURITY CONTRADICTION | Removed from hosted allowlist with test |
| Active health route is `/api/health/live` | FastAPI exposes `/health` | STALE ASSUMPTION | Audit/API docs state actual path |
| Bare root pytest is supported | It collected ignored `tmp/` | BROKEN | `testpaths`/`norecursedirs` configured |
| QA runner proves product baseline | It changed memory behavior and probed nonexistent UI | BROKEN | Runner uses pytest with normal behavior and current UI symbols |

## 22. Technical Debt

The complete register is `docs/TECHNICAL_DEBT.md`. No P0 remains. One P1 is the external spoken/hardware certification gate for unconditional GO. P2 covers deprecated SDK modules, broad exceptions, legacy memory compatibility, frontend development advisories/version ranges, monolith size, UI accessibility/theme consistency, and the fixed-candidate VS Code shell launcher. P3 covers historical skips, test log separation and third-party warning.

## 23. Git State

Baseline divergence was reconciled by normal merge; no reset, clean, stash, broad checkout or data deletion was used. Changes were staged explicitly by path and committed logically. Final handoff verification uses `git rev-parse HEAD`, `git rev-parse origin/main`, and `git rev-list --left-right --count origin/main...HEAD`; they match with `0 0`, and the tracked worktree is clean. Ignored private/runtime files remain intentionally ignored and are not “dirty” Git state.

The Linux clone was clean and five commits behind after the Windows push, then fast-forwarded to the same `origin/main`; it is now clean and `0 0`. INTEGRACION remained clean and `0 0` at `5ce1944`; the historical `/home/flako1312/jarvis` repository remained clean and `0 0` at `db5c25f`. LILITH remained untouched.

The real runtime was restarted after the recovery commits. The new process tree started at 2026-10-08 10:39 Europe/Madrid from `C:\JARVIS\.venv\Scripts\jarvis.exe`; the base interpreter child reported the same start second. `import main` resolved to `C:\JARVIS\main.py`. Sanitized startup evidence showed Gemini Live model enumeration, `JARVIS_START`, LILITH health 200, memory-context retrieval, and LILITH monitor/runtime online. `tmp/jarvis_status.json` reported `state=online`. This proves source/runtime identity and connection startup, not spoken microphone quality.

## 24. JL-A10 Physical Test Status

Status: **PASS / CLOSED**.

Final owner-operated Windows evidence on Git HEAD `bbe95a8d3abcdbbab130e46a3ac336bd47f5c374`:

- Full Windows regression: 429 passed, 77 skipped, 0 failed, 0 errors, 1 warning, 15 subtests passed.
- Startup: interface ready, LILITH context loaded with 87 facts, connected, microphone stream open, receive loop running, playback running.
- Spoken create description: "Encender bombilla mueble todos los días a las 10 de la noche".
- JARVIS submitted `lilith_routine` create with `timezone=Europe/Madrid`, `schedule_type=daily`, `schedule.hour=22`, `schedule.minute=0`, `action_intent=home.action`, `target=bombilla mueble`, and `action=turn_on`.
- LILITH confirmed create with correlation ID.
- `lilith_routine` list.
- Delete of `routine_id=14`.
- Final `lilith_routine` list.

Conclusion: the previous semantic schedule defect, intended `22:00` from "10 de la noche" submitted as `13:00`, is fixed and physically retested. LILITH correctly executed the structured schedule JARVIS supplied; no LILITH source change was required.

## 25. Non-blocking Operational Validation

The core JL-A10 spoken Gemini Live / persistent routine lifecycle gate is closed. Optional robustness checks such as mute/unmute, deeper interruption/barge-in behavior, device loss/reconnect, display scaling sweeps, and long soak remain useful non-blocking operational validation. Do not claim them unless separately performed.

## 26. Documentation Hierarchy

`README.md` is the entry point. Canonical authorities are `docs/ARCHITECTURE.md`, `docs/PROJECT_STATE.md`, `docs/TASKS.md`, `docs/TESTING.md`, `docs/LILITH_INTEGRATION.md`, and `docs/TECHNICAL_DEBT.md`. Git is detailed history; `docs/CHANGELOG.md` is a summary. This audit is a dated evidence snapshot. `docs/PROJECT_DOCUMENT_INDEX.md` is navigation only. `docs/MEMORY.md` and external older roadmap/state documents are historical/reference, not active authority.

## 27. Recovery Definition of Done

All machine-verifiable items are satisfied: identity, architecture, tool inventory, memory authority, routine/HA routing, API/config/dependency/security classification, baseline/final tests, docs hierarchy, debt, and Git reconciliation. JL-A10 owner-operated spoken Gemini Live / persistent routine lifecycle certification is now PASS / CLOSED.

## 28. Exact Current Development Point

JARVIS is at post-recovery stabilization: current code implements Gemini Live desktop/hosted interfaces, deterministic authority guards, LILITH persistent memory/routines/HA integration, and local Windows actions. No new feature branch was started. The active boundary is “certify the existing behavior,” not “extend it.”

## 29. GO / NO-GO

**GO for the JL-A10 core spoken Gemini Live / persistent routine lifecycle gate.** Optional robustness checks remain non-blocking operational validation.

## 30. Exact Next JARVIS Task

Next task is **AUT-9**, but it was not started by this documentation update. Start AUT-9 only on explicit owner request.
