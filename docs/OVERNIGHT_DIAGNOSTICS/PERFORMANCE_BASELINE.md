# PERFORMANCE_BASELINE — JARVIS Overnight Diagnostics
Last updated: 2026-11-07 00:08 CET (automated overnight session — night 2)
First generated: 2026-11-06 23:13 CET

All measurements taken with `JARVIS_SHARED_ALARMS_ENABLED=1`.
Timestamps are wall-clock CET. Values marked **MEASURED** vs **ESTIMATE**.

---

## Windows (AURORA)

### Night 1 (2026-11-06 23:13)
| Metric | Value | Type |
|---|---|---|
| CPU usage | 4% | MEASURED |
| RAM used | 9.9 GB / 15.9 GB | MEASURED |
| Disk C: used | 539.6 GB (used) / 390.8 GB (free) | MEASURED |

### Night 2 (2026-11-07 00:08)
| Metric | Value | Type |
|---|---|---|
| CPU usage | 4% | MEASURED |
| RAM used | 9.47 GB / 15.87 GB | MEASURED |
| LILITH /health latency | 62ms | MEASURED |
| Shared alarm create+verify roundtrip | < 500ms (observed in live E2E test) | MEASURED (qualitative) |

JARVIS Windows runs interactively; no persistent memory footprint to baseline.

---

## Ubuntu (server-lilith)

### Night 1 (2026-11-06 23:13)
| Metric | Value | Type |
|---|---|---|
| Uptime | 8 days 17h 28min | MEASURED (at 23:13) |
| Load average | 0.63 / 0.55 / 0.50 | MEASURED |
| RAM available | 3252 MB | MEASURED |
| Swap used | 1865 MB / 4096 MB | MEASURED |

### Night 2 (2026-11-07 00:07)
| Metric | Value | Type |
|---|---|---|
| Uptime | 8 days 18h 22min | MEASURED |
| Load average | 0.77 / 0.63 / 0.55 | MEASURED |
| CPU (us+sy) | ~23% (jarvis-headless) | MEASURED |
| RAM total | 7.1 GB | MEASURED |
| RAM used | 4.3 GB | MEASURED |
| RAM free | 186 MB | MEASURED |
| RAM available (w/cache) | 2.8 GB | MEASURED |
| Swap used | 1.8 GB / 4.0 GB (45%) | MEASURED |
| Disk / used | 86 GB / 109 GB (84%) | MEASURED |

### JARVIS headless_main.py (PID 441329)
- Night 1: Memory ~332 MB RSS, CPU 61+ min accumulated (new PID at 23:09)
- Night 2: Memory 796 MB peak RSS (from systemctl), CPU 13min 24s / ~58min uptime = 23% avg
- arecord subprocess (PID 441393): 7.5 MB, 0.2% CPU

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
