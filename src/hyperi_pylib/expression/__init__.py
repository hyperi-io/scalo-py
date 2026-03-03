# Project:   hyperi-pylib
# File:      expression/__init__.py
# Purpose:   CEL expression evaluation for DFE components
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
hyperi-pylib Expression Module — CEL-based expression evaluation.

Provides compile, evaluate, and validate functions for CEL expressions,
restricted to the DFE expression profile (high-performance subset only).

Both Python and Rust services use the same underlying ``cel-interpreter``
Rust crate, ensuring identical parsing and evaluation semantics.

Install::

    pip install hyperi-pylib[expression]

Usage::

    from hyperi_pylib.expression import evaluate, validate, compile_expression

    # Validate (returns errors list, empty if valid)
    errors = validate('severity == "critical"')

    # One-shot evaluation
    result = evaluate('amount > 10000', {"amount": 15000})

    # Boolean condition (missing fields → False)
    from hyperi_pylib.expression import evaluate_condition
    result = evaluate_condition('severity == "critical"', {})  # False

    # Compile for hot-path reuse
    program = compile_expression("score > threshold")
    program.execute({"score": 85, "threshold": 80})  # True

See: dfe-engine/docs/EXPRESSIONS-CEL.md for the full profile specification.
"""

from .cel import (
    ExpressionError,
    compile_expression,
    evaluate,
    evaluate_condition,
    validate,
)
from .profile import ALLOWED_FUNCTIONS, DISALLOWED_FUNCTIONS
from .transpiler import TranspileError, transpile_to_clickhouse

__all__ = [
    "ExpressionError",
    "TranspileError",
    "compile_expression",
    "evaluate",
    "evaluate_condition",
    "validate",
    "transpile_to_clickhouse",
    "ALLOWED_FUNCTIONS",
    "DISALLOWED_FUNCTIONS",
]
