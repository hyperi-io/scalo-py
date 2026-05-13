#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/au_tfn.py
#  Purpose:   Australian Tax File Number — context-required
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""AU TFN validator — context-required.

8 or 9 digit Australian Tax File Number with mod-11 weighted-sum
checksum. Context-required per spec §9.2 — mod-11 means 9% of
random 9-digit numbers pass checksum, far too high for unanchored
detection.
"""

from __future__ import annotations

import re

from stdnum.au import tfn

from ._base import _Validator


class TfnValidator(_Validator):
    """AU TFN — 8 or 9 digits with mod-11 checksum, keyword-anchored."""

    LABEL = "AU_TFN"
    # 8 or 9 digits. 9-digit formatted as 3-3-3, 8-digit as 3-3-2 or 4-4.
    PATTERN = re.compile(r"\b\d{3}[ ]?\d{3}[ ]?\d{2,3}\b")
    KEYWORDS = ("tfn", "tax file number")

    def validate(self, candidate: str) -> bool:
        try:
            return tfn.is_valid(candidate)
        except Exception:  # pragma: no cover
            return False
