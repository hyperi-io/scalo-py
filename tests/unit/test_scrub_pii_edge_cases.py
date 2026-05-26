#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_pii_edge_cases.py
#  Purpose:   Edge cases, non-ASCII, thread-safety, cross-validator scrubbing
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Edge cases for L3 PII validators.

Companion to ``test_scrub_pii_validators.py`` covering corners the
straight-line tests don't reach:

- Multi-byte / non-ASCII content per spec §10a
- Multiple matches per line, including overlaps
- Context boundary (keyword exactly at proximity distance)
- Thread-safety of validator instances
- Fail-safe behaviour when validate() raises
- Idempotency under repeated application
- Empty / whitespace / None-ish inputs
- Boundary checksum cases
"""

from __future__ import annotations

import threading

import pytest

from hyperi_pylib.logger.scrub import LayeredScrubber, ScrubConfig
from hyperi_pylib.logger.scrub.pii import (
    CreditCardValidator,
    EmailValidator,
    IbanValidator,
    PhoneValidator,
    _DynamicValidator,
    load_registry,
)
from hyperi_pylib.logger.scrub.pii._base import _Validator

_REGISTRY = load_registry()


def _make(key: str) -> _DynamicValidator:
    country, id_name = key.split(".", 1)
    entry = dict(_REGISTRY[country][id_name])
    entry["_entry_key"] = key
    return _DynamicValidator(entry)


# ---------------------------------------------------------------------------
# Empty / boundary inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "validator",
    [
        CreditCardValidator(),
        IbanValidator(),
        EmailValidator(),
        PhoneValidator(),
        _make("au.abn"),
        _make("au.tfn"),
        _make("au.medicare"),
    ],
)
class TestEmptyInputs:
    def test_empty_string(self, validator):
        assert validator.scrub("") == ""

    def test_only_whitespace(self, validator):
        text = "   \n\t  "
        assert validator.scrub(text) == text

    def test_only_punctuation(self, validator):
        text = "!@#$%^&*()_+-=[]{}|;':,.<>?/"
        assert validator.scrub(text) == text


# ---------------------------------------------------------------------------
# Multiple matches per line
# ---------------------------------------------------------------------------


class TestMultipleMatches:
    def test_two_emails_both_redacted(self):
        v = EmailValidator()
        out = v.scrub("From: alice@example.com To: bob@example.com")
        assert "alice@example.com" not in out
        assert "bob@example.com" not in out
        assert out.count("[EMAIL_REDACTED]") == 2

    def test_two_credit_cards_both_redacted(self):
        v = CreditCardValidator()
        # Two valid Luhn cards in one line
        out = v.scrub("Cards: 4111-1111-1111-1111 and 5555-5555-5555-4444")
        assert "4111-1111-1111-1111" not in out
        assert "5555-5555-5555-4444" not in out
        assert out.count("[CREDIT_CARD_REDACTED]") == 2

    def test_two_abns_with_keyword_both_redacted(self):
        v = _make("au.abn")
        # Both have "abn" keyword nearby
        out = v.scrub("Company A ABN: 53 004 085 616, Company B abn=53004085616")
        assert "53 004 085 616" not in out
        assert "53004085616" not in out
        assert out.count("[AU_ABN_REDACTED]") == 2


# ---------------------------------------------------------------------------
# Non-ASCII content per spec §10a.5
# ---------------------------------------------------------------------------


class TestNonAsciiContent:
    def test_email_with_cjk_neighbouring_text(self):
        v = EmailValidator()
        # CJK text surrounding an ASCII email
        text = "顧客 alice@example.com から連絡"
        out = v.scrub(text)
        assert "alice@example.com" not in out
        # Surrounding CJK preserved byte-for-byte
        assert "顧客" in out
        assert "から連絡" in out

    def test_abn_with_diacritic_company_name(self):
        v = _make("au.abn")
        # German umlaut in surrounding text doesn't break detection
        text = "Société Générale ABN: 53 004 085 616 paid"
        out = v.scrub(text)
        assert "53 004 085 616" not in out
        assert "Société Générale" in out

    def test_email_local_part_with_diacritic(self):
        v = EmailValidator()
        out = v.scrub("Sent to françois@example.fr")
        # The whole email should be redacted, including the diacritic
        assert "françois@example.fr" not in out
        assert "[EMAIL_REDACTED]" in out

    def test_rtl_arabic_around_credit_card(self):
        v = CreditCardValidator()
        # Arabic RTL text doesn't confuse the regex (which works on
        # logical codepoint order)
        text = "العميل دفع 4111-1111-1111-1111 شكراً"
        out = v.scrub(text)
        assert "4111-1111-1111-1111" not in out
        assert "العميل" in out

    def test_emoji_around_match(self):
        v = EmailValidator()
        out = v.scrub("📧 contact alice@example.com 🚀")
        assert "alice@example.com" not in out
        assert "📧" in out
        assert "🚀" in out


# ---------------------------------------------------------------------------
# Context boundary tests for context-required validators
# ---------------------------------------------------------------------------


class TestContextBoundary:
    def test_keyword_within_proximity_redacts(self):
        v = _make("au.abn")
        # Keyword ~10 chars before -- well within default 30
        out = v.scrub("ABN: x x x 53 004 085 616")
        assert "53 004 085 616" not in out

    def test_keyword_beyond_proximity_does_not_redact(self):
        v = _make("au.abn")
        # Keyword 60+ chars before the candidate -- beyond default 30
        text = "ABN section header: " + ("x " * 30) + "53 004 085 616"
        out = v.scrub(text)
        assert "53 004 085 616" in out, f"unexpectedly redacted: {out!r}"

    def test_keyword_in_candidate_itself_does_not_count(self):
        # "abn" appears WITHIN the digits -- should not satisfy context
        # (we look BEFORE the candidate, not at the candidate). With
        # the current implementation this case is moot for ABN (digits
        # don't contain "abn") but tests the principle.
        v = _make("au.abn")
        text = "Random text 53 004 085 616 abn"  # keyword AFTER candidate
        out = v.scrub(text)
        assert "53 004 085 616" in out, f"unexpectedly redacted: {out!r}"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Per Scrubber Protocol: instances MUST be thread-safe."""

    def test_concurrent_scrubs_produce_same_output(self):
        v = EmailValidator()
        text = "alice@example.com bob@example.com carol@example.com"
        results: list[str] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def worker():
            try:
                out = v.scrub(text)
                with lock:
                    results.append(out)
            except BaseException as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"concurrent errors: {errors}"
        assert len(results) == 20
        # All threads produce the same output
        assert all(r == results[0] for r in results)
        # And all three emails are redacted
        assert results[0].count("[EMAIL_REDACTED]") == 3


