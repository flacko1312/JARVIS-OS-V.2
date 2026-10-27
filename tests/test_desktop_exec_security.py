"""Security tests for desktop.py exec() sandbox and AST validator (TD-012).

Every test in AllowedOperations must PASS (functionality preserved).
Every test in BlockedOperations must be REJECTED (security enforced).
"""

import pytest

from actions.desktop import validate_generated_code, _build_sandbox, _execute_generated_code


# ── Allowed operations ─────────────────────────────────────────────

class TestAllowedOperations:
    """Operations the LLM legitimately needs — must keep working."""

    def test_simple_print(self):
        ok, _ = validate_generated_code('print("hello")')
        assert ok

    def test_path_operations(self):
        ok, _ = validate_generated_code('p = Path("C:/Users"); print(p.exists())')
        assert ok

    def test_list_comprehension(self):
        ok, _ = validate_generated_code('files = [f for f in Path(".").iterdir() if f.is_file()]')
        assert ok

    def test_for_loop(self):
        ok, _ = validate_generated_code('for i in range(5):\n    print(i)')
        assert ok

    def test_if_else(self):
        ok, _ = validate_generated_code('x = 1\nif x > 0:\n    print("yes")\nelse:\n    print("no")')
        assert ok

    def test_function_def(self):
        ok, _ = validate_generated_code('def greet(name):\n    return f"Hello {name}"\nprint(greet("user"))')
        assert ok

    def test_string_formatting(self):
        ok, _ = validate_generated_code('name = "test"\nprint(f"File: {name}")')
        assert ok

    def test_shutil_copy(self):
        ok, _ = validate_generated_code('shutil.copy2("a.txt", "b.txt")')
        assert ok

    def test_sorted_with_key(self):
        ok, _ = validate_generated_code('items = sorted([3,1,2])\nprint(items)')
        assert ok

    def test_try_except(self):
        ok, _ = validate_generated_code('try:\n    x = 1/0\nexcept Exception as e:\n    print(e)')
        assert ok

    def test_path_suffix_access(self):
        ok, _ = validate_generated_code('p = Path("test.txt")\nprint(p.suffix)')
        assert ok

    def test_os_path_functions(self):
        ok, _ = validate_generated_code('print(os_path_join("a", "b"))')
        assert ok

    def test_hasattr(self):
        ok, _ = validate_generated_code('print(hasattr(Path("."), "exists"))')
        assert ok

    def test_execution_produces_output(self):
        result = _execute_generated_code('print("hello world")')
        assert result == "hello world"

    def test_execution_path_listing(self):
        result = _execute_generated_code('print(len([f for f in Path(".").iterdir()]))')
        assert result.strip().isdigit()


# ── Blocked operations ─────────────────────────────────────────────

class TestBlockedImports:
    def test_import_os(self):
        ok, reason = validate_generated_code("import os")
        assert not ok
        assert "Import" in reason

    def test_import_subprocess(self):
        ok, reason = validate_generated_code("import subprocess")
        assert not ok

    def test_from_os_import(self):
        ok, reason = validate_generated_code("from os import system")
        assert not ok

    def test_import_sys(self):
        ok, reason = validate_generated_code("import sys")
        assert not ok

    def test_import_ctypes(self):
        ok, reason = validate_generated_code("import ctypes")
        assert not ok


class TestBlockedBuiltins:
    def test_eval(self):
        ok, _ = validate_generated_code('eval("1+1")')
        assert not ok

    def test_exec(self):
        ok, _ = validate_generated_code('exec("print(1)")')
        assert not ok

    def test_compile(self):
        ok, _ = validate_generated_code('compile("1", "", "eval")')
        assert not ok

    def test_open(self):
        ok, _ = validate_generated_code('open("/etc/passwd")')
        assert not ok

    def test_dunder_import(self):
        ok, _ = validate_generated_code('__import__("os")')
        assert not ok

    def test_globals(self):
        ok, _ = validate_generated_code('globals()')
        assert not ok

    def test_locals(self):
        ok, _ = validate_generated_code('locals()')
        assert not ok

    def test_getattr(self):
        ok, _ = validate_generated_code('getattr(Path, "cwd")')
        assert not ok

    def test_setattr(self):
        ok, _ = validate_generated_code('setattr(Path, "x", 1)')
        assert not ok

    def test_delattr(self):
        ok, _ = validate_generated_code('delattr(Path, "x")')
        assert not ok

    def test_type(self):
        ok, _ = validate_generated_code('type(Path)')
        assert not ok

    def test_super(self):
        ok, _ = validate_generated_code('super()')
        assert not ok

    def test_vars(self):
        ok, _ = validate_generated_code('vars(Path)')
        assert not ok

    def test_dir(self):
        ok, _ = validate_generated_code('dir(Path)')
        assert not ok

    def test_breakpoint(self):
        ok, _ = validate_generated_code('breakpoint()')
        assert not ok

    def test_input(self):
        ok, _ = validate_generated_code('input("password: ")')
        assert not ok


