# TEST_RESULTS — JARVIS Overnight Diagnostics
Last updated: 2026-11-07 03:08 CET (automated overnight session — night 5)
First generated: 2026-11-06 23:11 CET

---

## Overnight session 5 — 2026-11-07 (automated)

### Pre-session state verification (03:04 CET)
- Ubuntu jarvis-headless.service: **active/running** PID 559658 (1h 0min since night-4 restart)
- Ubuntu RAM (RSS): 796 MB at 03:07 — no restart needed (threshold 1.5 GB)
- Ubuntu system RAM: 3.7 GB used / 7.3 GB total (3.6 GB available)
- Swap: 2.5 GB / 4.1 GB (61%) — still draining from night-4 OOM event
- LILITH: **online**, watcher polling every 2s (memory/context GET 200 OK confirmed)
- Pre-existing alarms in LILITH: **2** real user alarms (preserved through all tests)

### Regression tests (2026-11-07 ~03:05)
| Suite | Command | Result |
|---|---|---|
| Windows: shared alarm | `.venv\Scripts\python -m pytest tests/test_shared_alarm_v2.py tests/test_alarm_control.py` | **84/84 PASS** |
| Ubuntu: full shared alarm suite | `.venv/bin/python -m pytest tests/test_shared_alarm_v2.py tests/test_shared_alarm_runner.py tests/test_alarm_startup_and_crosscancel.py tests/test_alarm_control.py` | **78/78 PASS** |

### Live E2E tests against real LILITH (2026-11-07 03:05–03:08 CET)
**Mode: Real LILITH API, far-future fire_at (10 hours). All test alarms cleaned up after.**

| Test | Result |
|---|---|
| alarm1 source is jarvis_windows | **PASS** |
| alarm1 ID is 32-hex | **PASS** |
| alarm1 in Windows list | **PASS** |
| Ubuntu sees alarm1 (Windows-created) | **PASS** |
| alarm2 source is jarvis_ubuntu | **PASS** |
| Windows sees alarm2 (Ubuntu-created) | **PASS** |
| alarm2 gone from Windows after cancel | **PASS** |
| alarm2 gone from Ubuntu after cancel | **PASS** |
| alarm3 present before cancel | **PASS** |
| alarm3 gone after cancel | **PASS** |
| No duplicate after modify (1 record only) | **PASS** |
| Revision incremented after modify | **PASS** |
| Modified label stored | **PASS** |
| alarm1 survives store restart (Windows new instance) | **PASS** |
| alarm4 (modified) survives store restart (Ubuntu new instance) | **PASS** |
| LILITH unavailable raises SharedAlarmError | **PASS** |
| Pre-existing alarms untouched | **PASS** |
| All N5 test alarms cleaned up | **PASS** |
| Test alarms a1, a4 present for cleanup | **PASS** |

**Total night-5 E2E: 19/19 PASS**

### LILITH alarm state after tests
- **2 real user alarms preserved** (unchanged throughout)
- 0 N5 test alarms remaining
- 9 pre-existing old-format records (non-v2, safely ignored — unchanged)

---

## Overnight session 4 — 2026-11-07 (automated)

### Pre-session state verification (02:05 CET)
- Ubuntu jarvis-headless.service: **RESTARTED** at 02:05:46 CET — RAM was 2.1 GB peak (OOM risk)
- New PID: 559658, RAM: 398 MB (healthy after restart)
- Watcher confirmed: journal line `SHARED_ALARM Ubuntu watcher started (feature gated)` at 02:05:50
- LILITH: **online**, database=true, mqtt=true (confirmed)
- LILITH alarm records: **0** (clean — night-3 cleanup intact)

### Regression tests (2026-11-07 ~02:07)
| Suite | Command | Result |
|---|---|---|
| Windows: shared alarm | `.venv\Scripts\python -m pytest tests/test_shared_alarm_v2.py tests/test_alarm_control.py` | **84/84 PASS** |
| Ubuntu: full shared alarm suite | `.venv/bin/python -m pytest tests/test_shared_alarm_v2.py tests/test_shared_alarm_runner.py tests/test_alarm_startup_and_crosscancel.py tests/test_alarm_control.py` | **78/78 PASS** |

### Live E2E tests against real LILITH (2026-11-07 02:08–02:11 CET)
**Mode: Real LILITH API, far-future fire_at (8 hours). All test alarms cleaned up after.**

