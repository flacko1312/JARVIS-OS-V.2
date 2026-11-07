# PERFORMANCE_BASELINE — JARVIS Overnight Diagnostics
Last updated: 2026-11-07 06:08 CET (automated overnight session — night 8)
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

### JARVIS headless_main.py
- Night 1: PID 441329, Memory ~332 MB RSS, CPU 61+ min accumulated (new PID at 23:09)
- Night 2: PID 441329, Memory 796 MB peak RSS (from systemctl), CPU 13min 24s / ~58min uptime = 23% avg
- Night 3: PID 441329, Memory 1.6 GB RSS, then 2.1 GB peak (2h 55min uptime) — OOM risk reached
- **Night 4 ACTION: Service restarted at 02:05:46 CET due to OOM risk (2.1 GB RSS, 2.7 GB swap in use)**
- Night 4: PID 559658, Memory 398 MB RSS (4min uptime) — leak cleared by restart
- Night 5: PID 559658, Memory 796 MB RSS (62min uptime) — same instance, leak ongoing
- **Night 6 ACTION: Service restarted at 04:05:24 CET due to OOM risk (1.8 GB RSS)**
- Night 6: PID 639077, Memory 288 MB RSS (2.6min uptime) — leak cleared by restart
- Night 7: PID 639077, Memory 777 MB RSS (59min uptime) — same instance, leak ongoing
- **Night 8 ACTION: Service restarted at 06:05:14 CET due to OOM risk (1.88 GB RSS, ~1h 59min uptime)**
- Night 8: PID 720285, Memory 381 MB RSS (2.5min uptime) — leak cleared by restart
- RAM leak confirmed: ~555 MB/hour (night 7 measurement: 777 MB at 59min from 231 MB base); restart every 2h needed overnight.
- arecord subprocess: re-spawned after restart (new PID), running

### Night 8 (2026-11-07 06:07)
| Metric | Value | Type |
|---|---|---|
| Uptime (since night-8 restart) | ~2.5min | MEASURED |
| RAM total | 7288 MB | MEASURED |
| RAM used | 3338 MB | MEASURED |
| RAM available | 3949 MB | MEASURED |
| Disk / used | 84% | ESTIMATE (unchanged) |
| jarvis-headless RSS | 381 MB | MEASURED |
| RAM growth rate | ~555 MB/hr (from night 7 data: 231→777 MB over 59min) | MEASURED |
| Restart threshold ~1.5 GB ETA | ~08:07 CET | ESTIMATE |

### Night 7 (2026-11-07 05:04)
| Metric | Value | Type |
|---|---|---|
| Uptime | 59min (since night-6 restart at 04:05) | MEASURED |
| RAM total | 7288 MB | MEASURED |
| RAM used | 3772 MB | MEASURED |
| RAM available | 3515 MB | MEASURED |
| Swap used | ~2.4 GB / 4.1 GB (59%) | MEASURED |
| jarvis-headless RSS | 777 MB | MEASURED |
| jarvis-headless CPU | 14min 13s / 59min = ~24% avg | MEASURED |
| RAM growth rate | 231 MB → 777 MB in 59min = ~555 MB/hr | MEASURED |

### Night 5 (2026-11-07 03:07)
| Metric | Value | Type |
|---|---|---|
| Uptime (since night-4 restart) | 1h 2min | MEASURED |
| RAM total | 7.3 GB | MEASURED |
| RAM used | 3.7 GB | MEASURED |
| RAM available | 3.6 GB | MEASURED |
| Swap used | 2.5 GB / 4.1 GB (61%) | MEASURED |
| Disk / used | 84% | MEASURED |
| jarvis-headless RSS | 796 MB | MEASURED |
| jarvis-headless VmSwap | 0 kB | MEASURED |
| jarvis-headless CPU (accumulated) | 13min 49s / 62min uptime = ~22% avg | MEASURED |
| RAM growth rate (session 5) | 398 MB → 796 MB in 62min = ~394 MB/hour | MEASURED |
| Restart threshold ~1.5 GB ETA | ~04:50 CET | ESTIMATE |

