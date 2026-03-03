# Project:   hyperi-pylib
# File:      tests/test_expression/test_transpiler.py
# Purpose:   Tests for CEL-to-ClickHouse SQL transpiler
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the CEL-to-ClickHouse SQL transpiler."""

import pytest

from hyperi_pylib.expression import (
    ExpressionError,
    TranspileError,
    transpile_to_clickhouse,
)

# ── Mapping table (EXPRESSIONS-CEL.md) ────────────────────────


class TestMappingTable:
    """Every row from docs/EXPRESSIONS-CEL.md lines 164-173."""

    def test_string_equality(self):
        assert transpile_to_clickhouse('severity == "critical"') == "severity = 'critical'"

    def test_logical_and_with_not(self):
        assert transpile_to_clickhouse("amount > 10000 && !is_test") == "amount > 10000 AND NOT is_test"

    def test_membership_in_list(self):
        assert transpile_to_clickhouse('status in ["active", "pending"]') == "status IN ('active', 'pending')"

    def test_contains(self):
        assert transpile_to_clickhouse('message.contains("error")') == "position(message, 'error') > 0"

    def test_starts_with(self):
        assert transpile_to_clickhouse('path.startsWith("/api/")') == "startsWith(path, '/api/')"

    def test_matches(self):
        assert transpile_to_clickhouse('hostname.matches("^web-[0-9]+$")') == "match(hostname, '^web-[0-9]+$')"

    def test_has(self):
        # CEL has() macro requires member access syntax: has(obj.field)
        assert transpile_to_clickhouse("has(event.user_id)") == "event.user_id IS NOT NULL"

    def test_size(self):
        assert transpile_to_clickhouse("size(tags) > 0") == "length(tags) > 0"


# ── Comparison operators ──────────────────────────────────────


class TestComparison:
    """Comparison operators: ==, !=, <, <=, >, >=."""

    def test_eq(self):
        assert transpile_to_clickhouse("x == 1") == "x = 1"

    def test_ne(self):
        assert transpile_to_clickhouse("x != 1") == "x != 1"

    def test_lt(self):
        assert transpile_to_clickhouse("x < 10") == "x < 10"

    def test_le(self):
        assert transpile_to_clickhouse("x <= 10") == "x <= 10"

    def test_gt(self):
        assert transpile_to_clickhouse("x > 10") == "x > 10"

    def test_ge(self):
        assert transpile_to_clickhouse("x >= 10") == "x >= 10"


# ── Logical operators ─────────────────────────────────────────


class TestLogical:
    """Logical operators: &&, ||, !."""

    def test_and(self):
        assert transpile_to_clickhouse("a > 1 && b < 10") == "a > 1 AND b < 10"

    def test_or(self):
        assert transpile_to_clickhouse("a > 1 || b < 10") == "a > 1 OR b < 10"

    def test_not(self):
        assert transpile_to_clickhouse("!enabled") == "NOT enabled"

    def test_double_not(self):
        assert transpile_to_clickhouse("!!enabled") == "NOT NOT enabled"

    def test_and_or_precedence(self):
        # && binds tighter than ||, so a || (b && c)
        result = transpile_to_clickhouse("a || b && c")
        assert result == "a OR b AND c"

    def test_or_grouped(self):
        result = transpile_to_clickhouse("(a || b) && c")
        assert result == "(a OR b) AND c"


# ── Membership ────────────────────────────────────────────────


class TestMembership:
    """Membership operator: in."""

    def test_in_strings(self):
        assert transpile_to_clickhouse('x in ["a", "b"]') == "x IN ('a', 'b')"

    def test_in_numbers(self):
        assert transpile_to_clickhouse("port in [80, 443, 8080]") == "port IN (80, 443, 8080)"

    def test_negated_in(self):
        result = transpile_to_clickhouse('!(status in ["blocked", "banned"])')
        assert result == "NOT (status IN ('blocked', 'banned'))"


# ── String methods ────────────────────────────────────────────


class TestStringMethods:
    """String methods: contains, startsWith, endsWith, matches."""

    def test_contains(self):
        assert transpile_to_clickhouse('msg.contains("err")') == "position(msg, 'err') > 0"

    def test_starts_with(self):
        assert transpile_to_clickhouse('path.startsWith("/v1")') == "startsWith(path, '/v1')"

    def test_ends_with(self):
        assert transpile_to_clickhouse('file.endsWith(".log")') == "endsWith(file, '.log')"

    def test_matches(self):
        assert transpile_to_clickhouse('name.matches("^[a-z]+$")') == "match(name, '^[a-z]+$')"


# ── Functions ─────────────────────────────────────────────────


class TestFunctions:
    """Free functions: has, size, type casts."""

    def test_has(self):
        # CEL has() macro requires member access: has(obj.field)
        assert transpile_to_clickhouse("has(event.name)") == "event.name IS NOT NULL"

    def test_has_deeply_dotted(self):
        assert transpile_to_clickhouse("has(event.user.id)") == "event.user.id IS NOT NULL"

    def test_size_in_comparison(self):
        assert transpile_to_clickhouse("size(items) == 0") == "length(items) = 0"

    def test_int_cast(self):
        assert transpile_to_clickhouse("int(x) > 10") == "toInt64(x) > 10"

    def test_uint_cast(self):
        assert transpile_to_clickhouse("uint(x) > 10") == "toUInt64(x) > 10"

    def test_double_cast(self):
        assert transpile_to_clickhouse("double(x) > 1.5") == "toFloat64(x) > 1.5"

    def test_string_cast(self):
        assert transpile_to_clickhouse("string(code) == \"200\"") == "toString(code) = '200'"

    def test_bool_cast(self):
        assert transpile_to_clickhouse("bool(flag) == true") == "toBool(flag) = 1"


# ── Ternary ───────────────────────────────────────────────────


class TestTernary:
    """Ternary conditional: a ? b : c → if(a, b, c)."""

    def test_simple(self):
        assert transpile_to_clickhouse("is_admin ? 95 : 50") == "if(is_admin, 95, 50)"

    def test_with_comparison(self):
        result = transpile_to_clickhouse('risk > 80 ? "high" : "low"')
        assert result == "if(risk > 80, 'high', 'low')"

    def test_nested(self):
        result = transpile_to_clickhouse('a > 80 ? "high" : a > 40 ? "medium" : "low"')
        assert result == "if(a > 80, 'high', if(a > 40, 'medium', 'low'))"


# ── Arithmetic ────────────────────────────────────────────────


class TestArithmetic:
    """Arithmetic operators: +, -, *, /, %."""

    def test_addition(self):
        assert transpile_to_clickhouse("a + b > 10") == "a + b > 10"

    def test_multiplication(self):
        assert transpile_to_clickhouse("price * quantity > threshold") == "price * quantity > threshold"

    def test_precedence(self):
        # * binds tighter than +, so (a + (b * c))
        assert transpile_to_clickhouse("a + b * c") == "a + b * c"

    def test_modulo(self):
        assert transpile_to_clickhouse("x % 2 == 0") == "x % 2 = 0"

    def test_subtraction(self):
        assert transpile_to_clickhouse("a - b > 0") == "a - b > 0"

    def test_division(self):
        assert transpile_to_clickhouse("total / count > 5") == "total / count > 5"


# ── Literals ──────────────────────────────────────────────────


class TestLiterals:
    """String, number, boolean, null literals."""

    def test_string_double_quotes(self):
        assert transpile_to_clickhouse('x == "hello"') == "x = 'hello'"

    def test_integer(self):
        assert transpile_to_clickhouse("x == 42") == "x = 42"

    def test_float(self):
        assert transpile_to_clickhouse("x > 3.14") == "x > 3.14"

    def test_true(self):
        assert transpile_to_clickhouse("enabled == true") == "enabled = 1"

    def test_false(self):
        assert transpile_to_clickhouse("enabled == false") == "enabled = 0"

    def test_null(self):
        assert transpile_to_clickhouse("x == null") == "x = NULL"

    def test_negative_number(self):
        assert transpile_to_clickhouse("score > -10") == "score > -10"


# ── Identifiers ───────────────────────────────────────────────


class TestIdentifiers:
    """Simple and dotted identifiers."""

    def test_simple(self):
        assert transpile_to_clickhouse("severity == \"critical\"") == "severity = 'critical'"

    def test_dotted(self):
        assert transpile_to_clickhouse('event.user_id == "abc"') == "event.user_id = 'abc'"

    def test_deeply_dotted(self):
        assert transpile_to_clickhouse('a.b.c == "x"') == "a.b.c = 'x'"


# ── Precedence & parentheses ─────────────────────────────────


class TestPrecedence:
    """Operator precedence and explicit grouping."""

    def test_and_before_or(self):
        # a || (b && c) — no parens needed because AND > OR
        result = transpile_to_clickhouse("x || y && z")
        assert result == "x OR y AND z"

    def test_grouped_or(self):
        # (a || b) && c — parens preserved
        result = transpile_to_clickhouse("(x || y) && z")
        assert result == "(x OR y) AND z"

    def test_multiply_before_add(self):
        result = transpile_to_clickhouse("a + b * c")
        assert result == "a + b * c"

    def test_grouped_add(self):
        result = transpile_to_clickhouse("(a + b) * c")
        assert result == "(a + b) * c"

    def test_comparison_with_logical(self):
        result = transpile_to_clickhouse("a > 1 && b < 10 || c == 5")
        assert result == "a > 1 AND b < 10 OR c = 5"


# ── Compound expressions ─────────────────────────────────────


class TestCompound:
    """Real-world compound expressions from hunt/alert configs."""

    def test_hunt_scoring(self):
        result = transpile_to_clickhouse('severity == "critical" && amount > 10000')
        assert result == "severity = 'critical' AND amount > 10000"

    def test_alert_trigger(self):
        result = transpile_to_clickhouse("result_count > 0")
        assert result == "result_count > 0"

    def test_routing_rule(self):
        result = transpile_to_clickhouse('source_type == "syslog" && facility in [1, 2, 3]')
        assert result == "source_type = 'syslog' AND facility IN (1, 2, 3)"

    def test_complex_condition(self):
        result = transpile_to_clickhouse(
            'severity == "critical" && !is_test && amount > 10000'
        )
        assert result == "severity = 'critical' AND NOT is_test AND amount > 10000"

    def test_string_with_membership(self):
        result = transpile_to_clickhouse(
            'msg.contains("error") && status in ["active", "pending"]'
        )
        assert result == "position(msg, 'error') > 0 AND status IN ('active', 'pending')"


# ── Error cases ───────────────────────────────────────────────


class TestErrors:
    """Invalid inputs and unsupported constructs."""

    def test_empty_expression(self):
        with pytest.raises(ExpressionError):
            transpile_to_clickhouse("")

    def test_whitespace_only(self):
        with pytest.raises(ExpressionError):
            transpile_to_clickhouse("   ")

    def test_invalid_syntax(self):
        with pytest.raises(ExpressionError):
            transpile_to_clickhouse("== broken")

    def test_disallowed_function(self):
        with pytest.raises(ExpressionError):
            transpile_to_clickhouse("[1,2,3].map(x, x * 2)")


# ── SQL injection safety ─────────────────────────────────────


class TestSQLInjection:
    """String escaping prevents SQL injection."""

    def test_single_quote_in_string(self):
        result = transpile_to_clickhouse("name == \"O'Brien\"")
        assert result == r"name = 'O\'Brien'"

    def test_backslash_in_string(self):
        # Backslashes in string literals are escaped for ClickHouse
        result = transpile_to_clickhouse(r'path == "test\\value"')
        assert "path = " in result
        assert "test" in result
        assert "value" in result

    def test_semicolon_in_string(self):
        # Semicolons inside string literals are safe (just data).
        result = transpile_to_clickhouse('cmd == "DROP; --"')
        assert result == "cmd = 'DROP; --'"
