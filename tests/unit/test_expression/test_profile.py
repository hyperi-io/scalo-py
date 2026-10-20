# Project:   scalo
# File:      tests/unit/test_expression/test_profile.py
# Purpose:   Tests for the CEL Fast profile scanner and its config
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the expression profile: what it refuses, where, and what unlocks it."""

import pytest

from scalo.expression import validate


class TestRegexIsRestricted:
    """``matches()`` has unbounded cost per record, so the default profile refuses it."""

    def test_matches_is_refused_by_default(self):
        errors = validate('name.matches("^web-[0-9]+$")')
        assert len(errors) == 1, errors
        assert "matches()" in errors[0]
        assert "allow_regex" in errors[0]

    def test_allow_regex_unlocks_matches(self):
        from scalo.expression import ProfileConfig

        assert validate('name.matches("^web-[0-9]+$")', profile=ProfileConfig(allow_regex=True)) == []

    def test_allow_regex_leaves_iteration_blocked(self):
        from scalo.expression import ProfileConfig

        errors = validate("[1, 2].map(x, x)", profile=ProfileConfig(allow_regex=True))
        assert len(errors) == 1
        assert "map()" in errors[0]


class TestStringLiteralsAreNotScanned:
    """A function name inside a quoted value is data, not a call."""

    @pytest.mark.parametrize(
        "expr",
        [
            'msg.contains("map(x)")',
            "msg.contains('filter(')",
            r'msg.contains("filter\"(")',
            'label == "timestamp(now)"',
            'msg.contains("nosuch(")',
        ],
    )
    def test_a_call_inside_a_string_literal_is_not_scanned(self, expr):
        assert validate(expr) == [], expr

    def test_a_real_call_after_a_string_is_still_caught(self):
        errors = validate('"ok(" + items.map(x, x)')
        assert len(errors) == 1
        assert "map()" in errors[0]


def _covered(expr: str, span) -> str:
    return expr.encode()[span.start : span.end].decode()


class TestScanSpans:
    """Each finding carries the byte range of the function name."""

    def test_spans_cover_the_function_name(self):
        from scalo.expression import scan_profile

        expr = 'host.startsWith("w") && name.matches("^x") || nosuch(y)'
        assert [_covered(expr, d.span) for d in scan_profile(expr)] == ["matches", "nosuch"]

    def test_a_span_after_a_string_literal_is_the_calls_own(self):
        from scalo.expression import scan_profile

        expr = 'msg.contains("map(") && x.map(a, a)'
        found = scan_profile(expr)
        assert len(found) == 1
        assert found[0].span is not None
        assert found[0].span.start == expr.rfind("map")

    def test_check_profile_is_the_scan_without_spans(self):
        from scalo.expression import check_profile, scan_profile

        expr = "[1].map(x, x) && bogus(z)"
        assert check_profile(expr) == [d.message for d in scan_profile(expr)]

    def test_every_category_unlocked_still_refuses_an_unknown_function(self):
        from scalo.expression import ProfileConfig, scan_profile

        everything = ProfileConfig(allow_regex=True, allow_iteration=True, allow_time=True)
        assert everything.blocked_functions() == frozenset()
        assert scan_profile('name.matches("x") && [1].map(x, x)', everything) == []
        assert len(scan_profile("nosuchfunc(x)", everything)) == 1


class TestDiagnose:
    """diagnose() is validate() with a byte span on each finding."""

    def test_a_valid_expression_has_no_findings(self):
        from scalo.expression import diagnose

        assert diagnose('severity == "high"') == []

    def test_a_syntax_error_spans_the_character_the_parser_stopped_at(self):
        from scalo.expression import diagnose

        expr = "severity == && x"
        found = diagnose(expr)
        assert len(found) == 1
        assert "Syntax error" in found[0].message
        assert _covered(expr, found[0].span) == "&"

    def test_a_profile_finding_comes_before_parsing(self):
        from scalo.expression import diagnose

        expr = 'x.matches("a") &&'
        found = diagnose(expr)
        assert len(found) == 1
        assert _covered(expr, found[0].span) == "matches"

    def test_an_empty_expression_has_no_span(self):
        from scalo.expression import diagnose

        found = diagnose("  ")
        assert len(found) == 1
        assert found[0].span is None

    def test_every_parser_error_is_reported(self):
        from scalo.expression import diagnose

        expr = "x == 'unterminated"
        assert len(diagnose(expr)) == 2

    def test_a_syntax_error_on_a_later_line_counts_the_lines_before_it(self):
        from scalo.expression import diagnose

        expr = "a ==\n  b &&"
        found = diagnose(expr)
        assert found[0].span is not None
        assert found[0].span.start == len(expr.encode())


class TestSpanAt:
    """Parser positions are line and column from 1, columns in characters."""

    def test_a_position_on_the_first_line_maps_to_its_byte(self):
        from scalo.expression.diagnostic import Span, span_at

        assert span_at("abc def", 1, 5) == Span(4, 5)

    def test_a_position_on_a_later_line_counts_the_lines_before_it(self):
        from scalo.expression.diagnostic import Span, span_at

        assert span_at("a ==\n  b &&", 2, 3) == Span(7, 8)

    def test_a_column_counts_characters_not_bytes(self):
        from scalo.expression.diagnostic import Span, span_at

        expr = 'x == "é" &&'
        span = span_at(expr, 1, 10)
        assert span == Span(10, 11)
        assert _covered(expr, span) == "&"

    def test_a_position_past_the_line_points_at_its_end(self):
        from scalo.expression.diagnostic import Span, span_at

        assert span_at("ab", 1, 9) == Span(2, 2)

    def test_an_unset_position_has_no_span(self):
        from scalo.expression.diagnostic import span_at

        assert span_at("ab", 0, 0) is None
        assert span_at("ab", 3, 1) is None


class TestProfileConfig:
    def test_a_section_sets_the_flags(self):
        from scalo.expression import ProfileConfig

        assert ProfileConfig.from_mapping({"allow_regex": True, "other": 1}) == ProfileConfig(allow_regex=True)
        assert ProfileConfig.from_mapping(None) == ProfileConfig()

    @pytest.mark.parametrize("raw", [{"allow_regex": "yes"}, {"allow_time": 1}, ["allow_regex"]])
    def test_a_flag_that_is_not_a_boolean_is_refused(self, raw):
        from scalo.expression import ProfileConfig

        with pytest.raises(ValueError, match="expression"):
            ProfileConfig.from_mapping(raw)

    def test_the_cascade_section_sets_the_default_profile(self, monkeypatch: pytest.MonkeyPatch):
        from scalo.config import settings
        from scalo.expression import profile

        monkeypatch.setenv("EXPRESSION__ALLOW_REGEX", "true")
        settings.reload()
        profile._read_cascade_profile.cache_clear()
        try:
            assert profile.cascade_profile().allow_regex is True
            assert validate('name.matches("^w")') == []
        finally:
            monkeypatch.delenv("EXPRESSION__ALLOW_REGEX")
            settings.reload()
            profile._read_cascade_profile.cache_clear()
        assert profile.cascade_profile().allow_regex is False
