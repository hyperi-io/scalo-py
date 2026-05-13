#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/au_medicare.py
#  Purpose:   Australian Medicare card number — context-required
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""AU Medicare card-number validator — context-required.

10 or 11 digit Medicare card number with weighted-sum mod-10
checksum per the ATO spec (§9.7 of the scrub spec). Context-required
per spec §9.2.

``python-stdnum`` v2.2 does not have a ``stdnum.au.medicare`` module
(only ``abn``, ``acn``, ``tfn``). The checksum is implemented locally
here per the ATO algorithm.
"""

from __future__ import annotations

import re

from ._base import _Validator

# Medicare card number checksum weights (first 8 digits).
_MEDICARE_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9)


def _is_valid_medicare(candidate: str) -> bool:
    """Return True if ``candidate`` is a valid AU Medicare card number.

    10-digit form: 9 digits + 1 check digit. The 11th digit, if
    present, is the issue number (1-9) and not part of the checksum.

    Per the ATO algorithm:
      - first digit must be 2-6 (card-type indicator)
      - weighted sum of first 8 digits mod 10 equals digit[8]
    """
    digits = re.sub(r"\s", "", candidate)
    if len(digits) not in (10, 11) or not digits.isdigit():
        return False
    # 10-digit card number portion. 11th (if present) is issue number.
    card = digits[:10]
    issue = digits[10:] or "1"
    if not card[0] in "23456":
        return False
    if not issue.isdigit() or not 1 <= int(issue) <= 9:
        return False
    total = sum(int(c) * w for c, w in zip(card[:8], _MEDICARE_WEIGHTS, strict=True))
    return total % 10 == int(card[8])


class MedicareValidator(_Validator):
    """AU Medicare card number — keyword-anchored."""

    LABEL = "AU_MEDICARE"
    # 10 or 11 digits. Common human format: 4-5-1 or 4-5-1-1.
    PATTERN = re.compile(r"\b\d{4}[ ]?\d{5}[ ]?\d(?:[ ]?\d)?\b")
    KEYWORDS = ("medicare", "medicare card", "medicare number")

    def validate(self, candidate: str) -> bool:
        return _is_valid_medicare(candidate)
