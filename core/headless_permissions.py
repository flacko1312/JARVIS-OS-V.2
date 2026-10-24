"""Unified permission system for JARVIS Headless tool execution.

Every tool action maps to a PermissionLevel:
- READ_ONLY: no confirmation needed
- SAFE_WRITE: low-risk mutation, no confirmation
- CONFIRM_REQUIRED: user must explicitly confirm before execution
- DENIED: never allowed via voice

Reusable across Ubuntu system tools, Home Assistant, and routines.
"""
from __future__ import annotations

import logging
from enum import Enum
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.headless.permissions")


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    SAFE_WRITE = "safe_write"
    CONFIRM_REQUIRED = "confirm_required"
    DENIED = "denied"


@dataclass(frozen=True)
class PermissionRule:
    tool: str
    action: str
    level: PermissionLevel
    description: str = ""


_PERMISSION_RULES: dict[tuple[str, str], PermissionRule] = {}


def _register(tool: str, action: str, level: PermissionLevel, desc: str = "") -> None:
    _PERMISSION_RULES[(tool, action)] = PermissionRule(tool, action, level, desc)


# ── System tools ──
_register("system_status", "*", PermissionLevel.READ_ONLY, "System metrics are always safe to read")
_register("disk_status", "*", PermissionLevel.READ_ONLY, "Filesystem capacity is read-only")
_register("docker_status", "*", PermissionLevel.READ_ONLY, "Docker inspection is read-only")
_register("infrastructure_status", "*", PermissionLevel.READ_ONLY, "Known service probes are read-only")
_register("service_logs", "*", PermissionLevel.READ_ONLY, "Bounded allowlisted log reading is read-only")
_register("process_list", "*", PermissionLevel.READ_ONLY, "Process listing is read-only")
_register("process_info", "*", PermissionLevel.READ_ONLY, "Process detail is read-only")
_register("systemd_status", "*", PermissionLevel.READ_ONLY, "Service status is read-only")
_register("systemd_action", "restart", PermissionLevel.CONFIRM_REQUIRED, "Restarting a service disrupts it")
_register("systemd_action", "start", PermissionLevel.CONFIRM_REQUIRED, "Starting a service")
_register("systemd_action", "stop", PermissionLevel.CONFIRM_REQUIRED, "Stopping a service")
_register("systemd_list_failed", "*", PermissionLevel.READ_ONLY, "Listing failed units is read-only")
_register("journal_read", "*", PermissionLevel.READ_ONLY, "Log reading is read-only")
_register("date_time", "*", PermissionLevel.READ_ONLY, "Date/time is always safe")
_register("open_capabilities_catalog", "*", PermissionLevel.READ_ONLY, "Catalog is read-only")

# ── LILITH / Home Assistant ──
_register("lilith_memory_search", "*", PermissionLevel.READ_ONLY)
_register("lilith_memory_store", "*", PermissionLevel.SAFE_WRITE, "Storing memory is low-risk")
_register("lilith_memory_delete", "*", PermissionLevel.CONFIRM_REQUIRED, "Deleting memory is destructive")
_register("lilith_home_action", "turn_on", PermissionLevel.SAFE_WRITE, "Turning on lights/switches is safe")
_register("lilith_home_action", "turn_off", PermissionLevel.SAFE_WRITE, "Turning off lights/switches is safe")
_register("lilith_home_action", "toggle", PermissionLevel.SAFE_WRITE, "Toggling is safe")
_register("lilith_home_action", "lock", PermissionLevel.CONFIRM_REQUIRED, "Lock actions require confirmation")
_register("lilith_home_action", "unlock", PermissionLevel.CONFIRM_REQUIRED, "Unlock actions require confirmation")
_register("lilith_home_action", "*", PermissionLevel.CONFIRM_REQUIRED, "Unknown home actions need confirmation")
_register("lilith_home_status", "*", PermissionLevel.READ_ONLY)
_register("lilith_health", "*", PermissionLevel.READ_ONLY)
_register("lilith_routine", "list", PermissionLevel.READ_ONLY)
_register("lilith_routine", "get", PermissionLevel.READ_ONLY)
_register("lilith_routine", "history", PermissionLevel.READ_ONLY)
_register("lilith_routine", "create", PermissionLevel.CONFIRM_REQUIRED)
_register("lilith_routine", "update", PermissionLevel.CONFIRM_REQUIRED)
_register("lilith_routine", "enable", PermissionLevel.CONFIRM_REQUIRED)
_register("lilith_routine", "disable", PermissionLevel.CONFIRM_REQUIRED)
_register("lilith_routine", "delete", PermissionLevel.CONFIRM_REQUIRED)


def check_permission(tool: str, action: str = "*") -> PermissionRule:
    """Look up permission for a tool+action pair.

    Checks exact match first, then tool+wildcard, then defaults to DENIED.
    """
    key = (tool, action)
    if key in _PERMISSION_RULES:
        return _PERMISSION_RULES[key]
    wildcard = (tool, "*")
    if wildcard in _PERMISSION_RULES:
        return _PERMISSION_RULES[wildcard]
    return PermissionRule(tool, action, PermissionLevel.DENIED, "No permission rule found")


def requires_confirmation(tool: str, action: str = "*") -> bool:
    """Quick check: does this tool+action need user confirmation?"""
    return check_permission(tool, action).level == PermissionLevel.CONFIRM_REQUIRED


def is_denied(tool: str, action: str = "*") -> bool:
    """Quick check: is this tool+action denied?"""
    return check_permission(tool, action).level == PermissionLevel.DENIED


def get_all_rules() -> list[PermissionRule]:
    """Return all registered permission rules for catalog/audit."""
    return sorted(_PERMISSION_RULES.values(), key=lambda r: (r.tool, r.action))