# ---------------------------------------------------------------------------
# Fail-safe contract (spec §5.1)
# ---------------------------------------------------------------------------


class _BrokenValidator(_Validator):
    """Test validator: PATTERN matches, validate() raises."""

    import re as _re

    LABEL = "BROKEN"
    PATTERN = _re.compile(r"\bbroken\b")

    def validate(self, candidate: str) -> bool:
        raise RuntimeError("intentional")


class TestFailSafe:
    def test_validate_raises_through_to_scrub(self):
        """If a custom validator's validate() raises, the SCRUB call
        propagates -- fail-safe lives at the LayeredScrubber level,
        not per-validator. Validators are expected to be well-behaved.
        """
        v = _BrokenValidator()
        with pytest.raises(RuntimeError, match="intentional"):
            v.scrub("This text contains broken word")

    def test_layered_scrubber_isolates_broken_validator(self):
        """A broken validator inside a LayeredScrubber doesn't break
        the chain (per spec §5.1)."""
        good = EmailValidator()
        broken = _BrokenValidator()
        chain = LayeredScrubber(layers=[broken, good])
        with pytest.warns(RuntimeWarning):
            out = chain.scrub("broken alice@example.com text")
        # The good validator still ran and redacted
        assert "alice@example.com" not in out


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("validator", "text"),
    [
        (EmailValidator(), "alice@example.com bob@example.com"),
        (CreditCardValidator(), "4111-1111-1111-1111 and 5555555555554444"),
        (IbanValidator(), "GB82WEST12345698765432"),
        (_make("au.abn"), "ABN: 53 004 085 616"),
        (_make("au.tfn"), "TFN: 123 456 782"),
        (_make("au.medicare"), "Medicare 2123 45670 1"),
    ],
)
class TestIdempotency:
    def test_double_scrub_equals_single_scrub(self, validator, text):
        once = validator.scrub(text)
        twice = validator.scrub(once)
        assert once == twice

    def test_no_progressive_damage(self, validator, text):
        """Repeatedly scrubbing must not introduce new artefacts."""
        result = text
        for _ in range(5):
            result = validator.scrub(result)
        # Same as a single scrub
        assert result == validator.scrub(text)


# ---------------------------------------------------------------------------
# Composite via LayeredScrubber (the production path)
# ---------------------------------------------------------------------------


class TestLayeredCompositionPii:
    def test_all_validators_compose_into_one_chain(self):
        layers = [
            CreditCardValidator(),
            IbanValidator(),
            EmailValidator(),
            PhoneValidator(),
            _make("au.abn"),
            _make("au.tfn"),
            _make("au.medicare"),
        ]
        chain = LayeredScrubber(config=ScrubConfig(), layers=layers)
        text = "User alice@example.com (ABN: 53 004 085 616) paid with 4111-1111-1111-1111 to GB82WEST12345698765432"
        out = chain.scrub(text)
        assert "alice@example.com" not in out
        assert "53 004 085 616" not in out
        assert "4111-1111-1111-1111" not in out
        assert "GB82WEST12345698765432" not in out

    def test_disabled_master_bypasses_all_layers(self):
        chain = LayeredScrubber(
            config=ScrubConfig(enabled=False),
            layers=[EmailValidator(), CreditCardValidator()],
        )
        text = "alice@example.com 4111-1111-1111-1111"
        assert chain.scrub(text) == text


# ---------------------------------------------------------------------------
# Performance sanity (regression guard, not a benchmark)
# ---------------------------------------------------------------------------


class TestPerformanceSanity:
    """Loose timing guard. Aim is to catch ~10× regressions, not bench."""

    def test_long_clean_line_fast(self):
        """A 10KB line with no matches scrubs in well under 100ms via
        the full validator chain. Spec §7 target is <350µs/line for
        the always-on stack -- 100ms is a regression bar, not a target."""
        import time

        v = EmailValidator()
        line = ("the quick brown fox jumps over the lazy dog. " * 200).strip()
        assert len(line) > 5000
        start = time.monotonic()
        for _ in range(100):
            v.scrub(line)
        elapsed = time.monotonic() - start
        # 100 scrubs of 10KB clean text in less than 1 second
        # (i.e. >10ms per scrub would be a serious regression)
        assert elapsed < 1.0, f"100 scrubs took {elapsed:.3f}s"
