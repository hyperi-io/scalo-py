#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_pii_validators.py
#  Purpose:   Tests for L3 PII validators (strong-structural + context-required)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the L3 PII validators per spec §9.

Two tiers tested separately:

- :class:`TestStrongStructural` — CC, IBAN, email, phone. Should fire
  from any context.
- :class:`TestContextRequired` — ABN, ACN, TFN, Medicare. Should
  fire only when keyword anchor is present.

Plus :class:`TestProtocolSatisfaction` — every validator satisfies
the :class:`Scrubber` Protocol.
"""

from __future__ import annotations

import pytest

from hyperi_pylib.logger.scrub import Scrubber
from hyperi_pylib.logger.scrub.pii import (
    CreditCardValidator,
    EmailValidator,
    IbanValidator,
    PhoneValidator,
    _DynamicValidator,
    load_registry,
)

# Shared registry — loaded once per module
_REGISTRY = load_registry()


def _make(key: str) -> _DynamicValidator:
    """Build a dynamic national-ID validator from the bundled TOML.

    ``key`` is ``"country.id"`` (e.g. ``"au.abn"``). Bypasses the
    ``enabled`` toggle so tests work regardless of operator config.
    """
    country, id_name = key.split(".", 1)
    entry = dict(_REGISTRY[country][id_name])
    entry["_entry_key"] = key
    return _DynamicValidator(entry)


# ---------------------------------------------------------------------------
# Protocol satisfaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("validator_factory", "label"),
    [
        (CreditCardValidator, "CREDIT_CARD"),
        (IbanValidator, "IBAN"),
        (EmailValidator, "EMAIL"),
        (PhoneValidator, "PHONE"),
        (lambda: _make("au.abn"), "AU_ABN"),
        (lambda: _make("au.acn"), "AU_ACN"),
        (lambda: _make("au.tfn"), "AU_TFN"),
        (lambda: _make("au.medicare"), "AU_MEDICARE"),
    ],
)
class TestProtocolSatisfaction:
    def test_satisfies_scrubber_protocol(self, validator_factory, label):
        assert isinstance(validator_factory(), Scrubber)

    def test_has_label_and_pattern(self, validator_factory, label):
        v = validator_factory()
        assert label == v.LABEL
        assert v.PATTERN


# ---------------------------------------------------------------------------
# Strong-structural: CC, IBAN, email, phone
# ---------------------------------------------------------------------------


class TestCreditCard:
    def setup_method(self):
        self.v = CreditCardValidator()

    def test_valid_visa(self):
        # Canonical Visa test card 4111-1111-1111-1111 (Luhn passes)
        out = self.v.scrub("Charged 4111-1111-1111-1111 today")
        assert "4111-1111-1111-1111" not in out
        assert "[CREDIT_CARD_REDACTED]" in out

    def test_valid_mastercard_no_separators(self):
        out = self.v.scrub("card 5555555555554444 expires soon")
        assert "5555555555554444" not in out

    def test_valid_amex_15_digits(self):
        # Amex test card 378282246310005 (15 digits, Luhn valid)
        out = self.v.scrub("amex 3782 822463 10005 used")
        assert "3782 822463 10005" not in out

    def test_invalid_luhn_passes_through(self):
        # Same shape, wrong Luhn — should NOT redact
        text = "Not a card 4111-1111-1111-1112"
        assert self.v.scrub(text) == text

    def test_no_card_in_text(self):
        text = "Just some random log line with no card numbers"
        assert self.v.scrub(text) == text

    def test_fires_without_keyword(self):
        # Strong-structural — no need for "card=" or similar context
        text = "4111 1111 1111 1111"
        assert "[CREDIT_CARD_REDACTED]" in self.v.scrub(text)


class TestIban:
    def setup_method(self):
        self.v = IbanValidator()

    def test_valid_gb_iban(self):
        # GB82 WEST 1234 5698 7654 32 — canonical example
        out = self.v.scrub("Wire to GB82WEST12345698765432 today")
        assert "GB82WEST12345698765432" not in out
        assert "[IBAN_REDACTED]" in out

    def test_valid_de_iban_with_spaces(self):
        out = self.v.scrub("DE89 3704 0044 0532 0130 00 received")
        # The IBAN value should not appear in the output
        assert "DE89370400440532013000" not in out.replace(" ", "")

    def test_invalid_checksum_passes_through(self):
        # GB82 with one digit changed — fails mod-97
        text = "Not an IBAN: GB82WEST12345698765431"
        assert self.v.scrub(text) == text


class TestEmail:
    def setup_method(self):
        self.v = EmailValidator()

    def test_basic_email(self):
        out = self.v.scrub("contact alice@example.com please")
        assert "alice@example.com" not in out
        assert "[EMAIL_REDACTED]" in out

    def test_email_with_plus_addressing(self):
        out = self.v.scrub("alice+work@example.com bounced")
        assert "alice+work@example.com" not in out

    def test_non_ascii_email(self):
        # IDN-like — Unicode local + ASCII domain (spec §10a.5)
        out = self.v.scrub("Sent to françois@example.fr")
        assert "françois@example.fr" not in out

    def test_no_at_no_match(self):
        text = "no email here"
        assert self.v.scrub(text) == text

    def test_fires_without_keyword(self):
        text = "alice@example.com"
        assert "[EMAIL_REDACTED]" in self.v.scrub(text)


class TestPhone:
    def setup_method(self):
        self.v = PhoneValidator()

    def test_valid_international(self):
        # +1 (US) — canonical test number
        out = self.v.scrub("Call +1 415 555 2671")
        # Validated via libphonenumber; if it accepts, we redact.
        # phonenumbers should treat +14155552671 as valid.
        assert "[PHONE_REDACTED]" in out

    def test_invalid_short_run_passes_through(self):
        # Too few digits for a real phone number
        text = "Random 123"
        assert self.v.scrub(text) == text

    def test_fires_without_keyword(self):
        out = self.v.scrub("+14155552671")
        assert "[PHONE_REDACTED]" in out


# ---------------------------------------------------------------------------
# Context-required: ABN, ACN, TFN, Medicare
# ---------------------------------------------------------------------------


class TestAbnContextRequired:
    def setup_method(self):
        self.v = _make("au.abn")

    def test_with_abn_keyword_redacts(self):
        out = self.v.scrub("Company ABN: 53 004 085 616 confirmed")
        assert "53 004 085 616" not in out
        assert "[AU_ABN_REDACTED]" in out

    def test_with_long_keyword_redacts(self):
        out = self.v.scrub("Australian Business Number 53004085616 verified")
        assert "53004085616" not in out
        assert "[AU_ABN_REDACTED]" in out

    def test_keyword_case_insensitive(self):
        out = self.v.scrub("abn=53004085616 in file")
        assert "53004085616" not in out

    def test_bare_digits_no_keyword_PASS_THROUGH(self):  # noqa: N802
        # 11-digit run with valid checksum but no context — must NOT match
        text = "Request id 53004085616 processed"
        # "request id" is in the preceding text but no ABN keyword
        result = self.v.scrub(text)
        assert "53004085616" in result, f"Got redacted: {result!r}"

    def test_invalid_checksum_with_keyword_passes_through(self):
        # Keyword present but checksum wrong — no redaction
        text = "ABN: 53 004 085 617 invalid"
        assert self.v.scrub(text) == text


class TestAcnContextRequired:
    def setup_method(self):
        self.v = _make("au.acn")

    def test_with_keyword_redacts(self):
        # 005 749 986 — valid ACN
        out = self.v.scrub("Company ACN 005 749 986 registered")
        assert "005 749 986" not in out

    def test_bare_9_digits_no_keyword_PASS_THROUGH(self):  # noqa: N802
        text = "Some 9-digit number 005749986 in a log"
        # Different word "log" — not an ACN keyword
        assert "005749986" in self.v.scrub(text)


class TestTfnContextRequired:
    def setup_method(self):
        self.v = _make("au.tfn")

    def test_with_keyword_redacts(self):
        # 123 456 782 — valid TFN
        out = self.v.scrub("Employee TFN: 123 456 782 on file")
        assert "123 456 782" not in out
        assert "[AU_TFN_REDACTED]" in out

    def test_bare_digits_no_keyword_PASS_THROUGH(self):  # noqa: N802
        # TFN's mod-11 checksum means ~9% of random 9-digit numbers
        # pass — context-requirement is critical here.
        text = "Trace id 123 456 782 logged"
        assert "123 456 782" in self.v.scrub(text)


class TestMedicareContextRequired:
    def setup_method(self):
        self.v = _make("au.medicare")

    def test_with_keyword_redacts(self):
        # 2123 45670 1 — synthetic but checksum-valid example
        # Compute a valid one: weights [1,3,7,9,1,3,7,9]
        # 2*1+1*3+2*7+3*9+4*1+5*3+6*7+7*9 = 2+3+14+27+4+15+42+63 = 170 mod 10 = 0
        # So d[8] = 0 ⇒ "21234567 0" with issue 1 ⇒ "2123 45670 1"
        out = self.v.scrub("Medicare card 2123 45670 1 confirmed")
        assert "2123 45670 1" not in out
        assert "[AU_MEDICARE_REDACTED]" in out

    def test_bare_digits_no_keyword_PASS_THROUGH(self):  # noqa: N802
        text = "ID 2123456701 logged"
        assert "2123456701" in self.v.scrub(text)

    def test_invalid_first_digit_rejected(self):
        # Medicare card numbers start with 2-6
        text = "Medicare 1234 56789 0"
        assert self.v.scrub(text) == text


# ---------------------------------------------------------------------------
# Combined: multiple validators compose into a scrubbing pipeline
# ---------------------------------------------------------------------------


class TestCompositeScrubbing:
    """Demonstrate that the validators compose cleanly with each other."""

    def test_email_and_abn_in_same_line(self):
        cc = CreditCardValidator()
        email = EmailValidator()
        abn = _make("au.abn")

        text = "Alice (alice@example.com) ABN: 53 004 085 616 - paid by 4111-1111-1111-1111"
        out = email.scrub(text)
        out = abn.scrub(out)
        out = cc.scrub(out)
        assert "alice@example.com" not in out
        assert "53 004 085 616" not in out
        assert "4111-1111-1111-1111" not in out
        assert "[EMAIL_REDACTED]" in out
        assert "[AU_ABN_REDACTED]" in out
        assert "[CREDIT_CARD_REDACTED]" in out

    def test_idempotent(self):
        # Applying the scrubber twice doesn't produce different output
        email = EmailValidator()
        text = "alice@example.com"
        once = email.scrub(text)
        twice = email.scrub(once)
        assert once == twice
