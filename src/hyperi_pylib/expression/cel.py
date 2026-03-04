# Project:   hyperi-pylib
# File:      expression/cel.py
# Purpose:   CEL expression evaluation wrapper for DFE
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""CEL expression evaluation — compile, evaluate, validate.

Wraps the ``common-expression-language`` package (which itself wraps the
Rust ``cel-interpreter`` crate via PyO3). The same Rust implementation
powers both Python and Rust services — zero behavioural drift.

Install::

    pip install hyperi-pylib[expression]

Usage::

    from hyperi_pylib.expression import compile_expression, evaluate, validate

    # Validate before storing (UI pre-submit)
    errors = validate('severity == "critical" && amount > 10000')
    assert errors == []

    # One-shot evaluation
    result = evaluate('severity == "critical"', {"severity": "critical"})
    assert result is True

    # Compile once, evaluate many (hot path)
    program = compile_expression("amount > threshold")
    program.execute({"amount": 15000, "threshold": 10000})  # True
    program.execute({"amount": 500, "threshold": 10000})     # False

    # Boolean condition evaluation (missing fields → False)
    result = evaluate_condition('severity == "critical"', {})
    assert result is False
"""

from __future__ import annotations

import re
from typing import Any

try:
    import cel as _cel
except ImportError as e:
    raise ImportError(
        "CEL expression support requires the 'expression' extra. Install with: pip install hyperi-pylib[expression]"
    ) from e

from .profile import ALLOWED_FUNCTIONS, DISALLOWED_FUNCTIONS

__all__ = [
    "ExpressionError",
    "compile_expression",
    "evaluate",
    "evaluate_condition",
    "validate",
]


class ExpressionError(Exception):
    """Raised when an expression fails compilation or profile validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


# Match function calls in CEL expressions: name(
_FUNCTION_CALL_RE = re.compile(r"\b([a-zA-Z_]\w*)\s*\(")


def _check_profile(expr: str) -> list[str]:
    """Check expression against the DFE profile. Returns errors."""
    errors: list[str] = []
    for match in _FUNCTION_CALL_RE.finditer(expr):
        name = match.group(1)
        # Skip CEL keywords/literals that look like function calls
        if name in ("true", "false", "null", "in", "has", "int", "uint", "double", "string", "bool"):
            continue
        if name in DISALLOWED_FUNCTIONS:
            errors.append(
                f"Function '{name}()' is not allowed in the DFE expression profile. "
                f"Excluded for performance: per-element iteration or time functions."
            )
        elif name not in ALLOWED_FUNCTIONS:
            # Unknown function — CEL will reject it at compile time anyway,
            # but we give a better error message here.
            pass  # Let CEL handle unknown functions with its own error
    return errors


def validate(expr: str) -> list[str]:
    """Validate an expression for syntax and DFE profile compliance.

    Returns a list of error strings (empty if valid).
    Designed for UI pre-submit validation — call this before storing expressions.

    Args:
        expr: CEL expression string.

    Returns:
        Empty list if valid, list of error messages otherwise.
    """
    errors: list[str] = []

    if not expr or not expr.strip():
        return ["Expression is empty"]

    # Check DFE profile (disallowed functions)
    profile_errors = _check_profile(expr)
    if profile_errors:
        return profile_errors

    # Check syntax via CEL compiler
    try:
        _cel.compile(expr)
    except (ValueError, TypeError) as e:
        msg = str(e)
        # Extract the readable part of the error
        if "Failed to parse expression" in msg:
            # Strip the wrapper, keep the ANTLR error
            errors.append(msg)
        else:
            errors.append(f"Invalid expression: {msg}")

    return errors


def compile_expression(expr: str) -> _cel.Program:
    """Compile a CEL expression, enforcing the DFE profile.

    Use this for hot paths where the same expression is evaluated
    against many records. Compile once, call ``program.execute(data)``
    for each record.

    Args:
        expr: CEL expression string.

    Returns:
        Compiled CEL program.

    Raises:
        ExpressionError: If expression is invalid or violates DFE profile.
    """
    errors = validate(expr)
    if errors:
        raise ExpressionError(errors)
    return _cel.compile(expr)


def evaluate(expr: str, data: dict[str, Any] | None = None) -> Any:
    """Compile and evaluate a CEL expression in one step.

    For repeated evaluation of the same expression, use
    :func:`compile_expression` instead.

    Args:
        expr: CEL expression string.
        data: Variable context (field name → value).

    Returns:
        The expression result (bool, int, float, string, list, etc.)

    Raises:
        ExpressionError: If expression is invalid or violates DFE profile.
        RuntimeError: If evaluation fails (missing fields, type mismatch).
    """
    program = compile_expression(expr)
    return program.execute(data or {})


def evaluate_condition(expr: str, data: dict[str, Any]) -> bool:
    """Evaluate a boolean condition, returning False on missing fields.

    This is the safe evaluation mode for scoring ``when`` conditions,
    alert triggers, and routing rules. If a field referenced in the
    expression is missing from ``data``, returns ``False`` instead of
    raising an error.

    Args:
        expr: CEL expression that should evaluate to a boolean.
        data: Variable context (field name → value).

    Returns:
        True if the condition matches, False otherwise (including on
        errors like missing fields or type mismatches).
    """
    try:
        program = compile_expression(expr)
        result = program.execute(data)
        return bool(result)
    except (RuntimeError, ValueError, TypeError, ExpressionError):
        return False
