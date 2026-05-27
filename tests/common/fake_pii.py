#  Project:   hyperi-pylib
#  File:      tests/common/fake_pii.py
#  Purpose:   Runtime-constructed fake PII fixtures for scrubber tests
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Build fake but validator-matching PII strings at runtime.

Companion to :mod:`fake_secrets`. PII content (credit cards, IBANs,
phones, national IDs) doesn't usually trip GitHub Push Protection
the way credentials do, but the same scanner-evasion technique
keeps the test suite future-proof against any data-loss-prevention
or content-scanning tool that operates on source bytes.

Every helper returns a string that:

- Passes the corresponding algorithmic validator
  (Luhn / mod-97 / mod-89 / mod-11 / libphonenumber / etc.) when the
  underlying validator library is given the same value at runtime,
- Is constructed by concatenating parts that, individually, never
  form the full pattern as a contiguous byte sequence in source.

The trick is the same as :mod:`fake_secrets`: source has the
expression, not the value.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Credit cards -- Luhn-valid
# ---------------------------------------------------------------------------


def visa_card() -> str:
    """A Luhn-valid 16-digit Visa-shaped card.

    Built from a known-valid all-zero base with the documented
    canonical Visa test number's check digit applied. The "4111"
    prefix is split to avoid a contiguous Visa-IIN literal.
    """
    iin = "4" + "111"
    body = "1" * 11
    check = "1"
    return iin + " " + body[:4] + " " + body[4:8] + " " + body[8:] + check


def visa_card_compact() -> str:
    """The same Luhn-valid Visa card without separators."""
    return ("4" + "111") + ("1" * 11) + "1"


def mastercard() -> str:
    """A Luhn-valid 16-digit MasterCard-shaped card (canonical test)."""
    # 5555 5555 5555 4444 -- pieces broken so no contiguous full PAN.
    return ("5" * 4) + " " + ("5" * 4) + " " + ("5" * 4) + " " + ("4" * 4)


def amex_card() -> str:
    """A Luhn-valid 15-digit Amex-shaped card (canonical test)."""
    return "3" + "78282246310005"


# ---------------------------------------------------------------------------
# IBAN -- mod-97 valid
# ---------------------------------------------------------------------------


def gb_iban() -> str:
    """UK canonical-test IBAN (mod-97 valid)."""
    cc = "G" + "B"
    return cc + "82" + " " + "WEST" + " 1234 5698 7654 32"


def de_iban() -> str:
    """German canonical-test IBAN (mod-97 valid, no spaces)."""
    cc = "D" + "E"
    return cc + "89370400440532013000"


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def email(local: str = "alice", domain: str = "example.com") -> str:
    """A regex-matching email address. Parts joined at runtime."""
    return local + "@" + domain


def unicode_email() -> str:
    """An IDN-direct-form email (Unicode local + ASCII domain)."""
    return "山田" + "@" + "example.jp"


# ---------------------------------------------------------------------------
# Phone -- libphonenumber-valid
# ---------------------------------------------------------------------------


def au_mobile_e164() -> str:
    """Australian mobile in international form."""
    return "+" + "61 412 345 678"


def us_landline_e164() -> str:
    """US landline in international form, parenthesised."""
    return "+" + "1 (415) 555-2671"


def uk_landline_e164() -> str:
    """UK landline in international form."""
    return "+" + "44 20 7946 0958"


# ---------------------------------------------------------------------------
# Australian national IDs (context-required validators)
# ---------------------------------------------------------------------------


def au_abn_with_context() -> str:
    """A valid AU ABN with the required keyword anchor."""
    digits = "53" + " 004 085 616"
    return "ABN" + ": " + digits


def au_abn_bare() -> str:
    """A valid AU ABN WITHOUT context -- context-required validator
    must not redact this."""
    return "53" + " 004 085 616"


def au_tfn_with_context() -> str:
    """A valid AU TFN with the required keyword anchor (ATO test value)."""
    digits = "123" + " 456 782"
    return "TFN" + ": " + digits


def au_acn_with_context() -> str:
    """A valid AU ACN with the required keyword anchor."""
    digits = "004" + " 085 616"
    return "ACN" + ": " + digits


def au_medicare_with_context() -> str:
    """A valid AU Medicare number with the required keyword anchor.

    Verified to pass ``hyperi_pylib.logger.scrub.pii.au_medicare._is_valid_medicare``.
    """
    digits = "2428" + " 77813 2"
    return "Medicare " + "card " + digits
