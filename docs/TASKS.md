# JARVIS Ubuntu Headless — Tasks

Status: **CANONICAL ACTIONABLE BACKLOG** as of 2026-10-24 for `server-lilith`.

## Current priority

The Ubuntu runtime is operational and already contains Blocks 6–9. The current job is **stabilization and closure**, not adding unrelated features.

## P0 — protect and consolidate the current runtime

Status: **IN PROGRESS / SAFETY CHECKPOINT CREATED**.

- Canonical runtime: `/home/flako1312/jarvis-headless`.
- Current branch: `fix/rebuild-integrity-fast`.
- Current runtime base HEAD: `2ad1f89`.
- Safety snapshot of the active working tree: `backup/ubuntu-headless-runtime-2026-10-24` at `19a3bc9`, pushed to GitHub.
- Blocks 6–9 development branch: `feat/headless-capabilities-6-9` at `7f89500`, pushed to GitHub and already merged into the runtime lineage via `fc4b13c`.

Do not delete or reset the active working tree until its changes have been reviewed and promoted intentionally.

## P1 — validate the active headless changes

Status: **PENDING**.

Validate the current working-tree changes with targeted automated tests and then physical checks. Focus on:

- barge-in and interrupted-turn behavior;
- replay/duplicate/void-turn suppression;
- conversation continuity;
- Gemini transient disconnect/reconnect recovery;
- headless system tools and permissions;
- LILITH memory/Home/routine routing;
- service health after restart/reconnect.

Do not turn this into a refactor or UI project.

## P1 — finish Block 10 physical acceptance

Status: **IMPLEMENTATION PRESENT / PHYSICAL ACCEPTANCE NOT CLOSED**.

The runtime lineage contains voice-stability and recovery work, but final acceptance must distinguish automated coverage from physical evidence. Required physical checks include real microphone behavior, interruption/barge-in, real recoverable Gemini/network interruption, reconnection without losing immediate context, and device/reconnect behavior where applicable.

## P1 — clean Ubuntu release candidate

Status: **PENDING AFTER VALIDATION**.

After the active changes pass:

1. classify every uncommitted file as production code, test/docs, experiment, runtime state or disposable development helper;
2. commit only validated production/test/docs work to the Ubuntu release line;
3. keep runtime state and private configuration out of Git;
4. mark experimental Telegram gateway work separately unless explicitly promoted;
5. push the clean Ubuntu candidate to GitHub and record the exact commit.

## P2 — documentation and deployment consistency

Status: **PARTIALLY CLOSED 2026-10-24**.

- `docs/PROJECT_STATE.md` now identifies `/home/flako1312/jarvis-headless` as the canonical Ubuntu runtime.
- `/home/flako1312/jarvis-headless-dev` is development only.
- `/home/flako1312/JARVIS-OS-V2` is legacy/reference only.
- AURORA Windows remains a separate adapter/runtime in `C:\JARVIS`.

Before Ubuntu freeze, recheck `README.md`, `docs/ARCHITECTURE.md`, deployment docs and the document index for the same boundary.

## Experimental / not closure blockers

- Telegram text gateway: experimental until explicitly validated/promoted.
- Patch/generator scripts: development artifacts.
- New UI/redesign work: out of scope for Ubuntu closure.
- LILITH-native wake/STT/TTS: not the canonical voice pipeline.
- Smart Display, Avatar, new domotic families and other V2 expansions: do not block this closure.

## Final soak

Status: **DEFERRED UNTIL GLOBAL FREEZE**.

Do not start or certify the final 24-hour soak while LILITH/AURORA/JARVIS Ubuntu/Monitor are still being changed. A final soak is meaningful only after the complete V1 configuration is frozen.

## Closure criterion

JARVIS Ubuntu Headless is ready to freeze when:

- active runtime changes are classified and committed cleanly;
- automated required tests pass;
- physical voice/reconnect gates pass or are explicitly separated as HUMAN-GATED;
- LILITH integration is healthy;
- service restart/recovery is verified;
- GitHub contains the exact release candidate;
- documentation matches the deployed runtime;
- no critical state depends on an untracked file.
