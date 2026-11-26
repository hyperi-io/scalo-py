#  Project:   scalo
#  File:      src/scalo/logger/scrub/pii/credit_card.py
#  Purpose:   Credit card validator (Luhn via python-stdnum)
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Credit card validator.

Detects 13-19 digit runs with optional separators and validates via Luhn
(ISO/IEC 7812-1 Annex B). A Luhn pass alone is not enough, because ids and
epoch timestamps pass it too: the number must be printed as a card is
(4-4-4-4, 4-6-5 or 4-6-4 with one separator) or follow a whole card word
within :attr:`PROXIMITY` characters.
"""

import re
from typing import override

from stdnum import luhn

from ._base import _Validator

# Words that make a Luhn-valid number a card, wherever it is grouped.
_CARD_WORDS = ("card", "creditcard", "cc", "pan", "visa", "mastercard", "amex")
_CARD_WORD_RE = re.compile(
    "(?<![A-Za-z0-9])(?:" + "|".join(_CARD_WORDS) + ")(?![A-Za-z0-9])",
    re.IGNORECASE | re.ASCII,
)
_CARD_GROUPS = ((4, 4, 4, 4), (4, 6, 5), (4, 6, 4))


def _card_grouped(candidate: str) -> bool:
    """Return whether ``candidate`` is grouped as a card is printed, with one separator throughout."""
    separator = next((char for char in candidate if char in " -"), None)
    if separator is None:
        return False
    groups = candidate.split(separator)
    if not all(group.isascii() and group.isdigit() for group in groups):
        return False
    return tuple(len(group) for group in groups) in _CARD_GROUPS


class CreditCardValidator(_Validator):
    """13-19 digit credit-card numbers with optional separators, grouped as a card or after a card word."""

    LABEL = "CREDIT_CARD"
    # Allow space, hyphen, or no separator between groups. Total length
    # 13-19 digits to cover Amex (15), MasterCard/Visa (16), 19-digit cards.
    PATTERN = re.compile(
        r"\b(?:\d[ -]?){12,18}\d\b",
    )

    @override
    def _anchored(self, text: str, match: re.Match[str]) -> bool:
        if _card_grouped(match.group()):
            return True
        start = max(0, match.start() - self.PROXIMITY)
        # A word may start inside the window and run into the number, which the lookahead then refuses.
        return any(word.end() <= match.start() for word in _CARD_WORD_RE.finditer(text, start, match.start() + 1))

    @override
    def validate(self, candidate: str) -> bool:
        digits = re.sub(r"[ -]", "", candidate)
        if not 13 <= len(digits) <= 19 or not digits.isdigit():
            return False
        try:
            return luhn.is_valid(digits)
        except Exception:  # pragma: no cover -- stdnum is well-tested
            return False
