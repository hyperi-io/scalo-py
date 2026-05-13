#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/au_acn.py
#  Purpose:   Australian Company Number — context-required
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""AU ACN validator — context-required.

9-digit Australian Company Number with weighted-sum checksum.
Context-required per spec §9.2.
"""

from __future__ import annotations

import re

from stdnum.au import acn

from ._base import _Validator


class AcnValidator(_Validator):
    """AU ACN — 9 digits with weighted-sum checksum, keyword-anchored."""

    LABEL = "AU_ACN"
    # 9 digits, optionally formatted as 3-3-3 with single spaces.
    PATTERN = re.compile(r"\b\d{3}[ ]?\d{3}[ ]?\d{3}\b")
    KEYWORDS = ("acn", "australian company number")

    def validate(self, candidate: str) -> bool:
        try:
            return acn.is_valid(candidate)
        except Exception:  # pragma: no cover
            return False
