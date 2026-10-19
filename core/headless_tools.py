"""Headless-only tool implementations for JARVIS on Ubuntu.

Provides system monitoring, process inspection, systemd management,
and log reading — all with proper permission gating.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.headless.tools")


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    SAFE_WRITE = "safe_write"
    CONFIRM_REQUIRED = "confirm_required"
    DENIED = "denied"


@dataclass(frozen=True)
class ToolPermission:
    tool: str
    action: str
    level: PermissionLevel
    description: str = ""


_SYSTEMD_ALLOWLIST = frozenset({
    "jarvis-headless",
    "jarvis-soak",
    "lilith",
    "lilith-worker",
    "nginx",
    "tailscaled",
})

_SYSTEMD_MUTATING = frozenset({"restart", "start", "stop"})

_JOURNAL_ALLOWLIST = frozenset({
    "jarvis-headless",
    "jarvis-soak",
    "lilith",
    "lilith-worker",
    "nginx",
    "tailscaled",
    "pulseaudio",
})

_MAX_JOURNAL_LINES = 100
_MAX_PROCESS_LIST = 50


def system_status() -> dict[str, Any]:
    """Read-only system status: CPU, RAM, swap, load, disk, uptime, temperature, network."""
    result: dict[str, Any] = {}

    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        result["load"] = {"1m": parts[0], "5m": parts[1], "15m": parts[2]}
    except OSError:
        result["load"] = "unavailable"

    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                key, _, val = line.partition(":")
                meminfo[key.strip()] = val.strip()
        total = int(meminfo.get("MemTotal", "0 kB").split()[0])
        avail = int(meminfo.get("MemAvailable", "0 kB").split()[0])
        swap_total = int(meminfo.get("SwapTotal", "0 kB").split()[0])
        swap_free = int(meminfo.get("SwapFree", "0 kB").split()[0])
        result["memory"] = {
            "total_mib": round(total / 1024),
            "available_mib": round(avail / 1024),
            "used_pct": round((1 - avail / total) * 100, 1) if total else 0,
        }
        result["swap"] = {
            "total_mib": round(swap_total / 1024),
            "used_mib": round((swap_total - swap_free) / 1024),
        }
    except (OSError, ValueError, ZeroDivisionError):
        result["memory"] = "unavailable"
        result["swap"] = "unavailable"

    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        hours, rem = divmod(int(secs), 3600)
        mins, secs_r = divmod(rem, 60)
        result["uptime"] = f"{hours}h{mins:02d}m{secs_r:02d}s"
    except OSError:
        result["uptime"] = "unavailable"

    try:
        with open("/proc/stat") as f:
            cpu_line = f.readline()
        parts = cpu_line.split()
        user, nice, system, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        total_t = user + nice + system + idle
        busy = user + nice + system
        result["cpu"] = {"usage_pct": round(busy / total_t * 100, 1) if total_t else 0}
    except (OSError, IndexError, ValueError):
        result["cpu"] = "unavailable"

    try:
        st = os.statvfs("/home")
        total_gb = st.f_blocks * st.f_frsize / (1024**3)
        free_gb = st.f_bavail * st.f_frsize / (1024**3)
        result["disk"] = {
            "mount": "/home",
            "total_gb": round(total_gb, 1),
            "free_gb": round(free_gb, 1),
            "used_pct": round((1 - free_gb / total_gb) * 100, 1) if total_gb else 0,
        }
    except OSError:
        result["disk"] = "unavailable"

    temps = _read_temperatures()
    if temps:
        result["temperature"] = temps

    try:
        r = subprocess.run(
            ["ip", "-br", "addr"], capture_output=True, text=True, timeout=5,
        )
        interfaces = []
        for line in r.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "UP":
                addrs = [p.split("/")[0] for p in parts[2:] if "." in p or ":" in p]
                interfaces.append({"name": parts[0], "addresses": addrs})
        result["network"] = interfaces
    except (subprocess.SubprocessError, OSError):
        result["network"] = "unavailable"

    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "jarvis-headless"],
            capture_output=True, text=True, timeout=5,
        )
        result["jarvis_service"] = r.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        result["jarvis_service"] = "unknown"

    return result


def _read_temperatures() -> dict[str, str] | None:
    hwmon = Path("/sys/class/hwmon")
    if not hwmon.exists():
        return None
    temps = {}
    for sensor_dir in hwmon.iterdir():
        name_path = sensor_dir / "name"
        if not name_path.exists():
            continue
        sensor_name = name_path.read_text().strip()
        for temp_input in sorted(sensor_dir.glob("temp*_input")):
            try:
                millicelsius = int(temp_input.read_text().strip())
                label_path = temp_input.with_name(temp_input.name.replace("_input", "_label"))
                label = label_path.read_text().strip() if label_path.exists() else temp_input.stem
                temps[f"{sensor_name}/{label}"] = f"{millicelsius / 1000:.1f}°C"
            except (ValueError, OSError):
                continue
    return temps or None


def process_list(filter_name: str = "") -> list[dict[str, Any]]:
    """List top processes by CPU/memory. Optional name filter."""
    try:
        r = subprocess.run(
            ["ps", "aux", "--sort=-rss"],
            capture_output=True, text=True, timeout=5,
        )
        lines = r.stdout.strip().splitlines()
        procs = []
        for line in lines[1:]:
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            name = parts[10]
            if filter_name and filter_name.lower() not in name.lower():
                continue
            procs.append({
                "user": parts[0],
                "pid": parts[1],
                "cpu": parts[2],
                "mem": parts[3],
                "rss_kb": parts[5],
                "command": name[:120],
            })
            if len(procs) >= _MAX_PROCESS_LIST:
                break
        return procs
    except (subprocess.SubprocessError, OSError) as e:
        return [{"error": str(e)}]


def process_info(pid: int) -> dict[str, Any]:
    """Detailed info for a specific PID."""
    try:
        r = subprocess.run(
            ["ps", "-p", str(pid), "-o", "pid,ppid,user,%cpu,%mem,rss,vsz,etime,comm", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return {"error": f"Process {pid} not found"}
        parts = r.stdout.strip().split(None, 8)
        return {
            "pid": parts[0], "ppid": parts[1], "user": parts[2],
            "cpu_pct": parts[3], "mem_pct": parts[4],
            "rss_kb": parts[5], "vsz_kb": parts[6],
            "elapsed": parts[7], "command": parts[8] if len(parts) > 8 else "",
        }
    except (subprocess.SubprocessError, OSError) as e:
        return {"error": str(e)}


def systemd_status(service: str) -> dict[str, Any]:
    """Read-only status of an allowlisted systemd --user service."""
    base = service.replace(".service", "")
    if base not in _SYSTEMD_ALLOWLIST:
        return {"error": f"Service '{service}' is not in the allowed list."}
    unit = f"{base}.service"
    try:
        r = subprocess.run(
            ["systemctl", "--user", "show", unit,
             "-p", "ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp,LoadState"],
            capture_output=True, text=True, timeout=5,
        )
        props = {}
        for line in r.stdout.strip().splitlines():
            k, _, v = line.partition("=")
            props[k] = v
        return props
    except (subprocess.SubprocessError, OSError) as e:
        return {"error": str(e)}


def systemd_action(service: str, action: str) -> dict[str, Any]:
    """Mutating action on an allowlisted systemd --user service. Returns confirmation request."""
    base = service.replace(".service", "")
    if base not in _SYSTEMD_ALLOWLIST:
        return {"error": f"Service '{service}' is not in the allowed list."}
    if action not in _SYSTEMD_MUTATING:
        return {"error": f"Action '{action}' is not allowed. Allowed: {', '.join(sorted(_SYSTEMD_MUTATING))}"}
    return {
        "confirmation_required": True,
        "action": action,
        "service": f"{base}.service",
        "summary": f"Systemd {action} {base}.service — this will affect the running service.",
    }


def systemd_execute(service: str, action: str) -> dict[str, Any]:
    """Actually execute a confirmed systemd action."""
    base = service.replace(".service", "")
    if base not in _SYSTEMD_ALLOWLIST or action not in _SYSTEMD_MUTATING:
        return {"error": "Not allowed"}
    unit = f"{base}.service"
    try:
        r = subprocess.run(
            ["systemctl", "--user", action, unit],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return {"result": f"Successfully executed: systemctl --user {action} {unit}"}
        return {"error": r.stderr.strip() or f"Exit code {r.returncode}"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"error": str(e)}


def systemd_list_failed() -> list[dict[str, str]]:
    """List failed systemd --user units."""
    try:
        r = subprocess.run(
            ["systemctl", "--user", "--failed", "--no-pager", "--plain", "--no-legend"],
            capture_output=True, text=True, timeout=5,
        )
        units = []
        for line in r.stdout.strip().splitlines():
            parts = line.split(None, 4)
            if parts:
                units.append({"unit": parts[0], "state": parts[2] if len(parts) > 2 else "failed"})
        return units
    except (subprocess.SubprocessError, OSError) as e:
        return [{"error": str(e)}]


def journal_read(service: str, lines: int = 50, priority: str = "", since: str = "") -> str:
    """Read recent journal entries for an allowlisted service."""
    base = service.replace(".service", "")
    if base not in _JOURNAL_ALLOWLIST:
        return f"Service '{service}' is not in the allowed journal list."
    lines = min(lines, _MAX_JOURNAL_LINES)
    cmd = ["journalctl", "--user", "-u", f"{base}.service", "--no-pager", "-n", str(lines), "--output=short-iso"]
    if priority:
        cmd.extend(["-p", priority])
    if since:
        cmd.extend(["--since", since])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = r.stdout.strip()
        for secret_pattern in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "BEARER"):
            if secret_pattern in output.upper():
                output = "[REDACTED: potential secret detected in log output]"
                break
        return output or "(no entries)"
    except (subprocess.SubprocessError, OSError) as e:
        return f"Error reading journal: {e}"


# ── Capability Catalog (headless version) ──



_VOICE_CAPABILITIES = [
    {
        "group": "Fecha y hora",
        "tools": ["date_time"],
        "description": "Consulta la fecha y hora reales del servidor.",
        "examples": [
            "¿Qué hora es?",
            "¿Qué día es hoy?",
        ],
    },
    {
        "group": "Estado del sistema",
        "tools": ["system_status"],
        "description": "Consulta CPU, memoria, disco, uptime y carga del servidor.",
        "examples": [
            "¿Cómo está el servidor?",
            "¿Cuánta RAM queda libre?",
        ],
    },
    {
        "group": "Procesos",
        "tools": ["process_list", "process_info"],
        "description": "Consulta los procesos que se están ejecutando.",
        "examples": [
            "¿Qué procesos están consumiendo más?",
            "¿Está JARVIS ejecutándose?",
        ],
    },
    {
        "group": "Servicios",
        "tools": ["systemd_status", "systemd_action", "systemd_list_failed"],
        "description": "Consulta y controla servicios permitidos del servidor.",
        "examples": [
            "¿Está activo Home Assistant?",
            "¿Está fallando algún servicio?",
        ],
    },
    {
        "group": "Logs",
        "tools": ["journal_read"],
        "description": "Consulta registros recientes de servicios permitidos.",
        "examples": [
            "Mira los últimos errores de JARVIS.",
            "¿Qué ha pasado en el servicio de LILITH?",
        ],
    },
    {
        "group": "Memoria persistente",
        "tools": ["lilith_memory_search", "lilith_memory_store", "lilith_memory_delete"],
        "description": "Busca, guarda o elimina recuerdos persistentes a través de LILITH.",
        "examples": [
            "Recuerda que prefiero respuestas en castellano.",
            "¿Qué recuerdas sobre este proyecto?",
        ],
    },
    {
        "group": "Home Assistant",
        "tools": ["lilith_home_action", "lilith_home_status"],
        "description": "Consulta estados y controla dispositivos permitidos.",
        "examples": [
            "¿Está encendida la luz del mueble?",
            "Enciende la bombilla de la habitación.",
        ],
    },
    {
        "group": "Rutinas",
        "tools": ["lilith_routine"],
        "description": "Consulta y gestiona rutinas persistentes.",
        "examples": [
            "¿Qué rutinas tengo?",
            "Crea una rutina para apagar la luz a las diez.",
        ],
    },
    {
        "group": "Estado de LILITH",
        "tools": ["lilith_health"],
        "description": "Consulta si LILITH está disponible.",
        "examples": [
            "¿LILITH está conectada?",
            "¿Está funcionando LILITH?",
        ],
    },
    {
        "group": "Catálogo de capacidades",
        "tools": ["open_capabilities_catalog"],
        "description": "Explica qué puede hacer JARVIS Headless.",
        "examples": [
            "¿Qué sabes hacer?",
            "Dime tus funciones.",
        ],
    },
]


def _headless_capability_entries() -> list[dict[str, Any]]:
    """Build capability catalog from actual HEADLESS_ACTIONS + headless-specific tools."""
    entries = []
    for cap in _VOICE_CAPABILITIES:
        for tool in cap["tools"]:
            entries.append({
                "name": tool,
                "category": cap["group"],
                "description": cap["description"],
                "read_only": tool not in (
                    "systemd_action", "lilith_memory_store", "lilith_memory_delete",
                    "lilith_home_action", "lilith_routine",
                ),
                "confirmation_required": tool in (
                    "systemd_action", "lilith_memory_delete",
                ),
                "platform": "any" if tool.startswith("lilith") else "linux",
            })
    return entries


def build_headless_catalog() -> str:
    """Generate a voice-friendly catalog of headless capabilities.

    Returns text suitable for JARVIS to read aloud — no visual language,
    grouped by human capability with natural-language examples.
    """
    lines = []
    for cap in _VOICE_CAPABILITIES:
        lines.append(cap["group"])
        lines.append(f"  {cap['description']}")
        for ex in cap["examples"]:
            lines.append(f"  Ejemplo: {ex}")
        lines.append("")
    return "\n".join(lines)


def build_headless_catalog_technical() -> str:
    """Generate a detailed Markdown catalog for debug/API use."""
    entries = _headless_capability_entries()
    lines = [
        "# JARVIS Headless — Capability Catalog (Technical)",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    categories: dict[str, list] = {}
    for e in entries:
        categories.setdefault(e["category"], []).append(e)
    for cat, items in categories.items():
        lines.append(f"## {cat}")
        lines.append("")
        for item in items:
            flags = []
            if item["read_only"]:
                flags.append("READ_ONLY")
            else:
                flags.append("MUTATING")
            if item["confirmation_required"]:
                flags.append("CONFIRM_REQUIRED")
            lines.append(f"- **{item['name']}** — {item['description']}  ")
            lines.append(f"  {' '.join(flags)} | platform: {item['platform']}")
        lines.append("")
    return "\n".join(lines)


def build_headless_catalog_voice_summary() -> str:
    """One-line voice summary of all capabilities."""
    groups = [cap["group"].lower() for cap in _VOICE_CAPABILITIES]
    if len(groups) > 1:
        return ", ".join(groups[:-1]) + " y " + groups[-1]
    return groups[0] if groups else ""
