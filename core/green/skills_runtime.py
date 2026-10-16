"""Skills Runtime — safe runtime integration of Skills framework into JARVIS.

Exposes read-only skill listing and validated skill instantiation through
JARVIS. Skills execute through normal JARVIS authority — the runtime bridge
never bypasses guards.

Feature flag: JARVIS_SKILLS_RUNTIME_ENABLED (default off).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from core.green.skills import (
    SkillDefinition,
    SkillRegistry,
    SkillRunner,
    SkillValidator,
    create_inspect_project_skill,
    create_diagnostics_skill,
)

logger = logging.getLogger("jarvis.green.skills_runtime")

SKILLS_RUNTIME_ENABLED = os.environ.get("JARVIS_SKILLS_RUNTIME_ENABLED", "0") == "1"

_registry: SkillRegistry | None = None
_runner: SkillRunner | None = None


def _ensure_initialized() -> tuple[SkillRegistry, SkillRunner]:
    """Lazy-init the singleton registry with built-in safe skills."""
    global _registry, _runner
    if _registry is None:
        _registry = SkillRegistry()
        _runner = SkillRunner()
        for factory in [create_inspect_project_skill, create_diagnostics_skill]:
            skill = factory()
            _registry.register(skill)
    return _registry, _runner


def list_skills() -> list[dict[str, Any]]:
    """List available skills (read-only summary). Returns empty if disabled."""
    if not SKILLS_RUNTIME_ENABLED:
        return []
    try:
        registry, _ = _ensure_initialized()
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "required_capabilities": s.required_capabilities,
                "allowed_tools": s.allowed_tools,
                "step_count": len(s.steps),
            }
            for s in registry.list()
        ]
    except Exception:
        logger.debug("list_skills failed — isolated", exc_info=True)
        return []


def get_skill(skill_id: str) -> dict[str, Any] | None:
    """Get details of a single skill. Returns None if disabled or not found."""
    if not SKILLS_RUNTIME_ENABLED:
        return None
    try:
        registry, _ = _ensure_initialized()
        skill = registry.get(skill_id)
        if skill is None:
            return None
        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "required_capabilities": skill.required_capabilities,
            "allowed_tools": skill.allowed_tools,
            "step_count": len(skill.steps),
            "parameters": skill.parameters,
        }
    except Exception:
        logger.debug("get_skill failed — isolated", exc_info=True)
        return None


def preview_skill_execution(
    skill_id: str,
    inputs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Preview what tool requests a skill would produce WITHOUT executing.

    Returns the list of tool request dicts. The actual execution goes through
    normal JARVIS _execute_tool dispatch — this just shows what would happen.
    """
    if not SKILLS_RUNTIME_ENABLED:
        return []
    try:
        registry, runner = _ensure_initialized()
        skill = registry.get(skill_id)
        if skill is None:
            return []
        return runner.run(skill, inputs)
    except Exception:
        logger.debug("preview_skill_execution failed — isolated", exc_info=True)
        return []


def register_skill(
    skill: SkillDefinition,
    known_tools: set[str] | None = None,
) -> list[str]:
    """Register a new skill with validation. Returns validation errors."""
    if not SKILLS_RUNTIME_ENABLED:
        return ["skills runtime disabled"]
    try:
        registry, _ = _ensure_initialized()
        validator = SkillValidator(known_tools=known_tools)
        return registry.register(skill, validator)
    except Exception as exc:
        logger.debug("register_skill failed — isolated", exc_info=True)
        return [str(exc)]


def reset_registry() -> None:
    """Reset the skills registry (for testing)."""
    global _registry, _runner
    _registry = None
    _runner = None
