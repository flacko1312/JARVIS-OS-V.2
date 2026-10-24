# JARVIS Ubuntu Headless — Project State

Status: **CANONICAL CURRENT STATE** as of 2026-10-24 for the Ubuntu deployment on `server-lilith`.

## Canonical runtime authority

- Runtime checkout: `/home/flako1312/jarvis-headless`
- Entry point: `headless_main.py`
- User service: `jarvis-headless.service`
- Active branch: `fix/rebuild-integrity-fast`
- Runtime base HEAD at this reconciliation: `2ad1f892f03e5027943d3a6e8e3d7707e1438d3c`
- GitHub repository: `flacko1312/JARVIS-OS-V.2`
- The GitHub `main` branch is currently the AURORA/Windows line. It is **not** the Ubuntu runtime branch.

The running service was verified from `/home/flako1312/jarvis-headless`. On 2026-10-24 `/health` returned `LISTENING`; `/status` reported Gemini connected, LILITH online, headless mode enabled and audio enabled.

## Repository/clones classification

- `/home/flako1312/jarvis-headless`: **CANONICAL UBUNTU RUNTIME**. All Ubuntu operational documentation must describe this checkout first.
- `/home/flako1312/jarvis-headless-dev`: **DEVELOPMENT CLONE / NOT RUNTIME**. Blocks 6–9 from `feat/headless-capabilities-6-9` were merged into the canonical runtime through merge commit `fc4b13c`. The branch is also published on GitHub at `7f89500` for traceability.
- `/home/flako1312/JARVIS-OS-V2`: **LEGACY/REFERENCE CLONE / NOT RUNTIME**. Its local uncommitted experiment was preserved on GitHub branch `backup/jarvis-os-v2-local-2026-10-24` at checkpoint `98f6d0b` without changing its working tree.

## Protected current Ubuntu work

The canonical runtime has active uncommitted development files. They were preserved without changing the running working tree on GitHub branch:

`backup/ubuntu-headless-runtime-2026-10-24` → checkpoint `19a3bc9`

Runtime-only state such as `.headless.pid`, local conversation state, scratchpad data and local memory backups was intentionally excluded from that Git checkpoint.

## Implemented Ubuntu headless capability blocks

### Core/headless runtime

- Persistent systemd user service and health/status HTTP surface.
- Gemini Live voice runtime without PyQt dependency.
- Separate headless conversation-state path.
- LILITH connectivity and headless-only tool allowlist.

### Block 6 — Ubuntu system capabilities

Implemented in the runtime lineage: date/time, system status, disk status, Docker/infrastructure status, bounded service logs, process inspection, systemd status/actions, failed-unit inspection, journal reads and capability catalog.

### Blocks 7–9 — LILITH expansion, remote API and voice stability

Merged into the runtime through `fc4b13c`. The development commits include Home/LILITH status and permissions expansion, secure remote/Tailscale-oriented API work, and voice stability/reconnect metrics.

### Current headless tool profile

The current runtime allowlist contains 21 headless tools: web search; date/time; system/disk/Docker/infrastructure status; service logs; process list/info; systemd status/action/failed units; journal read; LILITH memory search/store/delete; LILITH Home action/status; LILITH health; routines; and the capability catalog.

Targeted headless validation on 2026-10-24: `tests/test_headless_block1.py` → **109 passed, 0 failed, 1 third-party deprecation warning** when run with the service user's PulseAudio/DBus runtime environment. Two stale playback-stream tests were corrected to call the now-instance-bound helper correctly; production behavior was not changed. Health remained `LISTENING` after validation.

## Voice/stability work after Blocks 6–9

The Ubuntu branch contains additional work for local barge-in, interrupted-turn handling, replay/duplicate protection, void-turn filtering, transient Gemini recovery and conversation continuity. These commits are in the ancestry of the current runtime branch and its remote freeze/safety branches.

Do **not** interpret implementation as final physical certification. Hardware-dependent voice behavior, real disconnect/reconnect acceptance and the final global soak remain validation gates.

## Experimental/not yet canonical

- Telegram text gateway files exist in the active working tree and are included in the 2026-10-24 safety checkpoint. They are **experimental / not part of the closed Ubuntu V1 baseline** until explicitly validated and promoted.
- Patch/generator scripts in the working tree are development artifacts, not production authority.
- `/home/flako1312/JARVIS-OS-V2` is not a second production runtime.

## Architecture boundary

**LILITH CORE is the central cognitive/persistent core.** JARVIS Ubuntu Headless is an Ubuntu/voice/system adapter. It must not become a second independent cognitive core.

AURORA/JARVIS Windows is a separate Windows adapter/runtime in `C:\JARVIS`. Its documentation and physical validations are maintained on the Windows checkout.

## Soak policy

No final 24-hour certification soak should be claimed while AURORA Windows, JARVIS Ubuntu, Monitor or the final integration configuration are still changing. Partial soak windows may be retained as stability evidence only. The final soak begins after the complete V1 baseline is frozen.

## Immediate next work

1. Keep the active Ubuntu runtime protected; do not discard the current working tree.
2. Reconcile the active runtime changes into a clean Ubuntu release branch after tests/physical acceptance.
3. Finish the remaining hardware-gated voice/reconnect checks.
4. Freeze the Ubuntu candidate only when those checks pass.
5. Defer the final 24-hour soak until the whole ecosystem baseline is frozen.
