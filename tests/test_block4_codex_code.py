"""Block 4 — Dev Agent (Codex) & Code Helper audit tests.

Covers: dev_agent.py (project scaffolding, plan→write→run→fix loop)
and code_helper.py (write/edit/explain/run/build/optimize/screen_debug).
API calls are mocked; only pure helpers and dispatch logic are tested.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# A — DEV AGENT helpers (actions/dev_agent.py)
# ---------------------------------------------------------------------------

class TestStripFences(unittest.TestCase):

    def test_python_fence(self):
        from actions.dev_agent import _strip_fences
        self.assertEqual(_strip_fences("```python\nprint('hi')\n```"), "print('hi')")

    def test_no_fence(self):
        from actions.dev_agent import _strip_fences
        self.assertEqual(_strip_fences("hello"), "hello")

    def test_generic_fence(self):
        from actions.dev_agent import _strip_fences
        self.assertEqual(_strip_fences("```\ncode\n```"), "code")

    def test_empty(self):
        from actions.dev_agent import _strip_fences
        self.assertEqual(_strip_fences(""), "")


class TestIsRateLimit(unittest.TestCase):

    def test_429(self):
        from actions.dev_agent import _is_rate_limit
        self.assertTrue(_is_rate_limit(Exception("HTTP 429 Too Many Requests")))

    def test_quota(self):
        from actions.dev_agent import _is_rate_limit
        self.assertTrue(_is_rate_limit(Exception("RESOURCE_EXHAUSTED")))

    def test_normal_error(self):
        from actions.dev_agent import _is_rate_limit
        self.assertFalse(_is_rate_limit(Exception("ValueError")))


class TestClassifyError(unittest.TestCase):

    def test_dependency(self):
        from actions.dev_agent import _classify_error
        self.assertEqual(_classify_error("ModuleNotFoundError: No module named 'flask'"), "dependency_error")

    def test_syntax(self):
        from actions.dev_agent import _classify_error
        self.assertEqual(_classify_error("SyntaxError: invalid syntax"), "syntax_error")

    def test_import(self):
        from actions.dev_agent import _classify_error
        self.assertEqual(_classify_error("ImportError: cannot import name 'foo'"), "import_error")

    def test_cannot_import_only(self):
        from actions.dev_agent import _classify_error
        self.assertEqual(_classify_error("cannot import name 'foo' from 'bar'"), "import_error")

    def test_runtime(self):
        from actions.dev_agent import _classify_error
        self.assertEqual(_classify_error("Traceback (most recent call last):\n  TypeError: ..."), "runtime_error")

    def test_none(self):
        from actions.dev_agent import _classify_error
        self.assertEqual(_classify_error("All tests passed"), "none")


class TestHasError(unittest.TestCase):

    def test_timeout_not_error(self):
        from actions.dev_agent import _has_error
        self.assertFalse(_has_error("Timed out after 30s", "python main.py"))

    def test_empty_not_error(self):
        from actions.dev_agent import _has_error
        self.assertFalse(_has_error("", "python main.py"))

    def test_traceback_is_error(self):
        from actions.dev_agent import _has_error
        self.assertTrue(_has_error("Traceback (most recent call last):\n  File ...", "python main.py"))


class TestParseTraceback(unittest.TestCase):

    def test_match_project_file(self):
        from actions.dev_agent import _parse_traceback
        output = 'File "main.py", line 42, in <module>\n    raise ValueError'
        f, line = _parse_traceback(output, ["main.py", "utils/helpers.py"])
        self.assertEqual(f, "main.py")
        self.assertEqual(line, 42)

    def test_no_match(self):
        from actions.dev_agent import _parse_traceback
        output = 'File "/usr/lib/python3/lib.py", line 10'
        f, line = _parse_traceback(output, ["main.py"])
        self.assertIsNone(f)
        self.assertIsNone(line)


class TestDevAgentEntry(unittest.TestCase):

    def test_missing_description(self):
        from actions.dev_agent import dev_agent
        result = dev_agent({})
        self.assertIn("describe", result.lower())

    @patch("actions.dev_agent._plan_project")
    def test_rate_limit_handled(self, mock_plan):
        from actions.dev_agent import dev_agent, RateLimitError
        mock_plan.side_effect = RateLimitError("429")
        result = dev_agent({"description": "build a thing"})
        self.assertIn("rate limit", result.lower())

    @patch("actions.dev_agent._plan_project")
    def test_plan_failure(self, mock_plan):
        from actions.dev_agent import dev_agent
        mock_plan.side_effect = ValueError("bad JSON")
        result = dev_agent({"description": "build a thing"})
        self.assertIn("failed", result.lower())


class TestTryAutoInstall(unittest.TestCase):

    def test_detects_missing_module(self):
        from actions.dev_agent import _try_auto_install
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _try_auto_install(
                "ModuleNotFoundError: No module named 'requests'",
                Path(tempfile.gettempdir()),
            )
        self.assertTrue(result)
        mock_run.assert_called_once()

    def test_no_match(self):
        from actions.dev_agent import _try_auto_install
        result = _try_auto_install("TypeError: ...", Path(tempfile.gettempdir()))
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# B — CODE HELPER helpers (actions/code_helper.py)
# ---------------------------------------------------------------------------

class TestCleanCode(unittest.TestCase):

    def test_python_fence(self):
        from actions.code_helper import _clean_code
        self.assertEqual(_clean_code("```python\nprint(1)\n```"), "print(1)")

    def test_no_fence(self):
        from actions.code_helper import _clean_code
        self.assertEqual(_clean_code("x = 1"), "x = 1")

    def test_empty(self):
        from actions.code_helper import _clean_code
        self.assertEqual(_clean_code(""), "")


class TestResolveSavePath(unittest.TestCase):

    def test_default_python(self):
        from actions.code_helper import _resolve_save_path
        p = _resolve_save_path("", "python")
        self.assertTrue(str(p).endswith(".py"))

    def test_explicit_path(self):
        from actions.code_helper import _resolve_save_path
        p = _resolve_save_path("my_script.js", "javascript")
        self.assertEqual(p.name, "my_script.js")

    def test_absolute_path(self):
        from actions.code_helper import _resolve_save_path
        p = _resolve_save_path("C:\\temp\\test.py", "python")
        self.assertEqual(str(p), "C:\\temp\\test.py")

    def test_language_extensions(self):
        from actions.code_helper import _resolve_save_path
        for lang, ext in [("javascript", ".js"), ("typescript", ".ts"),
                          ("rust", ".rs"), ("go", ".go"), ("html", ".html")]:
            p = _resolve_save_path("", lang)
            self.assertTrue(str(p).endswith(ext), f"{lang} should give {ext}")


class TestReadFile(unittest.TestCase):

    def test_no_path(self):
        from actions.code_helper import _read_file
        content, err = _read_file("")
        self.assertEqual(content, "")
        self.assertIn("No file", err)

    def test_missing_file(self):
        from actions.code_helper import _read_file
        content, err = _read_file("/nonexistent/file.py")
        self.assertEqual(content, "")
        self.assertIn("not found", err.lower())

    def test_valid_file(self):
        from actions.code_helper import _read_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("hello = 1")
            f.flush()
            content, err = _read_file(f.name)
        os.unlink(f.name)
        self.assertEqual(content, "hello = 1")
        self.assertEqual(err, "")


class TestPreview(unittest.TestCase):

    def test_short_code(self):
        from actions.code_helper import _preview
        self.assertEqual(_preview("a\nb\nc", lines=5), "a\nb\nc")

    def test_long_code(self):
        from actions.code_helper import _preview
        code = "\n".join(str(i) for i in range(100))
        result = _preview(code, lines=3)
        self.assertIn("0\n1\n2", result)
        self.assertIn("more lines", result)


class TestHasErrorCodeHelper(unittest.TestCase):

    def test_error_detected(self):
        from actions.code_helper import _has_error
        self.assertTrue(_has_error("SyntaxError: unexpected EOF"))

    def test_clean_output(self):
        from actions.code_helper import _has_error
        self.assertFalse(_has_error("Hello World"))


class TestDetectIntent(unittest.TestCase):

    def test_screen_debug(self):
        from actions.code_helper import _detect_intent
        self.assertEqual(_detect_intent("what's wrong on the screen", "", ""), "screen_debug")

    def test_optimize(self):
        from actions.code_helper import _detect_intent
        self.assertEqual(_detect_intent("optimize this code", "", "x = 1"), "optimize")

    def test_explain_keyword(self):
        from actions.code_helper import _detect_intent
        self.assertEqual(_detect_intent("explain what this does", "", "code"), "explain")

    def test_write_default(self):
        from actions.code_helper import _detect_intent
        self.assertEqual(_detect_intent("make a calculator", "", ""), "write")

    def test_build_keyword(self):
        from actions.code_helper import _detect_intent
        self.assertEqual(_detect_intent("build a web scraper", "", ""), "build")

    def test_edit_existing_file(self):
        from actions.code_helper import _detect_intent
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"x = 1")
        try:
            self.assertEqual(_detect_intent("edit the function", f.name, ""), "edit")
        finally:
            os.unlink(f.name)

    def test_run_existing_file(self):
        from actions.code_helper import _detect_intent
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"print(1)")
        try:
            self.assertEqual(_detect_intent("run this script", f.name, ""), "run")
        finally:
            os.unlink(f.name)


class TestCodeHelperDispatch(unittest.TestCase):

    def test_unknown_action(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "nonexistent"})
        self.assertIn("Unknown action", result)

    def test_write_no_description(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "write"})
        self.assertIn("describe", result.lower())

    def test_edit_no_file(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "edit", "description": "fix it"})
        self.assertIn("file path", result.lower())

    def test_edit_no_instruction(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "edit", "file_path": "test.py"})
        self.assertIn("describe", result.lower())

    def test_explain_no_input(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "explain"})
        self.assertIn("provide", result.lower())

    def test_run_no_file(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "run"})
        self.assertIn("file path", result.lower())

    def test_run_missing_file(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "run", "file_path": "/nonexistent.py"})
        self.assertIn("not found", result.lower())

    def test_build_no_description(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "build"})
        self.assertIn("describe", result.lower())

    def test_optimize_no_input(self):
        from actions.code_helper import code_helper
        result = code_helper({"action": "optimize"})
        self.assertIn("provide", result.lower())


class TestRunFile(unittest.TestCase):

    def test_unsupported_extension(self):
        from actions.code_helper import _run_file
        result = _run_file(Path("test.xyz"), [], 10)
        self.assertIn("No interpreter", result)

    def test_python_run(self):
        from actions.code_helper import _run_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("print('hello from test')")
            f.flush()
        try:
            result = _run_file(Path(f.name), [], 10)
            self.assertIn("hello from test", result)
        finally:
            os.unlink(f.name)

    def test_timeout(self):
        from actions.code_helper import _run_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("import time; time.sleep(60)")
            f.flush()
        try:
            result = _run_file(Path(f.name), [], 2)
            self.assertIn("Timed out", result)
        finally:
            os.unlink(f.name)


class TestRunProject(unittest.TestCase):

    def test_timeout_not_error(self):
        from actions.dev_agent import _run_project
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "slow.py"
            script.write_text("import time; time.sleep(60)", encoding="utf-8")
            result = _run_project(f"python {script.name}", Path(d), timeout=2)
        self.assertIn("Timed out", result)

    def test_command_not_found(self):
        from actions.dev_agent import _run_project
        with tempfile.TemporaryDirectory() as d:
            result = _run_project("nonexistent_binary_xyz", Path(d), timeout=5)
        self.assertIn("not found", result.lower())


class TestInstallDependencies(unittest.TestCase):

    def test_no_dependencies(self):
        from actions.dev_agent import _install_dependencies
        result = _install_dependencies([], Path(tempfile.gettempdir()))
        self.assertIn("No external", result)

    def test_already_installed(self):
        from actions.dev_agent import _install_dependencies
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = _install_dependencies(["json"], Path(tempfile.gettempdir()))
        self.assertIn("already installed", result.lower())


class TestOpenVSCode(unittest.TestCase):

    @patch("subprocess.Popen", side_effect=FileNotFoundError)
    def test_all_candidates_fail(self, mock_popen):
        from actions.dev_agent import _open_vscode
        result = _open_vscode(Path(tempfile.gettempdir()))
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# C — SCREEN DEBUG (code_helper._screen_debug_action) — requires physical
# ---------------------------------------------------------------------------

class TestScreenDebugPhysical(unittest.TestCase):

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real screen + Gemini API")
    def test_screen_analysis(self):
        pass


# ---------------------------------------------------------------------------
# D — DEV AGENT full pipeline — requires Gemini API
# ---------------------------------------------------------------------------

class TestDevAgentPhysical(unittest.TestCase):

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real Gemini API")
    def test_full_build(self):
        pass

    @unittest.skip("PHYSICAL TEST REQUIRED — needs real Gemini API")
    def test_fix_loop(self):
        pass


if __name__ == "__main__":
    unittest.main()
