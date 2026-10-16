"""Local Skills Framework — reusable, reviewable, version-controlled procedures.

A Skill is a structured workflow that executes through normal JARVIS authority.
Skills cannot call sensitive handlers directly — every tool request goes through
existing JARVIS guards.

No community skills. No remote installation. No downloaded instructions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.green.capabilities import CapabilityError, validate_capabilities

logger = logging.getLogger("jarvis.green.skills")


class SkillStepType(Enum):
    TOOL_CALL = "tool_call"
    CONDITION = "condition"
    OUTPUT = "output"


@dataclass
class SkillStep:
    """A single step in a skill workflow."""

    step_type: SkillStepType
    tool_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    condition: str | None = None
    output_template: str | None = None


@dataclass
class SkillDefinition:
    """Complete definition of a local JARVIS skill."""

    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    parameters: dict[str, Any] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    steps: list[SkillStep] = field(default_factory=list)
    output_contract: dict[str, Any] = field(default_factory=dict)


class SkillValidationError(Exception):
    pass


class SkillValidator:
    """Validates skill definitions against known tools and capabilities."""

    def __init__(
        self,
        known_tools: set[str] | None = None,
    ) -> None:
        self._known_tools = known_tools or set()

    def validate(self, skill: SkillDefinition) -> list[str]:
        """Validate a skill and return list of errors (empty = valid)."""
        errors = []

        if not skill.id:
            errors.append("missing skill id")
        if not skill.name:
            errors.append("missing skill name")
        if not skill.version:
            errors.append("missing version")

        try:
            validate_capabilities(skill.required_capabilities)
        except CapabilityError as exc:
            errors.append(f"invalid capability: {exc}")

        if self._known_tools:
            for tool in skill.allowed_tools:
                if tool not in self._known_tools:
                    errors.append(f"unknown allowed tool: {tool!r}")

            for step in skill.steps:
                if step.step_type == SkillStepType.TOOL_CALL and step.tool_name:
                    if step.tool_name not in skill.allowed_tools:
                        errors.append(
                            f"step uses tool {step.tool_name!r} not in allowed_tools"
                        )

        for step in skill.steps:
            if step.step_type == SkillStepType.TOOL_CALL and not step.tool_name:
                errors.append("tool_call step missing tool_name")

        return errors


class SkillRegistry:
    """Manages local skill definitions."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition, validator: SkillValidator | None = None) -> list[str]:
        """Register a skill. Returns validation errors if any."""
        if skill.id in self._skills:
            return [f"duplicate skill id: {skill.id!r}"]

        if validator:
            errors = validator.validate(skill)
            if errors:
                return errors

        self._skills[skill.id] = skill
        logger.debug("registered skill: %s v%s", skill.name, skill.version)
        return []

    def get(self, skill_id: str) -> SkillDefinition | None:
        return self._skills.get(skill_id)

    def list(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def remove(self, skill_id: str) -> bool:
        return self._skills.pop(skill_id, None) is not None

    def contains(self, skill_id: str) -> bool:
        return skill_id in self._skills


class SkillRunner:
    """Executes skills through normal JARVIS tool authority.

    The runner does NOT call tool handlers directly. It produces
    a list of tool requests that the JARVIS execution path should
    process through its existing authority guards.
    """

    def run(self, skill: SkillDefinition, inputs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Produce tool requests for each step. Does not execute them."""
        requests = []
        for step in skill.steps:
            if step.step_type == SkillStepType.TOOL_CALL and step.tool_name:
                params = dict(step.parameters)
                if inputs:
                    for k, v in params.items():
                        if isinstance(v, str) and v.startswith("$input."):
                            input_key = v[7:]
                            if input_key in inputs:
                                params[k] = inputs[input_key]
                requests.append({
                    "tool": step.tool_name,
                    "parameters": params,
                    "description": step.description,
                })
            elif step.step_type == SkillStepType.OUTPUT:
                requests.append({
                    "output": step.output_template or "",
                    "description": step.description,
                })
        return requests


# ── Reference safe skills ──────────────────────────────────────────

def create_inspect_project_skill() -> SkillDefinition:
    """Safe read-only skill: inspect project structure."""
    return SkillDefinition(
        id="inspect_project_read_only",
        name="Inspect Project (Read-Only)",
        description="Lists project files and reads key documentation without making changes.",
        version="1.0",
        required_capabilities=["filesystem.read"],
        allowed_tools=["file_controller"],
        steps=[
            SkillStep(
                step_type=SkillStepType.TOOL_CALL,
                tool_name="file_controller",
                parameters={"action": "list_files", "path": "$input.project_path"},
                description="List project directory contents",
            ),
            SkillStep(
                step_type=SkillStepType.OUTPUT,
                output_template="Project structure listed for {project_path}",
                description="Report results",
            ),
        ],
    )


def create_diagnostics_skill() -> SkillDefinition:
    """Safe skill: summarize system diagnostics."""
    return SkillDefinition(
        id="summarize_diagnostics",
        name="Summarize Diagnostics",
        description="Collects read-only system information for troubleshooting.",
        version="1.0",
        required_capabilities=["system.read"],
        allowed_tools=["computer_settings"],
        steps=[
            SkillStep(
                step_type=SkillStepType.TOOL_CALL,
                tool_name="computer_settings",
                parameters={"action": "system_info"},
                description="Get system information",
            ),
            SkillStep(
                step_type=SkillStepType.OUTPUT,
                output_template="Diagnostics collected",
                description="Report diagnostics",
            ),
        ],
    )