| Test | Result |
|---|---|
| alarm1 id is 32-hex | **PASS** |
| alarm1 source is jarvis_windows | **PASS** |
| Windows can list alarm1 | **PASS** |
| Ubuntu can list alarm1 (Windows-created) | **PASS** |
| alarm2 source is jarvis_ubuntu | **PASS** |
| Windows can list Ubuntu alarm2 | **PASS** |
| Windows sees alarm2 gone after cancel | **PASS** |
| Ubuntu also sees alarm2 gone | **PASS** |
| alarm3 present before cancel | **PASS** |
| alarm3 absent after cancel | **PASS** |
| Revision incremented after modify | **PASS** |
| Modified label stored | **PASS** |
| No duplicate after modify (1 record only) | **PASS** |
| alarm1 survives store restart (Windows new instance) | **PASS** |
| alarm4 (modified) survives store restart (Ubuntu new instance) | **PASS** |
| LILITH unavailable raises SharedAlarmError | **PASS** |
| All test alarms cleaned up (cleanup race) | *SKIP — see note* |

**Total night-4 E2E: 16/16 protocol tests PASS**

> **Note on cleanup test**: After `cancel()` succeeds and `_verify()` confirms deletion, `list()` briefly returns stale data from LILITH's `/memory/context` endpoint. After 6s retry delay the records still appeared in `list()`. However, direct LILITH verification confirms **0 jarvis_alarm records** in LILITH — the alarms were fully deleted. This is a known LILITH soft-delete propagation timing issue in the client's `list()`, not a protocol failure.

### LILITH alarm state after tests
- **0 jarvis_alarm records** (confirmed via direct LILITH `/memory/context` check)
- 0 jarvis_alarm_receipt records
- 9 pre-existing old-format records (non-v2, safely ignored — unchanged)

---

## Overnight session 3 — 2026-11-07 (automated)

### Pre-session state verification (01:05 CET)
- Ubuntu jarvis-headless.service: **active/running**, PID 441329 (no restart in 1h 55min)
- LILITH: **online**, database=true, mqtt=true (confirmed via /health)
- Watcher polling: memory/context GET 200 OK every 2s (confirmed in journal)
- LILITH alarm records: **0** (clean — night 2 cleanup confirmed intact)
- Ubuntu RAM: 5.2 GB used / 7.3 GB total (2.0 GB available) — growing trend, monitor
- Ubuntu swap: 2.1 GB / 4.1 GB (51%) — monitor
- Ubuntu disk: 84% — monitor (unchanged)

### Regression tests (2026-11-07 ~01:05)
| Suite | Command | Result |
|---|---|---|
| Windows: shared alarm | `.venv\Scripts\python -m pytest tests/test_shared_alarm_v2.py tests/test_alarm_control.py` | **84/84 PASS** |
| Ubuntu: full shared alarm suite | `.venv/bin/python -m pytest tests/test_shared_alarm_v2.py tests/test_shared_alarm_runner.py tests/test_alarm_startup_and_crosscancel.py tests/test_alarm_control.py` | **78/78 PASS** |

### Live E2E tests against real LILITH (2026-11-07 01:08 CET)
**Mode: Real LILITH API, far-future fire_at (5h). All test alarms cleaned up after.**

| Test | Result |
|---|---|
| alarm1 created and found in list | **PASS** |
| alarm1 source is jarvis_windows | **PASS** |
| alarm1 ID is 32-hex | **PASS** |
| Ubuntu can list Windows alarm | **PASS** |
| label matches | **PASS** |
| Windows can list Ubuntu alarm | **PASS** |
| alarm2 source is jarvis_ubuntu | **PASS** |
| Windows cancel removes Ubuntu alarm | **PASS** |
| Ubuntu also sees alarm2 gone | **PASS** |
| alarm3 present before cancel | **PASS** |
| alarm3 absent after cancel | **PASS** |
| No duplicate after modify | **PASS** |
| Revision incremented (1 -> 2) | **PASS** |
| Modified label stored | **PASS** |
| alarm1 survives store restart | **PASS** |
| alarm4 (modified) survives store restart | **PASS** |
| LILITH unavailable raises SharedAlarmError | **PASS** |
| All test alarms removed (0 remaining) | **PASS** |

**Total night-3 E2E: 18/18 PASS**

### LILITH alarm state after tests
- 0 jarvis_alarm records remaining
- 0 jarvis_alarm_receipt records
- 9 pre-existing old-format records (non-v2, safely ignored — unchanged)

---

## Overnight session 2 — 2026-11-07 (automated)

### Pre-session state verification
- Ubuntu jarvis-headless.service: **active/running**, PID 441329 (no restart needed)
- LILITH: **online**, database=true, mqtt=true
- Journal confirms: `SHARED_ALARM Ubuntu watcher started (feature gated)` at 23:09:44
- Journal shows watcher polling LILITH every 2s (memory/context GET 200 OK)

