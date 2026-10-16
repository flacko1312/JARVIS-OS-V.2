"""Tests for Skills Runtime — Phase 7 of GREEN runtime integration."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from core.green.skills import SkillDefinition, SkillStep, SkillStepType
from core.green.skills_runtime import (
    list_skills,
    get_skill,
    preview_skill_execution,
    register_skill,
    reset_registry,
)

_FLAG = "core.green.skills_runtime.SKILLS_RUNTIME_ENABLED"


class TestDisabledIsNoop(unittest.TestCase):
    @patch(_FLAG, False)
    def test_list_skills_disabled(self):
        assert list_skills() == []

    @patch(_FLAG, False)
    def test_get_skill_disabled(self):
        assert get_skill("inspect_project_read_only") is None

    @patch(_FLAG, False)
    def test_preview_disabled(self):
        assert preview_skill_execution("inspect_project_read_only") == []

    @patch(_FLAG, False)
    def test_register_disabled(self):
        skill = SkillDefinition(id="test", name="Test")
        errors = register_skill(skill)
        assert "disabled" in errors[0]


class TestBuiltInSkills(unittest.TestCase):
    def setUp(self):
        reset_registry()

    @patch(_FLAG, True)
    def test_list_builtin_skills(self):
        skills = list_skills()
        assert len(skills) >= 2
        ids = [s["id"] for s in skills]
        assert "inspect_project_read_only" in ids
        assert "summarize_diagnostics" in ids

    @patch(_FLAG, True)
    def test_get_inspect_project(self):
        skill = get_skill("inspect_project_read_only")
        assert skill is not None
        assert skill["name"] == "Inspect Project (Read-Only)"
        assert "filesystem.read" in skill["required_capabilities"]
        assert skill["step_count"] == 2

    @patch(_FLAG, True)
    def test_get_diagnostics(self):
        skill = get_skill("summarize_diagnostics")
        assert skill is not None
        assert "system.read" in skill["required_capabilities"]

    @patch(_FLAG, True)
    def test_get_nonexistent(self):
        assert get_skill("nonexistent") is None


class TestSkillPreview(unittest.TestCase):
    def setUp(self):
        reset_registry()

    @patch(_FLAG, True)
    def test_preview_inspect_project(self):
        requests = preview_skill_execution(
            "inspect_project_read_only",
            inputs={"project_path": "/home/user/project"},
        )
        assert len(requests) == 2
        assert requests[0]["tool"] == "file_controller"
        assert requests[0]["parameters"]["path"] == "/home/user/project"

    @patch(_FLAG, True)
    def test_preview_diagnostics(self):
        requests = preview_skill_execution("summarize_diagnostics")
        assert len(requests) == 2
        assert requests[0]["tool"] == "computer_settings"

    @patch(_FLAG, True)
    def test_preview_nonexistent(self):
        assert preview_skill_execution("nonexistent") == []


class TestSkillRegistration(unittest.TestCase):
    def setUp(self):
        reset_registry()

    @patch(_FLAG, True)
    def test_register_valid_skill(self):
        skill = SkillDefinition(
            id="custom_read",
            name="Custom Read",
            version="1.0",
            required_capabilities=["filesystem.read"],
            allowed_tools=["file_controller"],
            steps=[
                SkillStep(
                    step_type=SkillStepType.TOOL_CALL,
                    tool_name="file_controller",
                    parameters={"action": "read", "path": "/tmp/test"},
                ),
            ],
        )
        errors = register_skill(skill)
        assert errors == []
        assert get_skill("custom_read") is not None

    @patch(_FLAG, True)
    def test_register_duplicate_fails(self):
        skill = SkillDefinition(id="inspect_project_read_only", name="Dup")
        errors = register_skill(skill)
        assert len(errors) > 0
        assert "duplicate" in errors[0]

    @patch(_FLAG, True)
    def test_register_with_known_tools_validation(self):
        skill = SkillDefinition(
            id="bad_skill",
            name="Bad",
            version="1.0",
            allowed_tools=["nonexistent_tool"],
        )
        errors = register_skill(skill, known_tools={"file_controller", "web_search"})
        assert len(errors) > 0
        assert "unknown" in errors[0]


class TestNoExecution(unittest.TestCase):
    def setUp(self):
        reset_registry()

    @patch(_FLAG, True)
    def test_preview_produces_requests_not_results(self):
        requests = preview_skill_execution("inspect_project_read_only", {"project_path": "."})
        for req in requests:
            assert "result" not in req
            assert "error" not in req

    @patch(_FLAG, True)
    def test_list_is_read_only(self):
        skills_before = list_skills()
        list_skills()  # second call
        skills_after = list_skills()
        assert len(skills_before) == len(skills_after)


if __name__ == "__main__":
    unittest.main()
