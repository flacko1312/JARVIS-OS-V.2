# AUT-12 — Automated soak/resource monitoring

## Harness

`scripts/soak_monitor.py` samples the current process without real email, Home Assistant, microphone, camera or browser actions. It records RSS, threads, Windows handles, recursive child processes, recognizable browser workers, zombie children and asyncio tasks when called inside a running loop.

It flags bounded indicators rather than claiming proof of leak absence: monotonic RSS growth above 96 MB, large count growth, handle growth and any zombie child. Duration is capped at one hour.

- CI/smoke: `python scripts/soak_monitor.py --duration 10 --interval 1`
- Manual 30-minute profile: `python scripts/soak_monitor.py --manual --interval 5`
- A future 60-minute run may use `--duration 3600 --interval 5`.

## Validation

- Unit regression: **6 passed**.
- One-second live sampler: **passed**, 6 samples, no warnings; RSS 29,347,840 → 29,364,224 bytes, 4 threads, 180 handles, 0 children/browser workers/zombies.

This short run detects obvious harness/resource regressions only. It does not prove absence of long-duration memory leaks. The 30–60 minute application workload remains a manual/extended validation item.