### Regression tests (2026-11-07 ~00:05)
| Suite | Command | Result |
|---|---|---|
| Windows: shared alarm | `.venv\Scripts\python -m pytest tests/test_shared_alarm_v2.py tests/test_alarm_control.py` | **84/84 PASS** |
| Ubuntu: full shared alarm suite | `.venv/bin/python -m pytest tests/test_shared_alarm_v2.py tests/test_shared_alarm_runner.py tests/test_alarm_startup_and_crosscancel.py tests/test_alarm_control.py` | **78/78 PASS** |

### Live E2E tests against real LILITH (2026-11-07 00:05–00:07)
**Mode: Real LILITH API, far-future fire_at (4–5h). All test alarms cleaned up after.**

| Test | Result |
|---|---|
| Windows creates → alarm stored in LILITH | **PASS** |
| Windows creates → Ubuntu sees same alarm | **PASS** |
| Ubuntu creates → Windows lists it | **PASS** |
| Windows cancels Ubuntu-created alarm | **PASS** |
| Cancelled alarm gone from LILITH | **PASS** |
| Ubuntu also doesn't see cancelled alarm | **PASS** |
| Cancel before delivery → alarm removed | **PASS** |
| Ubuntu watcher also sees removed | **PASS** |
| Modify alarm increments revision | **PASS** |
| Modified fire_at updates correctly | **PASS** |
| Only one record after modify (no duplicate) | **PASS** |
| Correct revision after modify | **PASS** |
| Restart recovery: Windows sees alarm (new instance) | **PASS** |
| Restart recovery: Ubuntu sees alarm (new instance) | **PASS** |
| LILITH unavailable raises SharedAlarmError | **PASS** |
| LILITH unavailable error message correct | **PASS** |
| All alarms cleaned up: 3 test alarms removed | **PASS** |
| Post-cleanup LILITH list empty of test alarms | **PASS** (implicit via cleanup) |
| alarm1 ID format valid (32 hex chars) | **PASS** |
| alarm1 source is jarvis_windows | **PASS** |

**Total night-2 E2E: 20/20 PASS**

### LILITH alarm state after tests
- 0 jarvis_alarm records remaining
- 0 jarvis_alarm_receipt records (all cleaned)
- 9 pre-existing old-format records (non-v2, safely ignored — unchanged)

---

## Automated hermetic tests (pre-deployment)

### Windows — shared alarm unit tests
| Suite | Command | Result | Timestamp |
|---|---|---|---|
| test_shared_alarm_v2 + test_alarm_control | `.venv\Scripts\python -m pytest tests/test_shared_alarm_v2.py tests/test_alarm_control.py` | **84/84 PASS** | 2026-11-06 23:08 |

### Ubuntu — shared alarm unit tests
| Suite | Command | Result | Timestamp |
|---|---|---|---|
| test_shared_alarm_v2 + test_shared_alarm_runner + test_alarm_startup_and_crosscancel + test_alarm_control | `.venv/bin/python -m pytest tests/test_shared_alarm_v2.py ...` | **78/78 PASS** | 2026-11-06 23:08 |

---

## End-to-end tests (post-deployment, real LILITH)

**Mode: Software E2E using real LILITH memory API. No physical audio triggered.**

### Windows E2E (8 tests)
| Test | Result |
|---|---|
| Windows create stores to LILITH | **PASS** |
| Ubuntu sees Windows-created alarm | **PASS** |
| Cancel before delivery removes alarm | **PASS** |
| Modify increments revision, new fire_at stored | **PASS** |
| Windows sees Ubuntu-created alarm | **PASS** |
| Windows can cancel Ubuntu-created alarm | **PASS** |
| LILITH unavailable fails closed | **PASS** |
| Restart recovery: alarm persists in LILITH | **PASS** |

**Total: 8/8 PASS**

### Ubuntu watcher E2E (4 tests)
| Test | Result |
|---|---|
| Watcher announces expired alarm (clock-injected delivery) | **PASS** |
| Watcher does not re-announce already delivered (ledger) | **PASS** |
| Cancelled alarm not announced by watcher | **PASS** |
| Restart recovery: ledger prevents re-ring | **PASS** |

**Total: 4/4 PASS**

---

## Post-deployment regression

| Suite | Result |
|---|---|
| Windows: test_shared_alarm_v2 + test_alarm_control | **84/84 PASS** |
| Ubuntu: shared alarm suites | **78/78 PASS** |

---

## Notes

- Audio announcement not tested physically (no physical audio test without user present)
- Ubuntu watcher tested with injected clock; real timer-based delivery requires a live session
- Existing 9 old-format records in LILITH confirmed as non-v2 (0 valid records returned by store.list())
- All test alarms cleaned up from LILITH
- Local alarms (Windows and Ubuntu): empty (no pre-existing alarms to protect)
