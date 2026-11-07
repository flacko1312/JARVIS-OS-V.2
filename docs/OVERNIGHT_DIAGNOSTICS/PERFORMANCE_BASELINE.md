# PERFORMANCE_BASELINE — JARVIS Overnight Diagnostics
Last updated: 2026-11-07 01:09 CET (automated overnight session — night 3)
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

### Night 3 (2026-11-07 01:05)
| Metric | Value | Type |
|---|---|---|
| Uptime | 8 days 19h 20min | MEASURED |
| Load average | 1.07 / 0.73 / 0.61 | MEASURED |
| RAM total | 7.1 GB (7288 MB) | MEASURED |
| RAM used | 5.1 GB (5205 MB) | MEASURED |
| RAM available | 2.0 GB (2083 MB) | MEASURED |
| Swap used | 2.1 GB / 4.1 GB (51%) | MEASURED |
| Disk / used | 86 GB / 109 GB (84%) | MEASURED |
| LILITH /health latency | < 100ms (online confirmed) | MEASURED (qualitative) |

### JARVIS headless_main.py (PID 441329)
- Night 1: Memory ~332 MB RSS, CPU 61+ min accumulated (new PID at 23:09)
- Night 2: Memory 796 MB peak RSS (from systemctl), CPU 13min 24s / ~58min uptime = 23% avg
- Night 3: Memory 1.6 GB RSS (systemctl, ~1h 55min uptime), CPU 27min 8s = ~24% avg
- RAM trend: 332 MB -> 796 MB -> 1.6 GB over ~2h. GROWING — monitor for memory leak in Gemini SDK or watcher.
- arecord subprocess (PID 441393): active, 7.5 MB, 0.2% CPU (unchanged)

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

- **Ubuntu RAM growing**: 332 MB -> 796 MB -> 1.6 GB (RSS) over ~2 hours. Rate ~630 MB/hour. If this continues, the system may OOM by morning. Likely Gemini SDK or watcher's asyncio loop. Monitor closely. If OOM risk: `systemctl --user restart jarvis-headless.service`.
- Ubuntu disk at 84% — monitor, not critical
- Ubuntu swap usage at 51% (2.1 GB) — elevated, monitor
- Ubuntu available RAM: 2.0 GB — currently adequate
