# Project:   scalo
# File:      expression/cel.py
# Purpose:   CEL expression evaluation wrapper
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""CEL expression evaluation -- compile, evaluate, validate, diagnose.

Wraps the ``common-expression-language`` package (which itself wraps the
Rust ``cel`` crate via PyO3). The same Rust implementation powers both
Python and Rust services -- zero behavioural drift.

Every entry point enforces the expression profile. ``profile=None`` means the
profile the config cascade sets under ``expression``.

Install::

    pip install scalo[expression]

Usage::

    from scalo.expression import compile_expression, diagnose, evaluate, validate

    # Validate before storing (UI pre-submit)
    errors = validate('severity == "critical" && amount > 10000')
    assert errors == []

    # The same check, each finding with the byte span it covers
    found = diagnose('name.matches("^x")')
    assert found[0].span.start == 5

    # One-shot evaluation
    result = evaluate('severity == "critical"', {"severity": "critical"})
    assert result is True

    # Compile once, evaluate many (hot path)
    program = compile_expression("amount > threshold")
    program.execute({"amount": 15000, "threshold": 10000})  # True
    program.execute({"amount": 500, "threshold": 10000})     # False

    # Boolean condition evaluation (missing fields -> False)
    result = evaluate_condition('severity == "critical"', {})
    assert result is False
"""

import functools
import re
from typing import Any

try:
    import cel as _cel
except ImportError as e:
    raise ImportError(
        "CEL expression support requires the 'expression' extra. Install with: pip install scalo[expression]"
    ) from e

from .diagnostic import Diagnostic, span_at
from .profile import ProfileConfig, cascade_profile, check_profile, scan_profile

__all__ = [
    "EVALUATION_ERRORS",
    "ExpressionError",
    "compile_expression",
    "diagnose",
    "evaluate",
    "evaluate_condition",
    "validate",
]

# What the cel package raises from Program.execute, by the CEL error it maps.
EVALUATION_ERRORS: tuple[type[Exception], ...] = (RuntimeError, ValueError, TypeError, ArithmeticError, LookupError)

# Distinct conditions evaluate_condition keeps compiled, least recently used dropped first.
_CONDITION_CACHE_SIZE = 1024

# One parser error in the cel package's report: line and column from 1, then the message.
_PARSE_ERROR = re.compile(r"^ERROR: <input>:(\d+):(\d+): (.*)$", re.MULTILINE)


class ExpressionError(Exception):
    """Raised when an expression fails compilation or profile validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _resolve(profile: ProfileConfig | None) -> ProfileConfig:
    return profile if profile is not None else cascade_profile()


def _validated(expr: str, profile: ProfileConfig) -> tuple[_cel.Program | None, list[str]]:
    """Compile ``expr`` under ``profile``, or return every error that stops it."""
    if not expr or not expr.strip():
        return None, ["Expression is empty"]
    profile_errors = check_profile(expr, profile)
    if profile_errors:
        return None, profile_errors
    try:
        return _cel.compile(expr), []
    except (ValueError, TypeError) as e:
        message = str(e)
        if "Failed to parse expression" in message:
            return None, [message]
        return None, [f"Invalid expression: {message}"]


def _parse_diagnostics(expr: str, message: str) -> list[Diagnostic]:
    """Split the cel package's parse report into one located diagnostic per parser error."""
    # The report opens with the expression itself, which may hold anything, so it is cut first.
    prefix = f"Failed to parse expression '{expr}': "
    report = message.removeprefix(prefix)
    found = [
        Diagnostic(match.group(3), span_at(expr, int(match.group(1)), int(match.group(2))))
        for match in _PARSE_ERROR.finditer(report)
    ]
    return found or [Diagnostic(message)]


def compile_diagnosed(expr: str, profile: ProfileConfig | None = None) -> tuple[_cel.Program | None, list[Diagnostic]]:
    """Compile ``expr``, or return every located problem that stops it.

    Args:
        expr: CEL expression string.
        profile: The profile to enforce. ``None`` means the cascade's.

    Returns:
        ``(program, [])`` when it compiles, else ``(None, diagnostics)``.
    """
    if not expr.strip():
        return None, [Diagnostic("Expression is empty")]
    found = scan_profile(expr, _resolve(profile))
    if found:
        return None, found
    try:
        return _cel.compile(expr), []
    except (ValueError, TypeError) as e:
        return None, _parse_diagnostics(expr, str(e))


def validate(expr: str, profile: ProfileConfig | None = None) -> list[str]:
    """Validate an expression for syntax and expression profile compliance.

    Returns a list of error strings (empty if valid).
    Designed for UI pre-submit validation -- call this before storing expressions.

    Args:
        expr: CEL expression string.
        profile: The profile to enforce. ``None`` means the cascade's.

    Returns:
        Empty list if valid, list of error messages otherwise.
    """
    return _validated(expr, _resolve(profile))[1]


def diagnose(expr: str, profile: ProfileConfig | None = None) -> list[Diagnostic]:
    """Return :func:`validate`'s findings, each with the byte span it covers.

    A profile finding spans the function name. A syntax error spans the character the
    parser stopped at.

    Args:
        expr: CEL expression string.
        profile: The profile to enforce. ``None`` means the cascade's.

    Returns:
        Empty list if valid, one :class:`~scalo.expression.Diagnostic` per problem otherwise.
    """
    return compile_diagnosed(expr, profile)[1]


def compile_expression(expr: str, profile: ProfileConfig | None = None) -> _cel.Program:
    """Compile a CEL expression, enforcing the expression profile.

    Use this for hot paths where the same expression is evaluated
    against many records. Compile once, call ``program.execute(data)``
    for each record.

    Args:
        expr: CEL expression string.
        profile: The profile to enforce. ``None`` means the cascade's.

    Returns:
        Compiled CEL program.

    Raises:
        ExpressionError: If expression is invalid or violates expression profile.
    """
    program, errors = _validated(expr, _resolve(profile))
    if program is None:
        raise ExpressionError(errors)
    return program


def evaluate(expr: str, data: dict[str, Any] | None = None) -> Any:
    """Compile and evaluate a CEL expression in one step.

    For repeated evaluation of the same expression, use
    :func:`compile_expression` instead.

    Args:
        expr: CEL expression string.
        data: Variable context (field name -> value).

    Returns:
        The expression result (bool, int, float, string, list, etc.)

    Raises:
        ExpressionError: If expression is invalid or violates expression profile.
        RuntimeError: If evaluation fails (missing fields, type mismatch).
    """
    program = compile_expression(expr)
    return program.execute(data or {})


@functools.lru_cache(maxsize=_CONDITION_CACHE_SIZE)
def _condition_program(expr: str, profile: ProfileConfig) -> _cel.Program | None:
    return _validated(expr, profile)[0]


def evaluate_condition(expr: str, data: dict[str, Any]) -> bool:
    """Evaluate a boolean condition, returning False on missing fields.

    This is the safe evaluation mode for scoring ``when`` conditions,
    alert triggers, and routing rules. If a field referenced in the
    expression is missing from ``data``, returns ``False`` instead of
    raising an error. Each distinct expression is compiled once and kept.

    Args:
        expr: CEL expression that should evaluate to a boolean.
        data: Variable context (field name -> value).

    Returns:
        True if the condition matches, False otherwise (including on
        an invalid expression and on every evaluation error).
    """
    program = _condition_program(expr, cascade_profile())
    if program is None:
        return False
    try:
        return bool(program.execute(data))
    except EVALUATION_ERRORS:
        return False
