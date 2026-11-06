# TEST_RESULTS — JARVIS Overnight Diagnostics
Generated: 2026-11-06 23:11 CET

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
