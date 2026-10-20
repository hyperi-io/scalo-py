# Project:   scalo
# File:      tests/unit/test_expression/test_condition.py
# Purpose:   Tests for evaluate_condition's compile cache and error handling
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""evaluate_condition compiles each expression once and turns every evaluation error into False."""

import pytest

from scalo.expression import cel as cel_module
from scalo.expression import evaluate_condition


class TestCompileOnce:
    """Scoring and alert loops call evaluate_condition per record with the same few expressions."""

    def test_repeated_calls_reuse_the_compiled_program(self):
        expr = 'severity == "high" && score > 7'
        cel_module._condition_program.cache_clear()

        assert evaluate_condition(expr, {"severity": "high", "score": 9}) is True
        assert evaluate_condition(expr, {"severity": "low", "score": 9}) is False
        assert evaluate_condition(expr, {"severity": "high", "score": 1}) is False

        info = cel_module._condition_program.cache_info()
        assert info.misses == 1, info
        assert info.hits == 2, info

    def test_an_invalid_expression_is_cached_as_no_program(self):
        cel_module._condition_program.cache_clear()
        assert evaluate_condition("== broken", {}) is False
        assert evaluate_condition("== broken", {}) is False
        info = cel_module._condition_program.cache_info()
        assert (info.misses, info.hits) == (1, 1), info


class TestEveryEvaluationErrorIsFalse:
    """A condition that cannot be evaluated does not match, whatever the error type."""

    @pytest.mark.parametrize(
        ("expr", "data"),
        [
            ('user.role == "admin"', {"user": {}}),
            ("x / 0 > 1", {"x": 1}),
            ("[1][3] == 1", {}),
            ("9223372036854775807 + x > 0", {"x": 1}),
        ],
        ids=["missing-nested-key", "division-by-zero", "index-out-of-range", "overflow"],
    )
    def test_an_evaluation_error_is_false(self, expr, data):
        assert evaluate_condition(expr, data) is False
