# Project:   scalo
# File:      tests/unit/test_expression/test_profile.py
# Purpose:   Tests for the CEL Fast profile scanner and its config
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the expression profile: what it refuses, where, and what unlocks it."""

import os
import subprocess
import sys

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


class TestWhitespaceBeforeTheParen:
    """CEL allows whitespace between a function name and its call, so the scan must too."""

    @pytest.mark.parametrize("gap", [" ", "\t", "\r", "\n", "\f", "\v", " \t\n "], ids=repr)
    def test_any_ascii_whitespace_before_the_paren_is_still_a_call(self, gap):
        regex = validate(f'name.matches{gap}("^w")')
        iteration = validate(f"[1, 2].map{gap}(x, x)")
        assert len(regex) == 1, regex
        assert "matches()" in regex[0]
        assert len(iteration) == 1, iteration
        assert "map()" in iteration[0]

    def test_the_span_still_covers_only_the_name(self):
        from scalo.expression import scan_profile

        expr = "x.map\n\t (a, a)"
        found = scan_profile(expr)
        assert len(found) == 1
        assert found[0].span is not None
        assert _covered(expr, found[0].span) == "map"


RESTRICTED_CALLS = {
    "matches": ("x.", '"a"'),
    "map": ("[1].", "v, v"),
    "filter": ("[1].", "v, v > 0"),
    "exists_one": ("[1].", "v, v > 0"),
    "existsOne": ("[1].", "v, v > 0"),
    "timestamp": ("", '"2024-01-01T00:00:00Z"'),
    "duration": ("", '"1h"'),
}

# Each hides the restricted call from a scanner that reads literals or comments differently from CEL.
LEXER_FORMS = {
    "raw r double": 'r"\\" == "x" || {call}',
    "raw R double": 'R"\\" == "x" || {call}',
    "raw r single": "r'\\' == 'x' || {call}",
    "raw R single": "R'\\' == 'x' || {call}",
    "raw triple double": 'r"""\\""" == "x" || {call}',
    "raw triple single": "r'''\\''' == 'x' || {call}",
    "triple double": '"""a"b""" == "x" || {call}',
    "triple single": "'''a'b''' == 'x' || {call}",
    "raw bytes br": 'br"\\" == b"x" || {call}',
    "raw bytes bR": 'bR"\\" == b"x" || {call}',
    "raw bytes Br": 'Br"\\" == b"x" || {call}',
    "raw bytes BR single": "BR'\\' == b'x' || {call}",
    "bytes triple": 'b"""a"b""" == b"x" || {call}',
    "comment holding a quote": '1 == 1 // "\n || {call}',
    "comment before the paren": "{gap://\n}",
    "spaced comment before the paren": "{gap: // note\n}",
    "comment line before the paren": "{gap:\n// note\n }",
}


def _lexer_case(form: str, name: str) -> str:
    receiver, args = RESTRICTED_CALLS[name]
    template = LEXER_FORMS[form]
    if template.startswith("{gap:"):
        return f"{receiver}{name}{template[5:-1]}({args})"
    return template.replace("{call}", f"{receiver}{name}({args})")


