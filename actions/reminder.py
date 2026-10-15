import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from actions.jarvis_file_stamp import mark_created_file, write_text_with_stamp
from core.schedule_safety import daily_time_from_text, normalize_timezone, normalized_turn_text, schedule_semantics

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _scripts_dir() -> Path:
    configured = os.environ.get("JARVIS_REMINDER_DIR", "").strip()
    d = Path(configured) if configured else Path.home() / ".jarvis" / "reminders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _registry_path() -> Path:
    return _scripts_dir() / "registry.json"


def _load_registry() -> list[dict]:
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _save_registry(items: list[dict]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True)
    fd, temporary = tempfile.mkstemp(prefix="reminders-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def _cleanup_registry(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(ZoneInfo("UTC"))
    active: list[dict] = []
    for item in _load_registry():
        try:
            target = datetime.fromisoformat(str(item["target_at"]))
        except (KeyError, TypeError, ValueError):
            continue
        if target.tzinfo is None:
            target = target.replace(tzinfo=ZoneInfo("UTC"))
        if target >= now - timedelta(hours=1):
            active.append(item)
    _save_registry(active)
    return active


_SPANISH_AMOUNTS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10, "once": 11, "doce": 12,
}


def _parse_natural_datetime(
    text: str,
    *,
    timezone_name: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime | None, str | None]:
    """Parse one-shot Spanish date/time wording, returning an error/clarification."""
    timezone_name = normalize_timezone(timezone_name) or "Europe/Madrid"
    zone = ZoneInfo(timezone_name)
    current = now.astimezone(zone) if now else datetime.now(zone)
    value = normalized_turn_text(text)
    if schedule_semantics(value) == "recurring":
        return None, "Las rutinas recurrentes deben gestionarse como rutinas de LILITH, no como recordatorios."

    import re
    relative = re.search(
        r"\b(?:en|dentro de)\s+(\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\s+"
        r"(minuto|minutos|hora|horas|dia|dias)\b",
        value,
    )
    if relative:
        raw = relative.group(1)
        amount = int(raw) if raw.isdigit() else _SPANISH_AMOUNTS[raw]
        unit = relative.group(2)
        delta = timedelta(
            minutes=amount if unit.startswith("minuto") else 0,
            hours=amount if unit.startswith("hora") else 0,
            days=amount if unit.startswith("dia") else 0,
        )
        return current + delta, None

    iso_date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", value)
    if iso_date:
        try:
            date_value = datetime.strptime(iso_date.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None, "No pude interpretar la fecha."
    elif "pasado manana" in value:
        date_value = (current + timedelta(days=2)).date()
    elif "manana" in value:
        date_value = (current + timedelta(days=1)).date()
    elif "hoy" in value:
        date_value = current.date()
    else:
        date_value = current.date()

    ambiguous_tomorrow = re.search(
        rf"\bmanana\s+a las?\s+(?:\d{{1,2}}|{'|'.join(_SPANISH_AMOUNTS)})\b",
        value,
    ) and not re.search(r"\b(?:de la )?(?:manana|tarde|noche)\b\s*$", value)
    if ambiguous_tomorrow:
        return None, "La hora es ambigua. Indica mañana, tarde, noche o formato 24 horas."

    clock = daily_time_from_text(value)
    numeric = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", value)
    if numeric:
        clock = int(numeric.group(1)), int(numeric.group(2))
    if clock is None:
        hour_words = "|".join(_SPANISH_AMOUNTS)
        if re.search(rf"\ba las?\s+(?:\d{{1,2}}|{hour_words})\b", value):
            return None, "La hora es ambigua. Indica mañana, tarde, noche o formato 24 horas."
        return None, "Necesito una hora concreta para el recordatorio."
    target = datetime.combine(date_value, datetime.min.time(), tzinfo=zone).replace(
        hour=clock[0], minute=clock[1]
    )
    if target <= current:
        return None, "Esa hora ya ha pasado."
    return target, None


def _sanitise(text: str, max_len: int = 200) -> str:
    return (
        text.replace("\\", "")
            .replace('"', "")
            .replace("'", "")
            .replace("\n", " ")
            .replace("\r", "")
            .strip()
    )[:max_len]

def _write_notify_script(task_name: str, message: str, os_name: str) -> Path:
    script_path = _scripts_dir() / f"{task_name}.py"
    msg_literal = json.dumps(message)  

    if os_name == "windows":
        notify_block = f"""
message = {msg_literal}
notified = False

try:
    from plyer import notification
    notification.notify(title="J.A.R.V.I.S Reminder", message=message, timeout=15)
    notified = True
except Exception:
    pass

if not notified:
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast("J.A.R.V.I.S Reminder", message, duration=15, threaded=False)
        notified = True
    except Exception:
        pass

if not notified:
    try:
        import subprocess
        subprocess.run(["msg", "*", "/TIME:30", message], check=False)
    except Exception:
        pass

try:
    import winsound
    for freq in [800, 1000, 1200]:
        winsound.Beep(freq, 180)
        import time; time.sleep(0.08)
except Exception:
    pass
"""

    elif os_name == "mac":
        notify_block = f"""
message = {msg_literal}
notified = False

try:
    from plyer import notification
    notification.notify(title="J.A.R.V.I.S Reminder", message=message, timeout=15)
    notified = True
except Exception:
    pass

if not notified:
    try:
        import subprocess
        script = 'display notification "{{}}" with title "J.A.R.V.I.S Reminder"'.format(
            message.replace('"', '')
        )
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        pass
"""

    else:  # linux
        notify_block = f"""
message = {msg_literal}
notified = False

try:
    from plyer import notification
    notification.notify(title="J.A.R.V.I.S Reminder", message=message, timeout=15)
    notified = True
except Exception:
    pass

if not notified:
    try:
        import subprocess
        subprocess.run(
            ["notify-send", "--urgency=normal", "--expire-time=15000",
             "J.A.R.V.I.S Reminder", message],
            check=False
        )
    except Exception:
        pass
"""

    script_body = f"""# Auto-generated by J.A.R.V.I.S reminder — do not edit
import sys, os, pathlib
{notify_block}
# Self-delete after firing
try:
    pathlib.Path(__file__).unlink(missing_ok=True)
except Exception:
    pass
"""
    write_text_with_stamp(script_path, script_body, "Reminder helper script generated by JARVIS.")
    script_path.chmod(0o600)   # owner read/write only
    return script_path

def _schedule_windows(target_dt: datetime, task_name: str,
                      script_path: Path, message: str) -> str:
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists():
        python_exe = pythonw

    xml_path = _scripts_dir() / f"{task_name}.xml"
    xml_content = (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <RegistrationInfo><Description>J.A.R.V.I.S Reminder</Description></RegistrationInfo>\n'
        '  <Triggers><TimeTrigger>\n'
        f'    <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>\n'
        '    <Enabled>true</Enabled>\n'
        '  </TimeTrigger></Triggers>\n'
        '  <Actions><Exec>\n'
        f'    <Command>{python_exe}</Command>\n'
        f'    <Arguments>"{script_path}"</Arguments>\n'
        '  </Exec></Actions>\n'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>\n'
        '    <Enabled>true</Enabled>\n'
        '  </Settings>\n'
        '  <Principals><Principal>\n'
        '    <LogonType>InteractiveToken</LogonType>\n'
        '    <RunLevel>LeastPrivilege</RunLevel>\n'
        '  </Principal></Principals>\n'
        '</Task>'
    )

    xml_path.write_text(xml_content, encoding="utf-16")
    mark_created_file(xml_path, "Windows scheduled task XML generated by JARVIS reminder.")

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
        capture_output=True, text=True,
    )

    try:
        xml_path.unlink(missing_ok=True)
    except Exception:
        pass

    if result.returncode != 0:
        script_path.unlink(missing_ok=True)
        err = (result.stderr or result.stdout).strip()
        print(f"[Reminder] ❌ schtasks: {err}")
        return ""  

    return task_name


