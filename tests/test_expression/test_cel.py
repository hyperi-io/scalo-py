# Project:   hyperi-pylib
# File:      tests/test_expression/test_cel.py
# Purpose:   Tests for CEL expression module
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the CEL expression evaluation module."""

import pytest

from hyperi_pylib.expression import (
    ALLOWED_FUNCTIONS,
    DISALLOWED_FUNCTIONS,
    ExpressionError,
    compile_expression,
    evaluate,
    evaluate_condition,
    validate,
)

# ── validate() ────────────────────────────────────────────────


class TestValidate:
    """Validate expression syntax + DFE profile compliance."""

    def test_valid_comparison(self):
        assert validate('severity == "critical"') == []

    def test_valid_numeric(self):
        assert validate("amount > 10000") == []

    def test_valid_logical(self):
        assert validate("a > 1 && b < 10") == []

    def test_valid_membership(self):
        assert validate('status in ["active", "pending"]') == []

    def test_valid_negated_membership(self):
        assert validate('!(status in ["blocked"])') == []

    def test_valid_string_function(self):
        assert validate('msg.contains("error")') == []

    def test_valid_starts_with(self):
        assert validate('path.startsWith("/api/")') == []

    def test_valid_ends_with(self):
        assert validate('file.endsWith(".log")') == []

    def test_valid_matches(self):
        assert validate('name.matches("^web-[0-9]+$")') == []

    def test_valid_has(self):
        assert validate("has(user.name)") == []

    def test_valid_size(self):
        assert validate("size(tags) > 0") == []

    def test_valid_ternary(self):
        assert validate("is_admin ? 95 : 50") == []

    def test_valid_type_cast(self):
        assert validate("int(x) > 10") == []

    def test_valid_arithmetic(self):
        assert validate("price * quantity > threshold") == []

    def test_valid_boolean_literal(self):
        assert validate("enabled == true") == []

    def test_valid_null_check(self):
        assert validate("x == null") == []

    def test_valid_compound(self):
        assert validate('severity == "critical" && amount > 10000 && !is_test') == []

    def test_empty_expression(self):
        errors = validate("")
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_whitespace_only(self):
        errors = validate("   ")
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_invalid_syntax(self):
        errors = validate("== broken")
        assert len(errors) == 1

    def test_invalid_expression(self):
        errors = validate("not valid stuff here")
        assert len(errors) >= 1

    def test_disallowed_map(self):
        errors = validate("[1,2,3].map(x, x * 2)")
        assert len(errors) == 1
        assert "map()" in errors[0]
        assert "not allowed" in errors[0]

    def test_disallowed_filter(self):
        errors = validate("[1,2,3].filter(x, x > 1)")
        assert len(errors) == 1
        assert "filter()" in errors[0]

    def test_disallowed_exists(self):
        errors = validate("[1,2,3].exists(x, x > 2)")
        assert len(errors) == 1
        assert "exists()" in errors[0]

    def test_disallowed_all(self):
        errors = validate("[1,2,3].all(x, x > 0)")
        assert len(errors) == 1
        assert "all()" in errors[0]

    def test_disallowed_timestamp(self):
        errors = validate('timestamp("2024-01-01T00:00:00Z")')
        assert len(errors) == 1
        assert "timestamp()" in errors[0]

    def test_disallowed_duration(self):
        errors = validate('duration("1h")')
        assert len(errors) == 1
        assert "duration()" in errors[0]


# ── evaluate() ────────────────────────────────────────────────


class TestEvaluate:
    """One-shot CEL expression evaluation."""

    def test_arithmetic(self):
        assert evaluate("1 + 2") == 3

    def test_string_concat(self):
        assert evaluate('"hello" + " world"') == "hello world"

    def test_comparison_true(self):
        assert evaluate('severity == "critical"', {"severity": "critical"}) is True

    def test_comparison_false(self):
        assert evaluate('severity == "critical"', {"severity": "low"}) is False

    def test_numeric_gt(self):
        assert evaluate("amount > 10000", {"amount": 15000}) is True

    def test_numeric_gt_false(self):
        assert evaluate("amount > 10000", {"amount": 5000}) is False

    def test_numeric_ge(self):
        assert evaluate("count >= 100", {"count": 100}) is True

    def test_numeric_lt(self):
        assert evaluate("risk < 5", {"risk": 3}) is True

    def test_numeric_le(self):
        assert evaluate("risk <= 5", {"risk": 5}) is True

    def test_numeric_eq(self):
        assert evaluate("port == 443", {"port": 443}) is True

    def test_numeric_ne(self):
        assert evaluate("port != 80", {"port": 443}) is True

    def test_logical_and(self):
        assert evaluate("a > 1 && b < 10", {"a": 5, "b": 3}) is True

    def test_logical_or(self):
        assert evaluate("a > 100 || b < 10", {"a": 5, "b": 3}) is True

    def test_logical_not(self):
        assert evaluate("!is_test", {"is_test": False}) is True

    def test_membership_in(self):
        assert evaluate('status in ["active", "pending"]', {"status": "active"}) is True

    def test_membership_in_false(self):
        assert evaluate('status in ["active", "pending"]', {"status": "blocked"}) is False

    def test_negated_in(self):
        assert evaluate('!(status in ["blocked"])', {"status": "active"}) is True

    def test_string_contains(self):
        assert evaluate('msg.contains("error")', {"msg": "an error occurred"}) is True

    def test_string_starts_with(self):
        assert evaluate('path.startsWith("/api/")', {"path": "/api/v1/users"}) is True

    def test_string_ends_with(self):
        assert evaluate('file.endsWith(".log")', {"file": "app.log"}) is True

    def test_string_matches_regex(self):
        assert evaluate('name.matches("^web-[0-9]+$")', {"name": "web-42"}) is True

    def test_string_matches_regex_false(self):
        assert evaluate('name.matches("^web-[0-9]+$")', {"name": "db-01"}) is False

    def test_has_present(self):
        assert evaluate("has(user.name)", {"user": {"name": "derek"}}) is True

    def test_has_missing(self):
        assert evaluate("has(user.name)", {"user": {}}) is False

    def test_size_list(self):
        assert evaluate("size(tags) > 0", {"tags": ["a", "b"]}) is True

    def test_size_string(self):
        assert evaluate("size(msg) > 5", {"msg": "hello world"}) is True

    def test_size_empty_list(self):
        assert evaluate("size(tags) == 0", {"tags": []}) is True

    def test_ternary_true(self):
        assert evaluate("is_admin ? 95 : 50", {"is_admin": True}) == 95

    def test_ternary_false(self):
        assert evaluate("is_admin ? 95 : 50", {"is_admin": False}) == 50

    def test_int_cast(self):
        assert evaluate('int(x) > 10', {"x": "15"}) is True

    def test_nested_field_access(self):
        assert evaluate('user.role == "admin"', {"user": {"role": "admin"}}) is True

    def test_boolean_true(self):
        assert evaluate("enabled == true", {"enabled": True}) is True

    def test_boolean_false(self):
        assert evaluate("enabled == false", {"enabled": False}) is True

    def test_null_check(self):
        assert evaluate("x == null", {"x": None}) is True

    def test_negative_number(self):
        assert evaluate("score > -10", {"score": 5}) is True

    def test_single_quoted_string(self):
        assert evaluate("severity == 'critical'", {"severity": "critical"}) is True

    def test_float_comparison(self):
        assert evaluate("score > 0.5", {"score": 0.8}) is True

    def test_compound_condition(self):
        result = evaluate(
            'severity == "critical" && amount > 10000',
            {"severity": "critical", "amount": 15000},
        )
        assert result is True

    def test_missing_field_raises(self):
        with pytest.raises(RuntimeError):
            evaluate('severity == "critical"', {})

    def test_invalid_expression_raises(self):
        with pytest.raises(ExpressionError):
            evaluate("== broken", {})

    def test_disallowed_function_raises(self):
        with pytest.raises(ExpressionError):
            evaluate("[1,2].map(x, x * 2)", {})

    def test_numeric_in_list(self):
        assert evaluate("port in [80, 443, 8080]", {"port": 443}) is True


# ── evaluate_condition() ──────────────────────────────────────


class TestEvaluateCondition:
    """Boolean condition evaluation — missing fields → False."""

    def test_match(self):
        assert evaluate_condition('severity == "critical"', {"severity": "critical"}) is True

    def test_no_match(self):
        assert evaluate_condition('severity == "critical"', {"severity": "low"}) is False

    def test_missing_field_returns_false(self):
        assert evaluate_condition('severity == "critical"', {}) is False

    def test_missing_nested_field_returns_false(self):
        assert evaluate_condition('user.role == "admin"', {}) is False

    def test_type_mismatch_returns_false(self):
        assert evaluate_condition("amount > 10", {"amount": "not_a_number"}) is False

    def test_invalid_expression_returns_false(self):
        assert evaluate_condition("== broken", {}) is False

    def test_empty_expression_returns_false(self):
        assert evaluate_condition("", {}) is False

    def test_compound_condition(self):
        assert evaluate_condition(
            'severity == "critical" && amount > 10000',
            {"severity": "critical", "amount": 15000},
        ) is True

    def test_compound_partial_match(self):
        assert evaluate_condition(
            'severity == "critical" && amount > 10000',
            {"severity": "critical", "amount": 5000},
        ) is False

    def test_in_membership(self):
        assert evaluate_condition(
            'status in ["active", "pending"]',
            {"status": "active"},
        ) is True

    def test_negated_in(self):
        assert evaluate_condition(
            '!(status in ["blocked", "banned"])',
            {"status": "active"},
        ) is True

    def test_string_function(self):
        assert evaluate_condition(
            'msg.contains("error")',
            {"msg": "an error occurred"},
        ) is True

    def test_numeric_comparison(self):
        assert evaluate_condition("amount > 10000", {"amount": 15000}) is True

    def test_boolean_literal(self):
        assert evaluate_condition("enabled == true", {"enabled": True}) is True

    def test_ternary_as_bool(self):
        # Ternary returning int — coerced to bool (non-zero = True)
        assert evaluate_condition("is_admin ? 95 : 0", {"is_admin": True}) is True
        assert evaluate_condition("is_admin ? 0 : 50", {"is_admin": True}) is False


# ── compile_expression() ──────────────────────────────────────


class TestCompileExpression:
    """Pre-compilation for hot-path evaluation."""

    def test_compile_and_execute(self):
        program = compile_expression("price * quantity > threshold")
        assert program.execute({"price": 10, "quantity": 5, "threshold": 40}) is True
        assert program.execute({"price": 3, "quantity": 2, "threshold": 10}) is False

    def test_compile_reuse(self):
        program = compile_expression('severity == "critical"')
        assert program.execute({"severity": "critical"}) is True
        assert program.execute({"severity": "low"}) is False
        assert program.execute({"severity": "critical"}) is True

    def test_compile_invalid_raises(self):
        with pytest.raises(ExpressionError):
            compile_expression("== broken")

    def test_compile_disallowed_raises(self):
        with pytest.raises(ExpressionError):
            compile_expression("[1,2].map(x, x*2)")

    def test_compile_empty_raises(self):
        with pytest.raises(ExpressionError):
            compile_expression("")


# ── Profile ───────────────────────────────────────────────────


class TestProfile:
    """DFE expression profile constants."""

    def test_allowed_functions_contains_core(self):
        for fn in ("contains", "startsWith", "endsWith", "matches", "size", "has"):
            assert fn in ALLOWED_FUNCTIONS

    def test_allowed_functions_contains_casts(self):
        for fn in ("int", "uint", "double", "string", "bool"):
            assert fn in ALLOWED_FUNCTIONS

    def test_disallowed_functions(self):
        for fn in ("map", "filter", "exists", "all", "exists_one", "timestamp", "duration"):
            assert fn in DISALLOWED_FUNCTIONS

    def test_no_overlap(self):
        assert frozenset() == ALLOWED_FUNCTIONS & DISALLOWED_FUNCTIONS


# ── ExpressionError ───────────────────────────────────────────


class TestExpressionError:
    """Error type for expression failures."""

    def test_errors_list(self):
        err = ExpressionError(["error one", "error two"])
        assert err.errors == ["error one", "error two"]
        assert "error one" in str(err)
        assert "error two" in str(err)

    def test_single_error(self):
        err = ExpressionError(["bad syntax"])
        assert str(err) == "bad syntax"
