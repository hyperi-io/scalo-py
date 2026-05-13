#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/au_abn.py
#  Purpose:   Australian Business Number — context-required
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""AU ABN validator — context-required.

11-digit Australian Business Number with weighted-sum mod-89
checksum. Context-required per spec §9.2 — bare 11-digit runs are
ambiguous (could be a phone number, request ID, etc.), so we
require a keyword anchor in the preceding text.
"""

from __future__ import annotations

import re

from stdnum.au import abn

from ._base import _Validator


class AbnValidator(_Validator):
    """AU ABN — 11 digits with mod-89 checksum, keyword-anchored."""

    LABEL = "AU_ABN"
    # 11 digits, optionally formatted as 2-3-3-3 with single spaces.
    PATTERN = re.compile(r"\b\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b")
    KEYWORDS = ("abn", "australian business number")

    def validate(self, candidate: str) -> bool:
        try:
            return abn.is_valid(candidate)
        except Exception:  # pragma: no cover
            return False
