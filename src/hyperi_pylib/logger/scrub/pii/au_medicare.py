#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/au_medicare.py
#  Purpose:   AU Medicare check-digit validator (python-stdnum lacks this)
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""AU Medicare card-number checksum validator.

``python-stdnum`` v2.2 doesn't include ``stdnum.au.medicare``. The
checksum is implemented here per the ATO spec (log-scrub-spec §9.7)
and referenced from ``national_ids.toml`` via
``local_validator = "hyperi_pylib.logger.scrub.pii.au_medicare:_is_valid_medicare"``.

10-digit or 11-digit Medicare card number:
- first digit must be 2-6 (card-type indicator)
- weighted sum of first 8 digits mod 10 equals digit[8]
- 11th digit (if present) is the issue number (1-9)
"""

from __future__ import annotations

import re

# Medicare card number checksum weights (first 8 digits).
_MEDICARE_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9)


def _is_valid_medicare(candidate: str) -> bool:
    """Return True if ``candidate`` is a valid AU Medicare card number."""
    digits = re.sub(r"\s", "", candidate)
    if len(digits) not in (10, 11) or not digits.isdigit():
        return False
    card = digits[:10]
    issue = digits[10:] or "1"
    if card[0] not in "23456":
        return False
    if not issue.isdigit() or not 1 <= int(issue) <= 9:
        return False
    total = sum(int(c) * w for c, w in zip(card[:8], _MEDICARE_WEIGHTS, strict=True))
    return total % 10 == int(card[8])