def _schedule_mac(target_dt: datetime, task_name: str,
                  script_path: Path) -> str:
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    label     = f"com.jarvis.reminder.{task_name}"
    plist_path = agents_dir / f"{label}.plist"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script_path}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Year</key>   <integer>{target_dt.year}</integer>
    <key>Month</key>  <integer>{target_dt.month}</integer>
    <key>Day</key>    <integer>{target_dt.day}</integer>
    <key>Hour</key>   <integer>{target_dt.hour}</integer>
    <key>Minute</key> <integer>{target_dt.minute}</integer>
  </dict>
  <key>RunAtLoad</key>         <false/>
  <key>StandardOutPath</key>   <string>/dev/null</string>
  <key>StandardErrorPath</key> <string>/dev/null</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content, encoding="utf-8")
    mark_created_file(plist_path, "macOS launchd plist generated by JARVIS reminder.")
    plist_path.chmod(0o644)

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        plist_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
        print(f"[Reminder] ❌ launchctl: {result.stderr.strip()}")
        return ""

    return label


def _schedule_linux(target_dt: datetime, task_name: str,
                    script_path: Path) -> str:

    if shutil.which("systemd-run"):
        on_calendar = target_dt.strftime("%Y-%m-%d %H:%M:00")
        result = subprocess.run(
            [
                "systemd-run",
                "--user",
                f"--on-calendar={on_calendar}",
                f"--unit={task_name}",
                "--",
                sys.executable, str(script_path),
            ],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return task_name
        print(f"[Reminder] ⚠️ systemd-run failed: {result.stderr.strip()}, trying 'at'")

    if shutil.which("at"):
        at_time = target_dt.strftime("%H:%M %Y-%m-%d")
        cmd_str = f"{sys.executable} {script_path}\n"
        result  = subprocess.run(
            ["at", at_time],
            input=cmd_str, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return task_name
        print(f"[Reminder] ❌ at: {result.stderr.strip()}")
        return ""

    print("[Reminder] ❌ Neither systemd-run nor at found on this Linux system.")
    return ""


def _cancel_job(item: dict, os_name: str) -> bool:
    job_id = str(item.get("job_id") or "")
    if not job_id:
        return False
    if os_name == "windows":
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", job_id, "/F"],
            capture_output=True, text=True,
        )
    elif os_name == "mac":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{job_id}.plist"
        result = subprocess.run(["launchctl", "unload", str(plist)], capture_output=True, text=True)
        if result.returncode == 0:
            plist.unlink(missing_ok=True)
    else:
        result = subprocess.run(
            ["systemctl", "--user", "stop", f"{job_id}.timer"],
            capture_output=True, text=True,
        )
    if result.returncode == 0:
        script_value = str(item.get("script_path") or "").strip()
        if script_value:
            Path(script_value).unlink(missing_ok=True)
        return True
    return False


def _list_reminders(items: list[dict]) -> str:
    if not items:
        return "No tienes recordatorios pendientes."
    lines = ["Recordatorios pendientes:"]
    for item in sorted(items, key=lambda value: str(value.get("target_at", ""))):
        lines.append(f"- {item.get('id')}: {item.get('message')} — {item.get('target_at')}")
    return "\n".join(lines)


def _schedule_record(
    target: datetime,
    message: str,
    timezone_name: str,
    *,
    reminder_id: str | None = None,
) -> tuple[dict | None, str | None]:
    os_name = _get_os()
    safe_msg = _sanitise(message)
    reminder_id = reminder_id or f"rem_{uuid.uuid4().hex[:12]}"
    task_name = f"JARVISReminder_{reminder_id}"
    try:
        script_path = _write_notify_script(task_name, safe_msg, os_name)
        local_wall_time = target.astimezone().replace(tzinfo=None)
        if os_name == "windows":
            job_id = _schedule_windows(local_wall_time, task_name, script_path, safe_msg)
        elif os_name == "mac":
            job_id = _schedule_mac(local_wall_time, task_name, script_path)
        else:
            job_id = _schedule_linux(local_wall_time, task_name, script_path)
    except Exception:
        try:
            script_path.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
        return None, "Algo salió mal al programar el recordatorio."
    if not job_id:
        return None, "No pude registrar el recordatorio con el programador del sistema."
    return {
        "id": reminder_id,
        "message": safe_msg,
        "target_at": target.isoformat(),
        "timezone": timezone_name,
        "job_id": job_id,
        "script_path": str(script_path),
        "created_at": datetime.now(ZoneInfo("UTC")).isoformat(),
    }, None

def reminder(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    action = str(parameters.get("action") or "create").strip().lower()
    timezone_name = normalize_timezone(parameters.get("timezone"))
    if timezone_name is None:
        return "La zona horaria no es válida. Usa un nombre IANA, por ejemplo Europe/Madrid."
    items = _cleanup_registry()

    if action == "list":
        return _list_reminders(items)

    reminder_id = str(parameters.get("id") or parameters.get("reminder_id") or "").strip()
    if action in {"cancel", "delete"}:
        item = next((entry for entry in items if entry.get("id") == reminder_id), None)
        if item is None:
            return "No encuentro ese recordatorio."
        if not _cancel_job(item, _get_os()):
            return "No pude cancelar el recordatorio en el programador del sistema."
        _save_registry([entry for entry in items if entry.get("id") != reminder_id])
        return f"Recordatorio {reminder_id} cancelado."

    if action not in {"create", "modify", "update"}:
        return f"Acción de recordatorio no compatible: {action}."

    old_item = None
    if action in {"modify", "update"}:
        old_item = next((entry for entry in items if entry.get("id") == reminder_id), None)
        if old_item is None:
            return "No encuentro ese recordatorio para modificarlo."

    message = str(parameters.get("message") or (old_item or {}).get("message") or "Recordatorio").strip()
    natural = str(parameters.get("text") or parameters.get("when") or "").strip()
    date_str = str(parameters.get("date") or "").strip()
    time_str = str(parameters.get("time") or "").strip()
    if not natural and date_str and time_str:
        natural = f"{date_str} {time_str}"
    if not natural:
        return "Necesito una fecha y una hora para el recordatorio."
    target, error = _parse_natural_datetime(natural, timezone_name=timezone_name)
    if error:
        return error
    assert target is not None

    duplicate = next((
        entry for entry in items
        if entry.get("id") != reminder_id
        and normalized_turn_text(str(entry.get("message", ""))) == normalized_turn_text(message)
        and abs((datetime.fromisoformat(str(entry["target_at"])) - target).total_seconds()) < 60
    ), None)
    if duplicate:
        return f"Ya existe un recordatorio equivalente: {duplicate.get('id')}."

    record, schedule_error = _schedule_record(
        target, message, timezone_name, reminder_id=reminder_id or None
    )
    if schedule_error or record is None:
        return schedule_error or "No pude programar el recordatorio."
    if old_item is not None and not _cancel_job(old_item, _get_os()):
        _cancel_job(record, _get_os())
        return "No pude sustituir el recordatorio anterior; no se aplicaron cambios."
    remaining = [entry for entry in items if entry.get("id") != reminder_id]
    remaining.append(record)
    _save_registry(remaining)
    return (
        f"Recordatorio {record['id']} programado para "
        f"{target.strftime('%Y-%m-%d %H:%M')} ({timezone_name})."
    )
