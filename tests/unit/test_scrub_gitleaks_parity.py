#  Project:   scalo
#  File:      tests/unit/test_scrub_gitleaks_parity.py
#  Purpose:   The L1 scrubber redacts what gitleaks reports and leaves what it allows
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Gitleaks' own rule vectors, plus the allowlist and entropy semantics on small rules.

``tests/fixtures/patterns/gitleaks_vectors.json`` holds the true and false positives
each upstream rule asserts about itself, compressed because GitHub push protection
rejects them in clear. A true positive has to be redacted and a false positive has to
come through unchanged, with the rule's entropy and allowlists and the global allowlist
applied.
"""

import base64
import json
import math
import zlib
from pathlib import Path
from typing import Any

import pytest

from scalo.logger.scrub.gitleaks_toml import GitleaksTomlScrubber, _shannon_entropy

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "patterns" / "gitleaks_vectors.json"


def _load_vectors() -> dict[str, dict[str, list[str]]]:
    packed = json.loads(_FIXTURE.read_text(encoding="utf-8"))["data"]
    return json.loads(zlib.decompress(base64.b64decode("".join(packed))))


_VECTORS = _load_vectors()


def _preview(vectors: list[str]) -> str:
    return "\n".join(f"  {v[:100]!r}" for v in vectors[:5])


@pytest.mark.parametrize("rule_id", sorted(_VECTORS))
def test_rule_agrees_with_gitleaks_on_its_own_vectors(rule_id: str) -> None:
    scrubber = GitleaksTomlScrubber(rule_ids={rule_id})
    assert scrubber.rule_count == 1
    vectors = _VECTORS[rule_id]
    missed = [tp for tp in vectors["tp"] if scrubber.scrub(tp) == tp]
    flagged = [fp for fp in vectors["fp"] if scrubber.scrub(fp) != fp]
    assert not missed, f"{rule_id}: {len(missed)} true positives left unredacted, first:\n{_preview(missed)}"
    assert not flagged, f"{rule_id}: {len(flagged)} false positives redacted, first:\n{_preview(flagged)}"


def _scrubber(rule: dict[str, Any], **kwargs: Any) -> GitleaksTomlScrubber:
    return GitleaksTomlScrubber(rules=[{"id": "r", "regex": r"tok-([a-z0-9]{8})", **rule}], **kwargs)


class TestEntropy:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [("", 0.0), ("aaaa", 0.0), ("abab", 1.0), ("abcd", 2.0), ("abcdefgh", 3.0)],
    )
    def test_shannon_entropy(self, data: str, expected: float) -> None:
        assert _shannon_entropy(data) == pytest.approx(expected)

    def test_frequencies_divide_by_the_utf8_byte_length(self) -> None:
        # Two code points over three bytes, as gitleaks reckons it, not 1.0 over two.
        assert _shannon_entropy("a\u00e9") == pytest.approx(-2 * (1 / 3) * math.log2(1 / 3))

    @pytest.mark.parametrize(
        ("secret", "entropy", "redacted"),
        [
            ("tok-aaaaaaaa", 2.0, False),
            ("tok-abcdefgh", 3.0, False),  # exactly at the threshold: gitleaks drops entropy <= threshold
            ("tok-abcdefgh", 2.9, True),
            ("tok-abcdefgh", 0.0, True),  # no entropy declared: never checked
            ("tok-aaaaaaaa", 0.0, True),
        ],
    )
    def test_threshold(self, secret: str, entropy: float, redacted: bool) -> None:
        text = f"x {secret} y"
        out = _scrubber({"entropy": entropy}).scrub(text)
        assert (out != text) is redacted

    def test_entropy_is_taken_over_the_secret_group_not_the_whole_match(self) -> None:
        # "tok-" adds variety the group does not have, so a whole-match reading would pass it.
        text = "tok-aaaaaaaa"
        assert _scrubber({"entropy": 1.0}).scrub(text) == text


class TestAllowlists:
    def test_regex_allowlist_tests_the_secret_by_default(self) -> None:
        scrubber = _scrubber({"allowlists": [{"regexes": ["^abc"]}]})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"
        assert scrubber.scrub("tok-xbcdefgh") != "tok-xbcdefgh"

    def test_match_target_sees_the_whole_match(self) -> None:
        scrubber = _scrubber({"allowlists": [{"regexTarget": "match", "regexes": ["^tok-abc"]}]})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"
        # The same regex against the secret alone would have missed the prefix.
        by_secret = _scrubber({"allowlists": [{"regexes": ["^tok-abc"]}]})
        assert by_secret.scrub("tok-abcdefgh") != "tok-abcdefgh"

    def test_line_target_sees_the_surrounding_line_only(self) -> None:
        scrubber = _scrubber({"allowlists": [{"regexTarget": "line", "regexes": ["docs example"]}]})
        assert scrubber.scrub("docs example: tok-abcdefgh") == "docs example: tok-abcdefgh"
        text = "docs example\ntok-abcdefgh"
        assert scrubber.scrub(text) != text

    def test_stopword_matches_the_secret_case_insensitively(self) -> None:
        scrubber = _scrubber({"allowlists": [{"stopwords": ["BCD"]}]})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"
        assert scrubber.scrub("tok-azzzzzzz") != "tok-azzzzzzz"

    def test_or_condition_allows_on_either_check(self) -> None:
        scrubber = _scrubber({"allowlists": [{"regexes": ["^zz"], "stopwords": ["bcd"]}]})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"
        assert scrubber.scrub("tok-zzzzzzzz") == "tok-zzzzzzzz"
        assert scrubber.scrub("tok-qqqqqqqq") != "tok-qqqqqqqq"

    def test_and_condition_needs_every_check(self) -> None:
        scrubber = _scrubber({"allowlists": [{"condition": "AND", "regexes": ["^abc"], "stopwords": ["fgh"]}]})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"
        assert scrubber.scrub("tok-abcdezzz") != "tok-abcdezzz"
        assert scrubber.scrub("tok-xxxdefgh") != "tok-xxxdefgh"

    def test_and_condition_with_paths_never_applies_to_text(self) -> None:
        allowlist = {"condition": "AND", "regexes": ["^abc"], "paths": [r"\.txt$"]}
        scrubber = _scrubber({"allowlists": [allowlist]})
        assert scrubber.scrub("tok-abcdefgh") != "tok-abcdefgh"

    def test_or_condition_ignores_paths(self) -> None:
        scrubber = _scrubber({"allowlists": [{"paths": [r"\.txt$"], "regexes": ["^abc"]}]})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"

    def test_paths_only_allowlist_excuses_nothing(self) -> None:
        scrubber = _scrubber({"allowlists": [{"paths": [r"\.txt$"]}]})
        assert scrubber.scrub("tok-abcdefgh") != "tok-abcdefgh"

    def test_any_one_allowlist_is_enough(self) -> None:
        scrubber = _scrubber({"allowlists": [{"regexes": ["^nope"]}, {"stopwords": ["bcd"]}]})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"

    def test_older_single_allowlist_table_is_honoured(self) -> None:
        scrubber = _scrubber({"allowlist": {"regexes": ["^abc"]}})
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"

    def test_global_allowlist_applies_to_every_rule(self) -> None:
        other = {"id": "o", "regex": r"other-[a-z0-9]{8}"}
        rules = [{"id": "r", "regex": r"tok-([a-z0-9]{8})"}, other]
        scrubber = GitleaksTomlScrubber(rules=rules, allowlists=[{"stopwords": ["bcd"]}])
        assert scrubber.scrub("tok-abcdefgh other-abcdefgh") == "tok-abcdefgh other-abcdefgh"
        assert scrubber.scrub("tok-azzzzzzz") != "tok-azzzzzzz"

    def test_target_rules_scope_a_global_table_to_those_rules(self) -> None:
        rules = [{"id": "r", "regex": r"tok-([a-z0-9]{8})"}, {"id": "o", "regex": r"other-[a-z0-9]{8}"}]
        scrubber = GitleaksTomlScrubber(rules=rules, allowlists=[{"targetRules": ["r"], "stopwords": ["bcd"]}])
        assert scrubber.scrub("tok-abcdefgh") == "tok-abcdefgh"
        assert scrubber.scrub("other-abcdefgh") != "other-abcdefgh"

    def test_explicit_rules_get_no_global_allowlist_unless_given(self) -> None:
        assert _scrubber({}).scrub("tok-aaaaaaaa") != "tok-aaaaaaaa"

    def test_bundled_global_allowlist_excuses_a_placeholder(self) -> None:
        # The bundled list allows ${VAR} style references and template placeholders.
        text = 'password = "${DB_PASSWORD}"'
        assert GitleaksTomlScrubber().scrub(text) == text

    @pytest.mark.parametrize(
        "bad",
        [
            {"condition": "XOR", "stopwords": ["bcd"]},
            {"regexTarget": "nowhere", "stopwords": ["bcd"]},
            {"description": "no checks at all"},
        ],
    )
    def test_unusable_allowlist_is_skipped_with_a_warning_and_excuses_nothing(self, bad: dict[str, Any]) -> None:
        with pytest.warns(RuntimeWarning, match="Ignoring it"):
            scrubber = _scrubber({"allowlists": [bad]})
        assert scrubber.scrub("tok-abcdefgh") != "tok-abcdefgh"

    def test_allowlist_regex_that_does_not_compile_excuses_nothing(self) -> None:
        scrubber = _scrubber({"allowlists": [{"regexes": ["[unclosed"], "stopwords": ["bcd"]}]})
        with pytest.warns(RuntimeWarning, match="did not compile"):
            out = scrubber.scrub("tok-abcdefgh")
        assert out != "tok-abcdefgh"
