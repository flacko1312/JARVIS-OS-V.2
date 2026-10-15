"""AUT-05 project containment, Git and explicit screen-fix approval tests."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import code_helper, dev_agent
from core.dev_workspace import contained_path, git_operation


class ProjectContainmentTests(unittest.TestCase):
    def test_relative_path_stays_inside_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(contained_path(root, "src/main.py"), root.resolve() / "src" / "main.py")

    def test_parent_and_absolute_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ("../escape.py", str(root.parent / "outside.py")):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "escapes"):
                    contained_path(root, value)

    def test_import_error_is_not_misclassified_as_missing_dependency(self):
        self.assertEqual(
            dev_agent._classify_error("ImportError: cannot import name 'thing' from 'pkg'"),
            "import_error",
        )
        self.assertEqual(dev_agent._classify_error("ModuleNotFoundError: No module named 'pkg'"), "dependency_error")


class ScreenFixApprovalTests(unittest.TestCase):
    def setUp(self):
        code_helper._PENDING_SCREEN_FIXES.clear()

    def test_explicit_token_applies_unchanged_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            original = "value = 1\n"
            path.write_text(original, encoding="utf-8")
            code_helper._PENDING_SCREEN_FIXES["fix_test"] = {
                "path": str(path),
                "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "fixed_code": "value = 2\n",
                "created_at": time.monotonic(),
                "proposal_path": "unused.patch",
            }
            result = code_helper._apply_screen_fix("fix_test")
            self.assertIn("applied", result)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("value = 2\n"))

    def test_changed_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            original = "value = 1\n"
            path.write_text("owner change\n", encoding="utf-8")
            code_helper._PENDING_SCREEN_FIXES["fix_test"] = {
                "path": str(path),
                "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "fixed_code": "value = 2\n",
                "created_at": time.monotonic(),
                "proposal_path": "unused.patch",
            }
            result = code_helper._apply_screen_fix("fix_test")
            self.assertIn("changed after analysis", result)
            self.assertEqual(path.read_text(encoding="utf-8"), "owner change\n")

    def test_invalid_and_expired_tokens_never_write(self):
        self.assertIn("Invalid", code_helper._apply_screen_fix("missing"))


class DisposableGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "jarvis-test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "JARVIS Test"], cwd=self.root, check=True)
        (self.root / "tracked.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "initial"], cwd=self.root, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_status_diff_and_branch_are_read_only(self):
        (self.root / "tracked.txt").write_text("two\n", encoding="utf-8")
        self.assertIn("tracked.txt", git_operation(self.root, "status"))
        self.assertIn("-one", git_operation(self.root, "diff"))
        self.assertTrue(git_operation(self.root, "branch"))

    def test_branch_creation_is_local_and_validated(self):
        result = git_operation(self.root, "create_branch", branch="jarvis/safe-test")
        self.assertNotIn("failed", result.lower())
        self.assertEqual(git_operation(self.root, "branch"), "jarvis/safe-test")
        self.assertIn("Invalid", git_operation(self.root, "create_branch", branch="../escape"))

    def test_commit_never_stages_unrelated_files(self):
        (self.root / "tracked.txt").write_text("staged\n", encoding="utf-8")
        (self.root / "unrelated.txt").write_text("untracked\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        result = git_operation(self.root, "commit", message="safe local commit")
        self.assertNotIn("failed", result.lower())
        status = git_operation(self.root, "status")
        self.assertIn("unrelated.txt", status)


if __name__ == "__main__":
    unittest.main()