class TestBlockedDunderAccess:
    def test_class(self):
        ok, _ = validate_generated_code('x = "".__class__')
        assert not ok

    def test_mro(self):
        ok, _ = validate_generated_code('x = str.__mro__')
        assert not ok

    def test_subclasses(self):
        ok, _ = validate_generated_code('x = object.__subclasses__()')
        assert not ok

    def test_globals_attr(self):
        ok, _ = validate_generated_code('x = print.__globals__')
        assert not ok

    def test_builtins_attr(self):
        ok, _ = validate_generated_code('x = print.__builtins__')
        assert not ok

    def test_init(self):
        ok, _ = validate_generated_code('x = str.__init__')
        assert not ok

    def test_dict_attr(self):
        ok, _ = validate_generated_code('x = str.__dict__')
        assert not ok

    def test_private_attr(self):
        ok, _ = validate_generated_code('x = Path(".")._accessor')
        assert not ok


class TestBlockedEscapeVectors:
    """Adversarial patterns that try to escape the sandbox."""

    def test_string_dunder_class(self):
        ok, _ = validate_generated_code("x = ''.__class__.__mro__[1].__subclasses__()")
        assert not ok

    def test_getattr_dunder_via_string(self):
        ok, _ = validate_generated_code('x = getattr(str, "__mro__")')
        assert not ok

    def test_dunder_in_string_with_getattr(self):
        ok, _ = validate_generated_code('s = "__class__"\nx = getattr(str, s)')
        assert not ok  # getattr is in _BANNED_NAMES

    def test_class_from_string_format(self):
        ok, _ = validate_generated_code('f"{[].__class__}"')
        assert not ok

    def test_subprocess_via_import(self):
        ok, _ = validate_generated_code('import subprocess; subprocess.run(["ls"])')
        assert not ok

    def test_os_system(self):
        ok, _ = validate_generated_code('import os; os.system("rm -rf /")')
        assert not ok

    def test_nested_exec(self):
        ok, _ = validate_generated_code('exec("import os")')
        assert not ok

    def test_eval_import(self):
        ok, _ = validate_generated_code('eval("__import__(\'os\')")')
        assert not ok

    def test_lambda_with_banned(self):
        ok, _ = validate_generated_code('f = lambda: eval("1")')
        assert not ok

    def test_walrus_with_exec(self):
        code = 'if (x := exec("import os")): pass'
        ok, _ = validate_generated_code(code)
        assert not ok

    def test_class_definition(self):
        ok, reason = validate_generated_code('class Evil:\n    pass')
        assert not ok
        assert "ClassDef" in reason

    def test_async_code(self):
        ok, _ = validate_generated_code('async def f(): pass')
        assert not ok

    def test_global_statement(self):
        ok, _ = validate_generated_code('global x')
        assert not ok

    def test_nonlocal_statement(self):
        ok, _ = validate_generated_code('def f():\n    x = 1\n    def g():\n        nonlocal x')
        assert not ok

    def test_delete_statement(self):
        ok, _ = validate_generated_code('del x')
        assert not ok


class TestBlockedFilesystem:
    def test_path_rmtree(self):
        ok, reason = validate_generated_code('shutil.rmtree("/important")')
        assert not ok
        assert "rmtree" in reason

    def test_path_write_text(self):
        """write_text is now blocked at the AST level."""
        ok, reason = validate_generated_code('Path("evil.txt").write_text("pwned")')
        assert not ok
        assert "write_text" in reason

    def test_path_unlink_ast(self):
        ok, reason = validate_generated_code('Path("important.txt").unlink()')
        assert not ok
        assert "unlink" in reason

    def test_os_system_method(self):
        ok, reason = validate_generated_code('os.system("rm -rf /")')
        assert not ok


class TestBlockedRuntimeSandbox:
    """Verify the runtime sandbox doesn't expose dangerous objects."""

    def test_ctypes_not_in_sandbox(self):
        sandbox = _build_sandbox()
        assert "ctypes" not in sandbox

    def test_os_not_in_sandbox(self):
        sandbox = _build_sandbox()
        assert "os" not in sandbox
        assert "os_path" not in sandbox

    def test_getattr_not_in_builtins(self):
        sandbox = _build_sandbox()
        assert "getattr" not in sandbox["__builtins__"]

    def test_setattr_not_in_builtins(self):
        sandbox = _build_sandbox()
        assert "setattr" not in sandbox["__builtins__"]

    def test_eval_not_in_builtins(self):
        sandbox = _build_sandbox()
        assert "eval" not in sandbox["__builtins__"]

    def test_exec_not_in_builtins(self):
        sandbox = _build_sandbox()
        assert "exec" not in sandbox["__builtins__"]

    def test_open_not_in_builtins(self):
        sandbox = _build_sandbox()
        assert "open" not in sandbox["__builtins__"]

    def test_import_not_in_builtins(self):
        sandbox = _build_sandbox()
        assert "__import__" not in sandbox["__builtins__"]

    def test_os_path_individual_functions_present(self):
        sandbox = _build_sandbox()
        assert callable(sandbox.get("os_path_join"))
        assert callable(sandbox.get("os_path_exists"))

    def test_rejected_code_does_not_execute(self):
        result = _execute_generated_code("import os; os.system('echo pwned')")
        assert "rejected" in result.lower()

    def test_unsafe_keyword_returns_safe_message(self):
        result = _execute_generated_code("UNSAFE")
        assert "cannot be performed safely" in result.lower()
