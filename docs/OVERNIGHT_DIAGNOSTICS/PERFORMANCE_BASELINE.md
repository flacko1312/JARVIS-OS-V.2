# PERFORMANCE_BASELINE — JARVIS Overnight Diagnostics
Generated: 2026-11-06 23:13 CET

All measurements taken with `JARVIS_SHARED_ALARMS_ENABLED=1` after deployment.
Timestamps are wall-clock CET. Values marked **MEASURED** vs **ESTIMATE**.

---

## Windows (AURORA)

| Metric | Value | Type |
|---|---|---|
| CPU usage | 4% | MEASURED |
| RAM used | 9.9 GB / 15.9 GB | MEASURED |
| Disk C: used | 539.6 GB (used) / 390.8 GB (free) | MEASURED |
| LILITH API latency | < 100ms (Invoke-RestMethod, local LAN) | MEASURED (qualitative) |
| Shared alarm create+verify roundtrip | < 500ms (observed in E2E test) | MEASURED (qualitative) |

JARVIS Windows runs interactively; no persistent memory footprint to baseline.

---

## Ubuntu (server-lilith)

| Metric | Value | Type |
|---|---|---|
| Uptime | 8 days 17h 28min | MEASURED (at 23:13) |
| Load average | 0.63 / 0.55 / 0.50 | MEASURED |
| CPU (us+sy) | ~23% | MEASURED |
| RAM total | 7288 MB | MEASURED |
| RAM used | 4037 MB | MEASURED |
| RAM available | 3252 MB | MEASURED |
| Swap used | 1865 MB / 4096 MB | MEASURED |
| Disk / used | 86 GB / 109 GB (84%) | MEASURED |
| TCP connections | 208 total, 31 established | MEASURED |

### JARVIS headless_main.py (PID 441329)
- Memory: ~332 MB (from systemctl status)
- CPU: 61+ minutes accumulated (since 18:35 prior session)
- Note: prior PID (141717) ran 4.5h; new PID started at 23:09 after restart

### Watcher overhead
- Poll interval: 2 seconds
- Each tick: 1 GET /api/v1/integration/memory/context call
- LILITH latency over loopback: < 10ms (estimate; not instrumented)
- CPU impact: negligible (< 1% incremental)

---

## LILITH Core

| Metric | Value | Type |
|---|---|---|
| Status | online | MEASURED |
| Database | true | MEASURED |
| MQTT | true | MEASURED |
| Memory API availability | 100% during test window | MEASURED |

---

## Alarm delivery latency

- Clock tick resolution: 2 seconds (watcher poll interval)
- Alarm delivery latency: 0–2 seconds after fire_at (worst case = one poll interval)
- max_lateness: 10 minutes (alarms older than 10 min are skipped)
- Pre-fire cancel safety window: cancel at any time before delivery clock tick

---

## Warnings

- Ubuntu disk at 84% — monitor, not critical
- Ubuntu swap usage at 45% (1.86 GB) — not degrading but monitor under heavy load
- Ubuntu RAM: 320 MB free (3.25 GB avail with cache) — adequate