class TestLexerForms:
    """String literals and comments are read the way cel-rust's lexer reads them."""

    @pytest.mark.parametrize("name", list(RESTRICTED_CALLS))
    @pytest.mark.parametrize("form", list(LEXER_FORMS))
    def test_no_literal_or_comment_form_hides_a_restricted_call(self, form, name):
        import cel

        expr = _lexer_case(form, name)
        cel.compile(expr)  # the form is valid CEL, so the call runs unless the profile refuses it
        errors = validate(expr)
        assert any(f"'{name}()'" in error for error in errors), (expr, errors)

    @pytest.mark.parametrize(
        "expr",
        [
            'r"map(" == "x"',
            '"""a"b map( c""" == "x"',
            "'''x.matches('a')''' == 'x'",
            'br"duration(" == b"x"',
            "x == 1 // map(v, v)",
            'x == 1 // "\n',
        ],
        ids=repr,
    )
    def test_a_call_inside_a_literal_or_comment_is_not_scanned(self, expr):
        assert validate(expr) == [], expr

    def test_the_scan_finds_every_restricted_function_cel_parses(self):
        import random

        import cel

        from scalo.expression import ProfileConfig, scan_profile

        # cel's own parser reports the functions it read, so it is the reference for the lexer.
        pieces = ['"', "'", '"""', "'''", "r", "R", "b", "B", "br", "\\", "//", "\n", " ", "a", "==", "||", "(", ")"]
        calls = ['x.matches("a")', 'timestamp("2024-01-01T00:00:00Z")', 'duration("1h")', 'x.matches//\n("a")']
        shapes = ['{h} == "x" || {c}', "{h} || {c}", "{c} || {h}", "[{h}] == [] || {c}"]
        rng = random.Random(20261021)
        checked = 0
        for _ in range(30000):
            head = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 10)))
            expr = rng.choice(shapes).format(h=head, c=rng.choice(calls))
            try:
                used = {"matches", "timestamp", "duration"} & set(cel.compile(expr).functions())
            except ValueError:
                continue
            checked += 1
            flagged = {d.message.split("'")[1].removesuffix("()") for d in scan_profile(expr, ProfileConfig())}
            assert used <= flagged, expr
        assert checked > 1000, checked

    def test_rb_is_a_name_then_a_plain_string_which_cel_refuses(self):
        from scalo.expression import scan_profile

        # CEL reads `rb` as a name, so the backslash escapes the quote and the string runs on.
        expr = 'rb"\\" == "x" || x.matches("a")'
        assert scan_profile(expr) == []
        assert validate(expr) != [], "a name followed by a string does not parse"


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

    @pytest.mark.parametrize("name", ["exists", "exists_one", "existsOne"])
    def test_every_spelling_of_exists_one_is_iteration(self, name):
        from scalo.expression import ProfileConfig, compile_expression, scan_profile

        expr = f"[1, 2].{name}(v, v > 1)"
        refused = scan_profile(expr, ProfileConfig())
        assert len(refused) == 1, refused
        assert "allow_iteration" in refused[0].message
        allowed = ProfileConfig(allow_iteration=True)
        assert scan_profile(expr, allowed) == []
        assert compile_expression(expr, allowed).execute({}) is True


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


class TestSpanOffsets:
    """A byte span converts to the character and UTF-16 offsets a UI indexes by."""

    EXPR = 'label == "été 😀" && x.map(a, a)'

    def test_a_span_after_non_ascii_text_converts_to_each_unit(self):
        from scalo.expression import Span, diagnose

        found = diagnose(self.EXPR)
        assert len(found) == 1
        span = found[0].span
        # Two 2-byte characters and one 4-byte, 2-unit character precede the call.
        assert span == Span(27, 30)
        assert span.char_offsets(self.EXPR) == (22, 25)
        assert span.utf16_offsets(self.EXPR) == (23, 26)

        start, end = span.char_offsets(self.EXPR)
        assert self.EXPR[start:end] == "map"
        units = self.EXPR.encode("utf-16-le")
        start, end = span.utf16_offsets(self.EXPR)
        assert units[2 * start : 2 * end].decode("utf-16-le") == "map"

    def test_an_ascii_span_is_the_same_in_every_unit(self):
        from scalo.expression import diagnose

        expr = "severity == && x"
        span = diagnose(expr)[0].span
        assert span is not None
        assert span.char_offsets(expr) == span.utf16_offsets(expr) == (span.start, span.end) == (12, 13)

    @pytest.mark.parametrize(("start", "end"), [(11, 12), (0, 999), (5, 3)])
    def test_a_span_inside_a_character_or_outside_the_text_is_refused(self, start, end):
        from scalo.expression import Span

        with pytest.raises(ValueError):
            Span(start, end).utf16_offsets(self.EXPR)
        with pytest.raises(ValueError):
            Span(start, end).char_offsets(self.EXPR)


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
        profile._LATCH.profile = None
        try:
            assert profile.cascade_profile().allow_regex is True
            assert validate('name.matches("^w")') == []
        finally:
            monkeypatch.delenv("EXPRESSION__ALLOW_REGEX")
            settings.reload()
            profile._LATCH.profile = None
        assert profile.cascade_profile().allow_regex is False

    def test_the_default_is_not_latched_before_the_cascade_supplies_a_profile(self, tmp_path):
        # A fresh interpreter, so no earlier test has read the profile.
        program = (
            "import os\n"
            "from scalo.config import settings\n"
            "from scalo.expression.profile import cascade_profile\n"
            "early = cascade_profile().allow_regex\n"
            "os.environ['EXPRESSION__ALLOW_REGEX'] = 'true'\n"
            "settings.reload()\n"
            "supplied = cascade_profile().allow_regex\n"
            "del os.environ['EXPRESSION__ALLOW_REGEX']\n"
            "settings.reload()\n"
            "kept = cascade_profile().allow_regex\n"
            "print(early, supplied, kept)\n"
        )
        env = {key: value for key, value in os.environ.items() if not key.startswith("EXPRESSION")}
        result = subprocess.run(
            [sys.executable, "-c", program],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        # The early default is not kept, and once the cascade supplied a profile it is.
        assert result.stdout.split() == ["False", "True", "True"], result.stdout
