# LILITH integration — JL-W001 → JL-W006

Status: **typed input, voice tool calling, routines, HOME resolution, and LILITH command tools integrated.** Human microphone/Gemini Live routine conversation remains the only JL-A10 gate.
Branch: `main` (merged from `feat/lilith-gemini-tools` via fast-forward, 2026-10-04).

## What it does

When `LILITH_API_URL` and `LILITH_API_KEY` are set, typed messages are offered to LILITH first
(`JarvisRuntime.process_input`). Only text that LILITH **actually executed** is kept away from Gemini;
everything else goes to Gemini exactly as before. With the variables unset, JARVIS behaves as before.

| Typed text | Result |
|---|---|
| `recuerda que ...` | stored in LILITH (`jarvis_fact`); HUD shows `LILITH: Guardado...`; **not** sent to Gemini |
| `qué sabes de ...` | LILITH memory search; HUD shows the stored text; **not** sent to Gemini |
| HOME words (`luz`, `bombilla`, `puerta`, ...) | typed HOME resolves through LILITH `/home/resolve`; safe actions go through `/home/action`; ambiguous/unknown/not-allowed cases do nothing and report honestly |
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

## Install note (important)

The `jarvis` command runs from an editable install whose module map is fixed at install time. After
pulling this branch run once: `.venv\Scripts\python.exe -m pip install -e . --no-deps`. Without it
`runtime`/`router`/`lilith_client` are not importable from the `jarvis` command and the bridge disables
itself (the HUD then shows `SYS: LILITH is configured but the integration could not be loaded.`).

## Tests

* `tests/test_lilith_runtime_wiring.py`: 35 offline unittest tests (bridge, real router through the real
  runtime with a fake client, `send_text` hook, `run()` lifecycle, cloud_safe).
* Library tests (84) live in `flacko1312/jarvis` and need `pytest-asyncio` (not in this venv).
* Pre-existing failures in this repo (74, mostly `tests/test_ui_regressions.py`) are unrelated and unchanged.
* Current Linux recovery baseline: `tests/test_lilith_home_resolution.py` = 33 passed. Focused memory authority (`TestPersistentMemoryFlow` + `TestMemoryCanonicalization`) = 23 passed, 4 subtests passed when run with temporary `sounddevice`/`google.genai` stubs; full collection still needs the supported GUI/audio environment.
* `scripts/lilith_typed_e2e.py`: manual E2E against the real runtime (real Gemini Live session, real LILITH).
  Side effects: one stored memory, a brief low-brightness change on one light (restored), one short Gemini turn.
  Run with `PYTHONUTF8=1`.

## Done since initial doc

* **JL-H005**: HOME by typed name resolves through LILITH (`/home/resolve`). Verified E2E.
* **JL-W005/W006**: Gemini Live tool calling → LILITH. Tools include memory, HOME, health/runtime, docs/source/Git, command submit, and routines. Offline/Linux slices and Windows tool E2E passed; human microphone/Gemini Live routine conversation remains.
* **JL-M003**: Memory context injection into Gemini system prompt.
* **JL-S003**: Approval flow for CONSULTATIVE/SENSITIVE actions.
* **JL-M004**: Deterministic semantic fact identity + context freshness.
* **JL-A7/JL-A8/JL-A9**: Persistent routines, due execution through LILITH/AUT-5, and natural-language routine tool.
* **JL-A10**: Real server/JARVIS tool E2E passed; only owner-operated Windows GUI microphone validation remains.

## Canonical workflow (2026-10-04)

* **Development**: `/home/flako1312/JARVIS-OS-V2` (Ubuntu, `main` branch)
* **Remote**: `origin` = `flacko1312/JARVIS-OS-V.2` (canonical)
* **Windows runtime**: `C:\JARVIS` — deployment only, pull from `origin/main`
* **upstream**: `MAL19INDUSTRIES/JARVIS-OS-V.2` — reference only, never push

## Backup: Windows → Ubuntu (2026-10-04)

Architecture: **Windows pushes outbound** to Ubuntu via SCP. Ubuntu validates and promotes.

| Component | Location | Purpose |
|---|---|---|
| `scripts/jarvis_backup.ps1` | Windows (`C:\JARVIS`) | PowerShell sender — SCP files to Ubuntu |
| `scripts/jarvis_backup_receive.sh` | Ubuntu | Validates JSON, checksums, promotes snapshot |

### What is backed up

| Files | Retention |
|---|---|
| `memory\long_term.json`, `memory\task_history.json`, `config\ui_settings.json`, `config\layout_settings.json` | 14 days |

**Not backed up (by design)**: `.env`, `config/api_keys.json`, tokens, passwords. Automated
plaintext secret backup is disabled. Encrypted secret backup is a future task.

### Directory structure (Ubuntu)

```
/mnt/lilith_data/backups/jarvis/
  incoming/     ← files land here during transfer (transient)
  snapshots/    ← promoted validated backups (timestamped)
  latest/       ← symlink to most recent good snapshot
  logs/         ← per-run receiver logs
```

### Configuration

On first run, the PowerShell sender requires `-UbuntuUser` and `-UbuntuHost`. These are
cached in `C:\JARVIS\config\backup_target.json` for subsequent runs. The SSH key defaults
to `$HOME\.ssh\id_ed25519`.

### Recovery procedure

From Ubuntu, copy files back to Windows:

```powershell
# On Windows — pull from the latest snapshot
scp -i $HOME\.ssh\id_ed25519 USER@UBUNTU:/mnt/lilith_data/backups/jarvis/latest/memory/long_term.json C:\JARVIS\memory\long_term.json
scp -i $HOME\.ssh\id_ed25519 USER@UBUNTU:/mnt/lilith_data/backups/jarvis/latest/memory/task_history.json C:\JARVIS\memory\task_history.json
scp -i $HOME\.ssh\id_ed25519 USER@UBUNTU:/mnt/lilith_data/backups/jarvis/latest/config/ui_settings.json C:\JARVIS\config\ui_settings.json
scp -i $HOME\.ssh\id_ed25519 USER@UBUNTU:/mnt/lilith_data/backups/jarvis/latest/config/layout_settings.json C:\JARVIS\config\layout_settings.json
```

Or verify a specific snapshot first:

```bash
# On Ubuntu
cd /mnt/lilith_data/backups/jarvis/snapshots/<STAMP>
sha256sum -c SHA256SUMS.txt
cat MANIFEST.json
```

### Invariants

- Retention is **never** applied if the current backup failed.
- Secret values are **never** backed up or printed.
- Failed incoming snapshots are preserved for debugging, not deleted.
- `latest/` symlink is only updated after successful validation.

## Not done / next

* Voice E2E: requires Windows PC with microphone + Gemini Live real session.
* JL-EA001-012: External agents (Claude/Codex) — not started.
