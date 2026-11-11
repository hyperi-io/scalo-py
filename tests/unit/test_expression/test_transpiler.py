# Project:   scalo
# File:      tests/test_expression/test_transpiler.py
# Purpose:   Tests for CEL-to-ClickHouse SQL transpiler
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the CEL-to-ClickHouse SQL transpiler."""

import pytest

from scalo.expression import (
    ExpressionError,
    ProfileConfig,
    TranspileError,
    transpile_to_clickhouse,
)

REGEX = ProfileConfig(allow_regex=True)

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
        sql = transpile_to_clickhouse('hostname.matches("^web-[0-9]+$")', profile=REGEX)
        assert sql == "match(hostname, '^web-[0-9]+$')"

    def test_matches_needs_allow_regex(self):
        with pytest.raises(ExpressionError, match="allow_regex"):
            transpile_to_clickhouse('hostname.matches("^web-[0-9]+$")')

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
        assert transpile_to_clickhouse('name.matches("^[a-z]+$")', profile=REGEX) == "match(name, '^[a-z]+$')"


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
        assert transpile_to_clickhouse('string(code) == "200"') == "toString(code) = '200'"

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

    @pytest.mark.parametrize(
        ("expr", "sql"),
        [
            pytest.param("total / 2 > 5", "intDiv(total, 2) > 5", id="int"),
            pytest.param("total / int(count) > 5", "intDiv(total, toInt64(count)) > 5", id="int-conversion"),
            pytest.param("total / 2.0 > 5.0", "total / 2.0 > 5.0", id="double"),
            pytest.param("total / count > 5", None, id="no-fixed-type"),
        ],
    )
    def test_division(self, expr, sql):
        if sql is None:
            with pytest.raises(TranspileError, match="no fixed type"):
                transpile_to_clickhouse(expr)
        else:
            assert transpile_to_clickhouse(expr) == sql


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

    def test_null_eq_emits_is_null(self):
        # ClickHouse: `x = NULL` always returns NULL (never true); the
        # IS NULL form is the only working way to test for null-ness.
        assert transpile_to_clickhouse("x == null") == "x IS NULL"

    def test_null_ne_emits_is_not_null(self):
        assert transpile_to_clickhouse("x != null") == "x IS NOT NULL"

    def test_null_eq_reversed_emits_is_null(self):
        # CEL allows null on either side
        assert transpile_to_clickhouse("null == x") == "x IS NULL"

    def test_negative_number(self):
        assert transpile_to_clickhouse("score > -10") == "score > -10"


# ── Identifiers ───────────────────────────────────────────────


class TestIdentifiers:
    """Simple and dotted identifiers."""

    def test_simple(self):
        assert transpile_to_clickhouse('severity == "critical"') == "severity = 'critical'"

    def test_dotted(self):
        assert transpile_to_clickhouse('event.user_id == "abc"') == "event.user_id = 'abc'"

    def test_deeply_dotted(self):
        assert transpile_to_clickhouse('a.b.c == "x"') == "a.b.c = 'x'"


# ── Precedence & parentheses ─────────────────────────────────


class TestPrecedence:
    """Operator precedence and explicit grouping."""

    def test_and_before_or(self):
        # a || (b && c) -- no parens needed because AND > OR
        result = transpile_to_clickhouse("x || y && z")
        assert result == "x OR y AND z"

    def test_grouped_or(self):
        # (a || b) && c -- parens preserved
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
        result = transpile_to_clickhouse('severity == "critical" && !is_test && amount > 10000')
        assert result == "severity = 'critical' AND NOT is_test AND amount > 10000"

    def test_string_with_membership(self):
        result = transpile_to_clickhouse('msg.contains("error") && status in ["active", "pending"]')
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
        result = transpile_to_clickhouse('name == "O\'Brien"')
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


# ── JSON columns ──────────────────────────────────────────────

_N = "doc.a.:Int64 {op} {v}, doc.a.:UInt64 {op} {v}, doc.a.:Float64 {op} {v}"


class TestJsonColumns:
    """A path under a JSON column reads the typed sub-column the other operand's type picks."""

    @pytest.mark.parametrize(
        ("expr", "sql"),
        [
            pytest.param(
                "doc.a == 42",
                f"coalesce({_N.format(op='=', v=42)}, if(doc.a IS NULL, NULL, false))",
                id="number-equals",
            ),
            pytest.param(
                "doc.a != 42",
                f"coalesce({_N.format(op='!=', v=42)}, if(doc.a IS NULL, NULL, true))",
                id="number-not-equals-holds-for-other-types",
            ),
            pytest.param("doc.a > 10", f"coalesce({_N.format(op='>', v=10)})", id="number-ordering"),
            pytest.param("doc.a >= -1.5", f"coalesce({_N.format(op='>=', v=-1.5)})", id="negative-double"),
            pytest.param("10 < doc.a", f"coalesce({_N.format(op='>', v=10)})", id="path-on-the-right"),
            pytest.param(
                'doc.a == "8080"',
                "coalesce(doc.a.:String = '8080', if(doc.a IS NULL, NULL, false))",
                id="string-never-matches-a-number",
            ),
            pytest.param('doc.a > "m"', "doc.a.:String > 'm'", id="string-ordering"),
            pytest.param('!(doc.a > "m")', "NOT (doc.a.:String > 'm')", id="string-ordering-negated"),
            pytest.param(
                "doc.a == true",
                "coalesce(doc.a.:Bool = 1, if(doc.a IS NULL, NULL, false))",
                id="bool-equals",
            ),
            pytest.param(
                'doc.a in [1, "x", 2]',
                "coalesce(doc.a.:Int64 IN (1, 2), doc.a.:UInt64 IN (1, 2), doc.a.:Float64 IN (1, 2),"
                " doc.a.:String IN ('x'), if(doc.a IS NULL, NULL, false))",
                id="in-splits-by-type",
            ),
            pytest.param('doc.a.contains("x")', "position(doc.a.:String, 'x') > 0", id="contains"),
            pytest.param('doc.a.startsWith("x")', "startsWith(doc.a.:String, 'x')", id="starts-with"),
            pytest.param('doc.a.endsWith("x")', "endsWith(doc.a.:String, 'x')", id="ends-with"),
            pytest.param("doc.f", "doc.f.:Bool", id="bare-path-is-a-bool"),
            pytest.param("!doc.f && doc.g", "NOT doc.f.:Bool AND doc.g.:Bool", id="logic-on-paths"),
            pytest.param("doc.f ? 1 : 2", "if(doc.f.:Bool, 1, 2)", id="ternary-condition"),
            pytest.param("doc.a == null", "doc.a IS NULL", id="null"),
            pytest.param("has(doc.a)", "doc.a IS NOT NULL", id="has"),
            pytest.param(
                "size(doc.a) > 0",
                "coalesce(lengthUTF8(doc.a.:String), JSONArrayLength(toJSONString(doc.a))) > 0",
                id="size",
            ),
            pytest.param(
                "int(doc.a) > 1",
                "coalesce(doc.a.:Int64, accurateCastOrNull(trunc(doc.a.:Float64), 'Int64'),"
                " toInt64OrNull(doc.a.:String)) > 1",
                id="int",
            ),
            pytest.param(
                "double(doc.a) > 1.0",
                "coalesce(doc.a.:Float64, toFloat64(doc.a.:Int64), toFloat64(doc.a.:UInt64),"
                " toFloat64OrNull(doc.a.:String)) > 1.0",
                id="double",
            ),
            pytest.param(
                'string(doc.a) == "1"', "if(doc.a IS NULL, NULL, toString(doc.a)) = '1'", id="string-conversion"
            ),
            pytest.param("doc.a + 1 > 2", "doc.a.:Int64 + 1 > 2", id="int-arithmetic"),
            pytest.param("doc.a * 1.5 > 2.0", "doc.a.:Float64 * 1.5 > 2.0", id="double-arithmetic"),
            pytest.param("doc.a / 2 > 1", "intDiv(doc.a.:Int64, 2) > 1", id="int-division"),
            pytest.param(
                "doc.b.c == 1",
                "coalesce(doc.b.c.:Int64 = 1, doc.b.c.:UInt64 = 1, doc.b.c.:Float64 = 1,"
                " if(doc.b.c IS NULL, NULL, false))",
                id="nested-path",
            ),
            pytest.param(
                "doc.a > double(limit)",
                "coalesce(doc.a.:Int64 > toFloat64(limit), doc.a.:UInt64 > toFloat64(limit),"
                " doc.a.:Float64 > toFloat64(limit))",
                id="typed-expression",
            ),
            pytest.param("other.a == 1", "other.a = 1", id="other-columns-unchanged"),
            pytest.param("doc == 1", "doc = 1", id="the-column-itself-unchanged"),
        ],
    )
    def test_emits(self, expr, sql):
        assert transpile_to_clickhouse(expr, json_columns=["doc"]) == sql

    @pytest.mark.parametrize(
        "expr",
        [
            pytest.param("doc.a == doc.b", id="two-paths"),
            pytest.param("doc.a == limit", id="untyped-identifier"),
            pytest.param("doc.a in [1, limit]", id="untyped-list-element"),
            pytest.param("doc.a + doc.b > 1", id="untyped-arithmetic"),
            pytest.param("-doc.a > 1", id="negated-path"),
        ],
    )
    def test_a_type_only_the_data_decides_is_left_to_evaluate(self, expr):
        with pytest.raises(TranspileError, match="no fixed type|both JSON paths"):
            transpile_to_clickhouse(expr, json_columns=["doc"])

    def test_without_json_columns_a_path_is_read_as_is(self):
        assert transpile_to_clickhouse("doc.a == 42") == "doc.a = 42"
