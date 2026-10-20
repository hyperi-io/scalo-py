# Project:   scalo
# File:      expression/__init__.py
# Purpose:   CEL expression evaluation for services
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""scalo Expression Module -- CEL-based expression evaluation.

Provides compile, evaluate, validate and diagnose functions for CEL expressions,
restricted to the expression profile (bounded cost per record). Regex, iteration and
time functions are unlocked per category by :class:`ProfileConfig`, which apps set
under the ``expression`` key of the config cascade.

Both Python and Rust services use the same underlying ``cel`` Rust crate, ensuring
identical parsing and evaluation semantics. :mod:`scalo.expression.rules` builds
ordered first-match rule sets on top.

Install::

    pip install scalo[expression]

Usage::

    from scalo.expression import evaluate, validate, compile_expression

    # Validate (returns errors list, empty if valid)
    errors = validate('severity == "critical"')

    # One-shot evaluation
    result = evaluate('amount > 10000', {"amount": 15000})

    # Boolean condition (missing fields -> False)
    from scalo.expression import evaluate_condition
    result = evaluate_condition('severity == "critical"', {})  # False

    # Compile for hot-path reuse
    program = compile_expression("score > threshold")
    program.execute({"score": 85, "threshold": 80})  # True

See: docs/api/EXPRESSION.md for the full profile specification.
"""

from .cel import (
    ExpressionError,
    compile_expression,
    diagnose,
    evaluate,
    evaluate_condition,
    validate,
)
from .diagnostic import Diagnostic, Span
from .profile import (
    ALLOWED_FUNCTIONS,
    DISALLOWED_FUNCTIONS,
    RESTRICTED_ITERATION,
    RESTRICTED_REGEX,
    RESTRICTED_TIME,
    ProfileConfig,
    cascade_profile,
    check_profile,
    scan_profile,
)
from .transpiler import TranspileError, transpile_to_clickhouse

__all__ = [
    "ALLOWED_FUNCTIONS",
    "DISALLOWED_FUNCTIONS",
    "RESTRICTED_ITERATION",
    "RESTRICTED_REGEX",
    "RESTRICTED_TIME",
    "Diagnostic",
    "ExpressionError",
    "ProfileConfig",
    "Span",
    "TranspileError",
    "cascade_profile",
    "check_profile",
    "compile_expression",
    "diagnose",
    "evaluate",
    "evaluate_condition",
    "scan_profile",
    "transpile_to_clickhouse",
    "validate",
]
