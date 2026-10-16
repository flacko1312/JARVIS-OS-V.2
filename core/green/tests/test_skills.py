"""Tests for Skills Framework — Phase 8 of GREEN Foundation."""
from __future__ import annotations

import unittest

from core.green.skills import (
    SkillDefinition,
    SkillRegistry,
    SkillRunner,
    SkillStep,
    SkillStepType,
    SkillValidationError,
    SkillValidator,
    create_diagnostics_skill,
    create_inspect_project_skill,
)


class TestSkillValidator(unittest.TestCase):
    def setUp(self):
        self.validator = SkillValidator(known_tools={"file_controller", "computer_settings"})

    def test_valid_skill(self):
        skill = create_inspect_project_skill()
        errors = self.validator.validate(skill)
        assert errors == []

    def test_missing_id(self):
        skill = SkillDefinition(id="", name="test")
        errors = self.validator.validate(skill)
        assert any("missing skill id" in e for e in errors)

    def test_missing_name(self):
        skill = SkillDefinition(id="x", name="")
        errors = self.validator.validate(skill)
        assert any("missing skill name" in e for e in errors)

    def test_missing_version(self):
        skill = SkillDefinition(id="x", name="test", version="")
        errors = self.validator.validate(skill)
        assert any("missing version" in e for e in errors)

    def test_invalid_capability(self):
        skill = SkillDefinition(
            id="x", name="test",
            required_capabilities=["flying.unicorn"],
        )
        errors = self.validator.validate(skill)
        assert any("invalid capability" in e for e in errors)

    def test_unknown_allowed_tool(self):
        skill = SkillDefinition(
            id="x", name="test",
            allowed_tools=["nonexistent_tool"],
        )
        errors = self.validator.validate(skill)
        assert any("unknown allowed tool" in e for e in errors)

    def test_step_tool_not_in_allowed(self):
        skill = SkillDefinition(
            id="x", name="test",
            allowed_tools=["file_controller"],
            steps=[
                SkillStep(step_type=SkillStepType.TOOL_CALL, tool_name="computer_settings"),
            ],
        )
        errors = self.validator.validate(skill)
        assert any("not in allowed_tools" in e for e in errors)

    def test_tool_call_missing_tool_name(self):
        skill = SkillDefinition(
            id="x", name="test",
            steps=[SkillStep(step_type=SkillStepType.TOOL_CALL)],
        )
        errors = self.validator.validate(skill)
        assert any("missing tool_name" in e for e in errors)

    def test_no_known_tools_skips_tool_checks(self):
        validator = SkillValidator()
        skill = SkillDefinition(
            id="x", name="test",
            allowed_tools=["anything"],
        )
        errors = validator.validate(skill)
        assert errors == []


class TestSkillRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = SkillRegistry()

    def test_register_and_get(self):
        skill = create_inspect_project_skill()
        errors = self.registry.register(skill)
        assert errors == []
        assert self.registry.get(skill.id) is skill

    def test_duplicate_id(self):
        skill = create_inspect_project_skill()
        self.registry.register(skill)
        errors = self.registry.register(skill)
        assert any("duplicate" in e for e in errors)

    def test_register_with_validator(self):
        validator = SkillValidator(known_tools={"file_controller"})
        skill = create_inspect_project_skill()
        errors = self.registry.register(skill, validator)
        assert errors == []

    def test_register_with_validation_errors(self):
        validator = SkillValidator(known_tools=set())
        skill = SkillDefinition(id="", name="")
        errors = self.registry.register(skill, validator)
        assert len(errors) > 0
        assert not self.registry.contains("")

    def test_list(self):
        self.registry.register(create_inspect_project_skill())
        self.registry.register(create_diagnostics_skill())
        assert len(self.registry.list()) == 2

    def test_remove(self):
        skill = create_inspect_project_skill()
        self.registry.register(skill)
        assert self.registry.remove(skill.id)
        assert not self.registry.contains(skill.id)

    def test_contains(self):
        assert not self.registry.contains("nope")
        self.registry.register(create_inspect_project_skill())
        assert self.registry.contains("inspect_project_read_only")


class TestSkillRunner(unittest.TestCase):
    def test_produces_tool_requests(self):
        runner = SkillRunner()
        skill = create_inspect_project_skill()
        requests = runner.run(skill, inputs={"project_path": "C:\\JARVIS"})
        assert len(requests) == 2
        assert requests[0]["tool"] == "file_controller"
        assert requests[0]["parameters"]["path"] == "C:\\JARVIS"

    def test_output_step(self):
        runner = SkillRunner()
        skill = create_inspect_project_skill()
        requests = runner.run(skill)
        output_reqs = [r for r in requests if "output" in r]
        assert len(output_reqs) == 1

    def test_no_direct_execution(self):
        runner = SkillRunner()
        skill = create_inspect_project_skill()
        requests = runner.run(skill)
        # Runner produces requests, it does NOT call handlers
        for req in requests:
            assert "result" not in req


class TestReferenceSkills(unittest.TestCase):
    def test_inspect_project(self):
        skill = create_inspect_project_skill()
        assert skill.id == "inspect_project_read_only"
        assert "filesystem.read" in skill.required_capabilities

    def test_diagnostics(self):
        skill = create_diagnostics_skill()
        assert skill.id == "summarize_diagnostics"
        assert "system.read" in skill.required_capabilities


if __name__ == "__main__":
    unittest.main()
