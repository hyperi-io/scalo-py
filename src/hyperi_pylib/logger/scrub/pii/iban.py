#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/iban.py
#  Purpose:   IBAN validator (mod-97 via python-stdnum)
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""IBAN validator -- strong-structural.

Detects ISO 13616-1 International Bank Account Numbers. Strong-
structural per spec §9.1 -- the country-code prefix + check digits
make the candidate shape distinctive.
"""

from __future__ import annotations

import re

from stdnum import iban

from ._base import _Validator


class IbanValidator(_Validator):
    """ISO 13616-1 IBAN with mod-97 checksum."""

    LABEL = "IBAN"
    # 2-letter country code + 2 check digits + 11-30 alphanumeric BBAN.
    # IBAN length is country-dependent (15-34 total). Allow spaces.
    PATTERN = re.compile(
        r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b",
    )

    def validate(self, candidate: str) -> bool:
        try:
            return iban.is_valid(candidate.replace(" ", ""))
        except Exception:  # pragma: no cover
            return False
