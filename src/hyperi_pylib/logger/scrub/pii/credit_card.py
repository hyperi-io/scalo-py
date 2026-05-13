#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/credit_card.py
#  Purpose:   Credit card validator (Luhn via python-stdnum)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Credit card validator — strong-structural.

Detects 13-19 digit runs with optional separators and validates via
Luhn (ISO/IEC 7812-1 Annex B). Strong-structural per spec §9.1 —
fires from any context.
"""

from __future__ import annotations

import re

from stdnum import luhn

from ._base import _Validator


class CreditCardValidator(_Validator):
    """13-19 digit credit-card numbers with optional separators."""

    LABEL = "CREDIT_CARD"
    # Allow space, hyphen, or no separator between groups. Total length
    # 13-19 digits to cover Amex (15), MasterCard/Visa (16), 19-digit cards.
    PATTERN = re.compile(
        r"\b(?:\d[ -]?){12,18}\d\b",
    )

    def validate(self, candidate: str) -> bool:
        digits = re.sub(r"[ -]", "", candidate)
        if not 13 <= len(digits) <= 19 or not digits.isdigit():
            return False
        try:
            return luhn.is_valid(digits)
        except Exception:  # pragma: no cover — stdnum is well-tested
            return False