### Night 4 (2026-11-07 02:10)
| Metric | Value | Type |
|---|---|---|
| Uptime (after restart) | 4min | MEASURED |
| RAM total | 7.1 GB | MEASURED |
| RAM used | 3.3 GB | MEASURED |
| RAM available | 3.9 GB | MEASURED |
| Swap used | 2.5 GB / 4.0 GB (63%) | MEASURED (draining from pre-restart) |
| Disk / used | 84% | MEASURED |
| jarvis-headless RSS | 398 MB | MEASURED |
| jarvis-headless CPU | 1min 3s / 4min = ~26% avg | MEASURED |

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

## Night 6 (2026-11-07 04:08) — immediately after restart
| Metric | Value | Type |
|---|---|---|
| Uptime (after restart) | 2.6min | MEASURED |
| RAM total | 7.3 GB (7288 MB) | MEASURED |
| RAM used | 3.3 GB (3336 MB) | MEASURED |
| RAM free | 1.9 GB (1916 MB) | MEASURED |
| RAM available (w/cache) | 3.9 GB (3952 MB) | MEASURED |
| Swap used | 2.5 GB / 4.1 GB (62%) | MEASURED |
| Disk / used | 84% | MEASURED |
| Load average | 2.02 / 1.81 / 1.23 | MEASURED |
| jarvis-headless RSS | 288 MB | MEASURED |
| jarvis-headless CPU | 39s / 2.6min uptime = ~25% avg | MEASURED |
| RAM growth rate (session 6) | fresh restart — insufficient data | N/A |
| Restart threshold ~1.5 GB ETA | ~06:00 CET | ESTIMATE |

### Windows (Night 6)
| Metric | Value | Type |
|---|---|---|
| CPU usage | 34% | MEASURED |
| RAM used | ~9.73 GB / ~15.87 GB | MEASURED |

---

## Night 7 (2026-11-07 05:04 CET) — session start (59min uptime since night-6 restart)
| Metric | Value | Type |
|---|---|---|
| Uptime (since night-6 restart) | 59min | MEASURED |
| RAM total | 7.3 GB (7288 MB) | MEASURED |
| RAM used | 3.8 GB (3772 MB) | MEASURED |
| RAM free | 1.4 GB (1400 MB) | MEASURED |
| RAM available (w/cache) | 3.5 GB (3515 MB) | MEASURED |
| Swap used | 2.4 GB / 4.1 GB (59%) | MEASURED |
| jarvis-headless RSS | 777 MB (795856 KB) | MEASURED |
| RAM growth rate (session 7 start) | 231 MB → 777 MB in 59min = **~555 MB/hour** | MEASURED |
| Restart threshold ~1.5 GB ETA | ~06:28-06:41 CET | ESTIMATE |

### Windows (Night 7)
| Metric | Value | Type |
|---|---|---|
| LILITH /health | HTTP 200 (online) | MEASURED |
| Feature flag | JARVIS_SHARED_ALARMS_ENABLED=1 | MEASURED |

---

## Warnings

- **Ubuntu RAM leak CONFIRMED**: 332 MB → 796 MB → 1.6 GB → 2.1 GB (RSS) over ~3 hours. Rate ~555-630 MB/hour. Night-4 triggered restart at 02:05 CET (2.1 GB), Night-6 triggered at 04:05 CET (1.8 GB), threshold lowered to 1.5 GB. Restart cadence: every 2–3 hours overnight. Next restart ETA ~06:28-06:41 CET.
- Ubuntu swap at 2.4 GB — slight improvement, still draining slowly. No OOM risk while RSS is fresh.
- Ubuntu disk at 84% — monitor, not critical
- Physical audio test still PENDING (requires user presence)
