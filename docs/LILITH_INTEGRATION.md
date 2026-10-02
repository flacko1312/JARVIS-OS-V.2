# LILITH integration (typed input) — JL-W001 → JL-W004

Status: **typed input integrated and verified (2026-10-02).** Voice is NOT routed (see "Not done").
Branch: `feat/lilith-runtime-integration` (not merged to `main`).

## What it does

When `LILITH_API_URL` and `LILITH_API_KEY` are set, typed messages are offered to LILITH first
(`JarvisRuntime.process_input`). Only text that LILITH **actually executed** is kept away from Gemini;
everything else goes to Gemini exactly as before. With the variables unset, JARVIS behaves as before.

| Typed text | Result |
|---|---|
| `recuerda que ...` | stored in LILITH (`jarvis_fact`); HUD shows `LILITH: Guardado...`; **not** sent to Gemini |
| `qué sabes de ...` | LILITH memory search; HUD shows the stored text; **not** sent to Gemini |
| HOME words (`luz`, `bombilla`, `puerta`, ...) | router needs an entity (JL-H005 pending) -> LILITH does nothing -> **sent to Gemini** |
| LILITH offline / error / timeout (12 s) | HUD note `LILITH no disponible; continúo con Gemini.` -> **sent to Gemini** |
| anything else (conversation, windows, files, ...) | **sent to Gemini** |
| internal prompts starting with `[` (e.g. `[UI EVENT]`), verified self-quit | never offered to LILITH |

## Runtime hook (actual code)

* `main.py` `JarvisLive.run()` is now a thin wrapper: if not `cloud_safe`, `LilithBridge.from_env()` +
  `start()` (same asyncio loop as `send_text`), then `await self._run_live()` (the previous `run()` body,
  renamed), and `bridge.stop()` in `finally`.
* `main.py` `JarvisLive.send_text()`: after the self-quit decision and before `send_client_content`,
  `_offer_typed_to_lilith(text)`; `True` -> return without sending to Gemini.
* `cloud_safe`/hosted mode never starts the bridge (a remote client must not use this machine's credential).
* `core/lilith_gateway.py` (`LilithBridge`): glue only; never raises; lazy import of `runtime`/`httpx`.

## Files

* Imported unchanged from `flacko1312/jarvis@db5c25f` (SHA-256 verified): `lilith_client/`, `router/`, `runtime.py`.
* New: `core/lilith_gateway.py`, `tests/test_lilith_runtime_wiring.py`, `scripts/lilith_typed_e2e.py`, this doc.
* Edited: `main.py` (+40 lines), `pyproject.toml` (`runtime`, `lilith_client*`, `router*`),
  `requirements.txt` (`httpx>=0.27`), `.env.example` (commented keys).
* PyInstaller specs unchanged: `main.py` imports `core.lilith_gateway` statically.

## Configuration (`.env`, untracked)

`LILITH_API_URL` (LAN address of the LILITH API, reachable from this PC; Tailscale was not reachable from
this PC when tested), `LILITH_API_KEY` = the **token part only** of an `API_INTEGRATION_TOKENS` entry
(`user:token` -> send `token`; the client sends `Authorization: Bearer <token>`). Optional:
`LILITH_TIMEOUT_SECONDS`, `LILITH_MAX_RETRIES`. The credential is AUTHORIZED + scope `integration`:
it can use memory and `/home/action` (allowlisted lights only) and is rejected on `/api/ha/services/*`.
**Never use an ADMIN token here.**

## Tests

* `tests/test_lilith_runtime_wiring.py`: 35 offline unittest tests (bridge, real router through the real
  runtime with a fake client, `send_text` hook, `run()` lifecycle, cloud_safe).
* Library tests (84) live in `flacko1312/jarvis` and need `pytest-asyncio` (not in this venv).
* Pre-existing failures in this repo (74, mostly `tests/test_ui_regressions.py`) are unrelated and unchanged.
* `scripts/lilith_typed_e2e.py`: manual E2E against the real runtime (real Gemini Live session, real LILITH).
  Side effects: one stored memory, a brief low-brightness change on one light (restored), one short Gemini turn.
  Run with `PYTHONUTF8=1`.

## Not done / next

* Voice: Gemini transcripts arrive at `turn_complete`, too late to route. Direction: Gemini tool/function
  calling -> LILITH (JL-W005, JL-W006).
* HOME by typed name needs name -> `entity_id` resolution (JL-H005).