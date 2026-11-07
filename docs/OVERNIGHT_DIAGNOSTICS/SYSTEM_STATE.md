# SYSTEM_STATE — JARVIS Overnight Diagnostics
Last updated: 2026-11-07 04:08 CET (automated overnight session — night 6)
First generated: 2026-11-06 23:11 CET

---

## Windows (AURORA) — C:\JARVIS

| Property | Value |
|---|---|
| Hostname | flako |
| OS | Windows 11 Home |
| Branch | codex/neural-voice-visual |
| HEAD commit | b3123e0 docs(alarm): overnight verification night 5 — 19/19 E2E PASS + RAM stable |
| Working tree | Clean (only untracked: VOICE_CHECK_2026-11-06.md, lilith_client/*.bak, logs/) |
| Untracked | VOICE_CHECK_2026-11-06.md, lilith_client/adapter_connector.py.bak.m3_20261106, logs/ |

### Active processes (JARVIS)
- JARVIS Windows does NOT run as a background service; invoked interactively
- main.py imports gate `is_enabled()` per call — no restart required for flag change

### Configuration
```
LILITH_API_URL=http://192.168.1.50:8000       ✓ configured
LILITH_API_KEY=<token>                         ✓ configured
JARVIS_SHARED_ALARMS_ENABLED=1                 ✓ ENABLED (this session)
JARVIS_ALARM_TIMEZONE=Europe/Madrid            ✓ configured
JARVIS_PREFERRED_OUTPUT_DEVICE=M197WD
GEMINI_VOICE_NAME=puck
```

### Dependencies
- LILITH Core: 192.168.1.50:8000 (Docker)
- Ubuntu JARVIS watcher: 192.168.1.50:7471 (headless_main.py)
- Windows IP (Wi-Fi): 192.168.1.45 (dynamic — verify at runtime)

---

## Ubuntu (server-lilith) — /home/flako1312/jarvis-headless

| Property | Value |
|---|---|
| Hostname | server-lilith |
| Branch | codex/neural-voice-visual |
| HEAD commit | b836e1f test(alarm): extended runner coverage |
| Working tree | Many preexisting modified/untracked entries (preserved, not committed) |
| Service | jarvis-headless.service (systemd --user) |
| PID | 639077 (restarted night 6 at 04:05:24 CET — previous PID 559658 killed due to 1.8 GB RAM leak) |
| Running since | 2026-11-07 04:05:24 CET |
| CPU (accumulated) | 39s / 2.6min uptime = ~24% avg |
| RAM (RSS) | 288 MB at 04:08 CET (fresh after restart; threshold ~1.5 GB ETA ~06:00 CET) |

### Active services
| Service | Port | State |
|---|---|---|
| jarvis-headless | 7471 (HTTP gateway) | active/running |
| LILITH Core | 8000 | online (db=true, mqtt=true) |
| chat-api | - | running |
| jarvis-telegram | - | running |
| jarvis-adapter-presence | - | running |
| lilith-global-soak-24h | - | **inactive** |
| lilith-soak01 | - | **inactive** |

### Configuration
```
LILITH_API_URL=http://127.0.0.1:8000           ✓ configured
LILITH_API_KEY=<token>                          ✓ configured
JARVIS_SHARED_ALARMS_ENABLED=1                  ✓ ENABLED (this session)
JARVIS_ALARM_TIMEZONE=Europe/Madrid             ✓ configured
```

### Connections
- Ubuntu is co-located with LILITH (same machine, 127.0.0.1)
- Ubuntu watcher polls LILITH memory API every 2 seconds
- Windows communicates to LILITH at 192.168.1.50:8000 over local network

---

## LILITH Core

| Property | Value |
|---|---|
| Host | server-lilith (192.168.1.50) |
| Port | 8000 |
| Status | online |
| Database | true |
| MQTT | true |

### Shared alarm records in LILITH (pre-deployment)
- 9 records in category `jarvis_alarm` (older format, NOT v2 — safely ignored)
- 0 receipts
- 0 valid v2 records (confirmed by shared_alarm_v2.list() returning 0)

---

## Feature flags state after deployment

| Flag | Windows | Ubuntu |
|---|---|---|
| JARVIS_SHARED_ALARMS_ENABLED | **1** | **1** |
| Watcher running | N/A (Windows creates only) | **YES** (journal confirmed) |
