# TROUBLESHOOTING — JARVIS Overnight Diagnostics
Generated: 2026-11-06

---

## JARVIS Windows not responding

1. Run main.py manually: `cd C:\JARVIS && .\.venv\Scripts\python.exe main.py`
2. Check .env has GEMINI_API_KEY and LILITH_API_KEY set
3. Check network: `Test-NetConnection 192.168.1.50 -Port 8000`
4. Shared alarms only: check JARVIS_SHARED_ALARMS_ENABLED=1 in .env

---

## JARVIS Ubuntu not responding

```bash
# Check service
systemctl --user status jarvis-headless.service

# Restart
systemctl --user restart jarvis-headless.service

# Logs
journalctl --user-unit jarvis-headless.service -n 100 --no-pager

# Manual start (debug)
cd /home/flako1312/jarvis-headless
source .env
.venv/bin/python3 headless_main.py
```

---

## Ubuntu jarvis-headless RAM leak (CONFIRMED as of night 4; night 5 rate updated)

**Symptom**: RSS grows ~400–630 MB/hour from baseline ~300 MB. After ~3 hours, OOM risk.

**Confirmed rates**:
- Nights 2–3: ~630 MB/hour
- Night 5: ~394 MB/hour (same PID 559658, 62min: 398 MB → 796 MB)
- Nights 2–3: 300 MB → 796 MB → 1.6 GB → 2.1 GB over 3 hours.

**Root cause**: Unknown — likely Gemini SDK streaming buffer or asyncio watcher task accumulation. No crash observed; service continues to function until killed by OOM.

**Mitigation**: Restart service when RSS exceeds ~1.5 GB or after 2–3 hours continuous uptime.

```bash
# Check current RAM
systemctl --user status jarvis-headless.service | grep Memory

# Safe restart (alarms persist in LILITH; watcher re-registers on startup)
systemctl --user restart jarvis-headless.service

# Verify watcher re-confirmed after restart
journalctl --user-unit jarvis-headless.service -n 20 | grep SHARED_ALARM
```

**Note**: Alarms are stored in LILITH (not in memory), so restart does NOT lose pending alarms.

---

## Shared alarm watcher not running

Symptoms: Alarms created on Windows don't ring on Ubuntu.

1. Check flag: `grep SHARED_ALARMS /home/flako1312/jarvis-headless/.env`
   - Must be `JARVIS_SHARED_ALARMS_ENABLED=1`
2. Check journal: `journalctl --user-unit jarvis-headless.service | grep SHARED_ALARM`
   - Should show: `SHARED_ALARM Ubuntu watcher started (feature gated)`
3. If missing, restart: `systemctl --user restart jarvis-headless.service`
4. Test watcher manually:
   ```bash
   cd /home/flako1312/jarvis-headless
   source .env
   export JARVIS_SHARED_ALARMS_ENABLED=1
   .venv/bin/python -m pytest -q tests/test_shared_alarm_runner.py
   ```

---

## Shared alarm not found after create

Symptoms: `SharedAlarmError: No se encontró esa alarma compartida`

Possible causes:
- Alarm was already claimed (receipt written) → `store.list()` excludes it
- Alarm record in older/incompatible format → `_parse_fact()` returns None
- Alarm fire_at was already 10+ minutes ago → watcher skips it
- LILITH returned HTTP non-200 → `SharedAlarmError` raised

Verify:
```python
# On Ubuntu:
source .env && .venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from actions.shared_alarm_v2 import SharedAlarmStore
s = SharedAlarmStore(source='jarvis_ubuntu')
print(s.list())
"
```

---

## Duplicate alarm announcements

The ledger (`~/.jarvis/alarms/shared_delivery_ledger.json`) prevents re-delivery.

If duplicates occur:
1. Check ledger: `cat ~/.jarvis/alarms/shared_delivery_ledger.json`
2. Check LILITH receipts in memory context (category `jarvis_alarm_receipt`)
3. Only one Ubuntu instance should run; running two watcher processes causes races

---

## Microphone / wakeword / speech (Ubuntu)

```bash
# List audio devices
arecord -l
aplay -l

# Check default
pactl info | grep Default

# Test mic capture (3 seconds, don't play back)
arecord -D plughw:CARD=Microphone,DEV=0 -d 3 -f S16_LE -r 16000 /tmp/mic_test.wav

# Check JARVIS wakeword in logs
journalctl --user-unit jarvis-headless.service -n 50 | grep -i wakeword
```

---

## LILITH not reachable

From Ubuntu:
```bash
curl -s http://127.0.0.1:8000/health
```

From Windows:
```powershell
Invoke-RestMethod http://192.168.1.50:8000/health
```

Expected: `{"status":"online","database":true,"mqtt":true}`

If LILITH is down:
- Shared alarms fail closed (no announcement, no data loss)
- Wait for LILITH to recover; watcher resumes automatically
- Do NOT modify LILITH Core, Docker, or HA

---

## Slow responses / high CPU / RAM

Ubuntu:
```bash
top -c -n1 | head -20
# Look for python3 headless_main.py
systemctl --user status jarvis-headless.service | grep Memory
```

Windows:
```powershell
Get-Process python* | Select-Object Name, CPU, WorkingSet
```

RAM growth observed: 332 MB at night-1 → 796 MB peak at night-2 (58 min of operation).
If RAM > 900 MB on Ubuntu JARVIS, restart: `systemctl --user restart jarvis-headless.service`

---

## Network failures between Windows and Ubuntu

```powershell
# From Windows, ping Ubuntu
ping 192.168.1.50

# Check JARVIS Ubuntu is listening
Test-NetConnection 192.168.1.50 -Port 7471
```

```bash
# From Ubuntu, verify IP
ip addr show | grep 192.168
# Windows typically: 192.168.1.45 (dynamic — may change)
```

Shared alarms use LILITH as the intermediary — Windows and Ubuntu never communicate directly for alarms. Only LILITH connectivity is required from each side.
