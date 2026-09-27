"""Tools the model may call, described in OpenAI function-calling format.

Adding a tool is two steps: write a function that returns something
JSON-serializable, then register it with :func:`tool` together with its JSON
schema. The chat loop sends ``TOOL_SCHEMAS`` with the request and runs
:func:`run_tool` for every call the model makes.
"""

from __future__ import annotations

import ast
import datetime
import inspect
import operator
import platform
from collections.abc import Callable
from typing import Any

__all__ = ["TOOL_SCHEMAS", "run_tool", "tool"]

_REGISTRY: dict[str, Callable[..., Any]] = {}
TOOL_SCHEMAS: list[dict[str, Any]] = []


def tool(name: str, description: str, parameters: dict[str, Any] | None = None):
    """Register ``fn`` as a tool the model can call."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _REGISTRY[name] = fn
        TOOL_SCHEMAS.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters or {"type": "object", "properties": {}},
                },
            }
        )
        return fn

    return decorator


async def run_tool(name: str, args: dict[str, Any]) -> Any:
    """Execute one tool call and return a JSON-serializable result."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"unknown tool {name!r}"}
    try:
        result = fn(**(args or {}))
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception as exc:  # noqa: BLE001 - reported back to the model
        return {"error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------- #
# Built-in tools
# --------------------------------------------------------------------- #

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Evaluate an arithmetic AST without going near ``eval``."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        if isinstance(node.op, ast.Pow):
            exponent = _safe_eval(node.right)
            if abs(exponent) > 1000:
                raise ValueError("exponent too large")
            return operator.pow(_safe_eval(node.left), exponent)
        return _OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


@tool(
    "get_current_time",
    "Return the current date and time on the server.",
    {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone name, for example America/Caracas. Defaults to UTC.",
            }
        },
    },
)
def get_current_time(timezone: str = "UTC") -> dict[str, str]:
    now = datetime.datetime.now(datetime.UTC)
    resolved = timezone or "UTC"
    if resolved.upper() != "UTC":
        try:
            from zoneinfo import ZoneInfo

            now = now.astimezone(ZoneInfo(resolved))
        except Exception:  # noqa: BLE001 - a bad timezone falls back to UTC
            resolved = "UTC"
    return {
        "iso": now.isoformat(timespec="seconds"),
        "human": now.strftime("%A %d %B %Y, %H:%M"),
        "timezone": resolved,
    }


@tool(
    "calculate",
    "Evaluate an arithmetic expression such as '(18 * 7) / 3'.",
    {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "The arithmetic expression."}
        },
        "required": ["expression"],
    },
)
def calculate(expression: str) -> dict[str, Any]:
    try:
        value = _safe_eval(ast.parse(expression, mode="eval"))
    except Exception as exc:  # noqa: BLE001 - reported back to the model
        return {"error": f"could not evaluate {expression!r}: {exc}"}
    return {"expression": expression, "result": value}


@tool("system_info", "Report the operating system and Python version of the server.")
def system_info() -> dict[str, str]:
    return {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "machine": platform.machine(),
    }
