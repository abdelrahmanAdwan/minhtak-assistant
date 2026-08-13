"""Safe calculator tool — arithmetic only, no `eval`.

The agent uses this for grounded math: monthly budget (stipend minus rent),
funding gaps, quick ratios. It parses the expression into an AST and walks it,
allowing ONLY numbers and arithmetic operators. Names, calls, and attribute
access are rejected — there is no code-execution surface here.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

_BIN_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorError(Exception):
    """The expression was not safe, well-formed arithmetic."""


def calculate(expression: str) -> dict[str, Any]:
    """Evaluate an arithmetic `expression` and return its numeric result."""
    if not expression or not expression.strip():
        raise CalculatorError("no expression was provided")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"could not parse {expression!r}: {exc.msg}") from exc

    result = _eval(tree.body)
    # Present integers cleanly (10.0 -> 10) without losing real decimals.
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return {"expression": expression.strip(), "result": result}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculatorError("only numbers are allowed")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise CalculatorError(f"unsupported operator: {type(node.op).__name__}")
        try:
            return op(_eval(node.left), _eval(node.right))
        except ZeroDivisionError as exc:
            raise CalculatorError("division by zero") from exc
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise CalculatorError(f"unsupported unary operator: {type(node.op).__name__}")
        return op(_eval(node.operand))
    raise CalculatorError(
        "only numbers and + - * / // % ** operators are allowed"
    )
