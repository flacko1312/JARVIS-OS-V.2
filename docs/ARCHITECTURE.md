# JARVIS Architecture

Status: **CANONICAL**. This document describes executable architecture verified during the 2026-10-08 recovery. When it conflicts with historical prose, code plus tests plus the recovery audit win.

## System boundary

```text
USER
  -> JARVIS PyQt desktop or authenticated web client
  -> Gemini Live conversation (audio/transcription/reasoning/tool selection)
  -> JARVIS provenance and authority guards
  -> JARVIS-local action OR LILITH integration API
  -> verified tool result
  -> Gemini Live audio response
  -> USER
```

JARVIS owns the human interface, Gemini Live session, microphone/playback, Spanish prompt, tool schemas, local Windows actions, and translation of natural language into structured calls. LILITH owns persistent personal memory, authoritative context, persistent routines, Home Assistant resolution/action authority, approvals, and other persistent cognitive state. Gemini selects language/tool intent; it is not authority for side effects or persistent state.

## Active runtimes

- Desktop: `main.py:cli_main` creates `JarvisLive` and the PyQt6 `ui.MainWindow`. This is the real `C:\JARVIS\.venv\Scripts\jarvis.exe` runtime.
- Hosted: `api/server.py` exposes authenticated FastAPI HTTP and `/ws`; it creates `JarvisLive(cloud_safe=True, external_audio=True)`. The Next.js client in `web/` is a second supported interface, not the Windows desktop runtime.
- Typed LILITH bridge: `core/lilith_gateway.py` owns one `runtime.JarvisRuntime`, using `router/` and `lilith_client/`. Voice tool calls go through `main.py` tool handlers instead.
- `/home/flako1312/jarvis` is a historical integration-library source/reference. Its imported `runtime.py`, `router/`, and `lilith_client/` copies are active inside this repository; the separate checkout is not the runtime.

## Gemini Live and audio

- SDK: supported `google.genai` async Live API in `main.py`.
- Model: `GEMINI_LIVE_MODEL`, then `config/api_keys.json:live_model`, then `models/gemini-2.5-flash-native-audio-preview-12-2025`; model discovery selects a Live-capable fallback when necessary.
- Voice: `GEMINI_VOICE_NAME`, then `config/api_keys.json:voice_name`, then `puck`; unsupported configured voices fall back to `puck` after a specific API error.
- Input: mono PCM16, 16 kHz, `sounddevice.RawInputStream`, 1024-frame chunks.
- Output: mono PCM16, 24 kHz, `sounddevice.RawOutputStream`, 1024-frame blocks, or WebSocket audio events in hosted mode.
- Gemini provides input/output transcription and audio synthesis. There is no separate production local STT pipeline. Optional external TTS code exists, but Gemini audio is the normal path.
- Feedback control suppresses microphone forwarding while JARVIS is speaking. Interruption is handled through Live activity/turn state and local shutdown/cancellation flags; hardware barge-in quality remains a human gate.
- The reconnect loop rebuilds a session after errors; shutdown exits it. No fabricated online state is documented as a substitute for a real Live connection.

## Tool execution and authority

`TOOL_DECLARATIONS` contains 46 unique schemas. `_receive_audio()` reads Gemini FunctionCalls, `_execute_tool_batch()` serializes every potentially mutating/mixed tool, and `_execute_tool_guarded()` applies turn provenance, duplicate FunctionCall ID, schedule, and memory authority guards before `_execute_tool()` dispatches. Results return via `session.send_tool_response()`.

Scheduled effects are fail-closed. Recurring requests route only to `lilith_routine`; one-shot reminders route to `reminder`; immediate Home actions route to `lilith_home_action`. FunctionCall IDs, session/turn provenance, pending routine state, and duplicate suppression are enforced.

Memory is fail-closed. Explicit persistent facts route to `lilith_memory_store`; explicit local/session-only state routes to in-process `save_memory`; ambiguous authority writes nowhere and requests clarification. Local memory is recreated per `JarvisLive` instance and is not written to the legacy JSON store.

## LILITH integration

`LilithClient` is the single HTTP client and uses bearer authentication, configured timeout, and bounded retry for connection/timeout failures. It covers health, runtime, docs, source, Git, command submit, memory search/context/store/delete, Home resolution/entity/action, and approval lifecycle. Persistent routines use the canonical command gateway with structured correlation/idempotency fields.

Mutating LILITH handlers report success only when the response contract confirms it. HOME actions resolve the entity through LILITH, validate supported action/parameters, execute through LILITH, and attempt state verification. Offline physical-control requests are reported as failures, not passed to Gemini to improvise.

## State and storage classification

| Store/system | Classification | Purpose |
|---|---|---|
| LILITH memory/context API | ACTIVE CANONICAL | Persistent personal facts and authoritative context |
| `JarvisLive._local_session_memory` | SESSION-ONLY | Explicit local/session operational notes |
| `memory/long_term.json` and legacy memory helpers | LEGACY COMPATIBILITY | Older prompt/context paths; personal categories are stripped when LILITH context is available |
| Hosted SQL database | ACTIVE CANONICAL for hosted accounts | Users, encrypted per-user secrets, chat records |
| OS keyring | ACTIVE CANONICAL for local secret UI | Local Gemini/OAuth secret material where supported |
| `config/api_keys.json` | LEGACY LOCAL CONFIG | Voice/model and older local key flow; ignored by Git |
| `tmp/jarvis_status.json` | CACHE/RUNTIME STATE | Best-effort local status only |
| Task queues in `agent/` and action modules | ACTIVE LOCAL | Background local work, not LILITH autonomy |
| JARVIS `reminder` | ACTIVE LOCAL ONE-SHOT | One-time OS reminder; never a persistent routine |

## GUI and concurrency

PyQt6 is the active Windows GUI. `JarvisLive` runs async work outside direct widget mutation and communicates through UI methods/signals. The hosted Next.js UI is independent. Historical first-run/tour test specifications never matched `ui.py` and are not an active product contract. Broad exception handling and the size of `main.py`/`ui.py` remain classified technical debt; visual redesign is out of scope.

## Security boundary

- Desktop local tools can launch applications, drive browser/keyboard/mouse, manipulate files, and invoke system actions. QA mode blocks real side effects unless separately opted in.
- Power actions require explicit computer/system intent. Messaging and email use prepare/approve lifecycles where implemented.
- `open_app` uses resolved executables without `shell=True`; only a validated `ms-settings:` URI uses `os.startfile`.
- Hosted HTTP uses bearer auth, per-user scoping, rate limits, encrypted secrets, production configuration validation, constrained CORS, and WebSocket subprotocol authentication. Tokens are session-scoped in the browser and no longer placed in WebSocket URLs. Arbitrary local code execution (`code_helper`) is excluded from the hosted allowlist.
- Secret values must never enter docs, Git, QA reports, or routine logs.

## Known noncanonical/legacy areas

The older `google.generativeai` SDK remains in several secondary agent/action modules, while the canonical Live and hosted chat paths use `google.genai`. Legacy JSON memory remains for compatibility. The historical UI tour specification is retained as skipped evidence. These are tracked in `docs/TECHNICAL_DEBT.md`.
