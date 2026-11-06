"""JARVIS tool dispatch contract, verified without importing audio or running services.

The test checks whether names advertised to Gemini have a matching static
dispatch branch. It does NOT claim the tool works in production.
"""
import ast
from pathlib import Path


def _assigned(tree: ast.AST, identifier: str):
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == identifier for t in targets):
                return node.value
    return None


def _literal_names(container: ast.AST) -> set[str]:
    return {
        node.value for node in ast.walk(container)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _declared_tools(tree: ast.AST) -> set[str]:
    headless = _assigned(tree, "HEADLESS_ACTIONS")
    if headless is not None:
        return _literal_names(headless)
    declarations = _assigned(tree, "TOOL_DECLARATIONS")
    assert isinstance(declarations, ast.List), "Missing Gemini tool declarations"
    return {
        v.value
        for declaration in declarations.elts if isinstance(declaration, ast.Dict)
        for k, v in zip(declaration.keys, declaration.values)
        if isinstance(k, ast.Constant) and k.value == "name"
        and isinstance(v, ast.Constant) and isinstance(v.value, str)
    }


def _routed_tools(tree: ast.AST) -> set[str]:
    jarvis = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "JarvisLive"
    )
    dispatch = next(
        node for node in jarvis.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_execute_tool"
    )
    routed = set()
    for node in ast.walk(dispatch):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name):
            continue
        if node.left.id != "name":
            continue
        for operator, right in zip(node.ops, node.comparators):
            if isinstance(operator, (ast.Eq, ast.In)):
                if isinstance(right, ast.Constant) and isinstance(right.value, str):
                    routed.add(right.value)
                elif isinstance(right, (ast.Set, ast.Tuple, ast.List)):
                    routed.update(
                        item.value for item in right.elts
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    )
    return routed


def test_exposed_gemini_tools_have_a_dispatch_branch():
    # Source-only AST: no TTS/audio import, Gemini call or Home Assistant action.
    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    advertised = _declared_tools(tree)
    routed = _routed_tools(tree)
    assert len(advertised) >= 20, "Tool inventory unexpectedly truncated"
    missing = sorted(advertised - routed)
    assert not missing, f"Exposed to Gemini without direct dispatch: {missing}"
