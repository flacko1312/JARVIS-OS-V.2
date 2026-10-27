from __future__ import annotations

import ast
import math
import operator
import re


_MAX_EXPR_LEN = 160
_MAX_ABS_RESULT = 1e100
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _normalize_expression(raw: str) -> str:
    text = str(raw or "").strip().casefold()
    if not text:
        raise ValueError("Falta la operación a calcular.")
    if len(text) > _MAX_EXPR_LEN:
        raise ValueError("La operación es demasiado larga.")

    text = text.replace("×", "*").replace("÷", "/").replace("^", "**")
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    text = re.sub(r"\bpor\s+ciento\s+de\b", "% de", text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%\s+de\s+(\d+(?:\.\d+)?)", r"(\1/100)*\2", text)
    replacements = (
        (r"\bm[aá]s\b", "+"),
        (r"\bmenos\b", "-"),
        (r"\bpor\b", "*"),
        (r"\bentre\b", "/"),
        (r"\bdividido\s+por\b", "/"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    text = re.sub(r"\s+x\s+", " * ", text)
    text = re.sub(r"\bal\s+cuadrado\b", "**2", text)
    text = re.sub(r"\bal\s+cubo\b", "**3", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("El exponente es demasiado grande.")
        value = _ALLOWED_BINOPS[type(node.op)](left, right)
        if isinstance(value, complex) or not math.isfinite(float(value)) or abs(float(value)) > _MAX_ABS_RESULT:
            raise ValueError("El resultado está fuera del rango permitido.")
        return value
    raise ValueError("La operación contiene elementos no permitidos.")


def calculate(expression: str) -> str:
    normalized = _normalize_expression(expression)
    try:
        tree = ast.parse(normalized, mode="eval")
        value = _eval_node(tree)
    except ZeroDivisionError:
        return "No se puede dividir entre cero."
    except (SyntaxError, ValueError, OverflowError) as exc:
        return f"No he podido calcular esa operación: {exc}"

    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, float):
        value = round(value, 12)
    return f"Resultado: {value}"


def calculator(parameters=None, response=None, player=None) -> str:
    params = parameters or {}
    return calculate(str(params.get("expression") or params.get("query") or ""))
