#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/phone.py
#  Purpose:   Phone number validator (libphonenumber via phonenumbers)
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Phone validator -- strong-structural.

Detects phone numbers via libphonenumber-grade parsing. Strong-
structural per spec §9.1 -- but only when libphonenumber confirms the
candidate. python-stdnum has no phone module; libphonenumber (via
``phonenumbers``) is the canonical answer for global phone parsing.
"""

from __future__ import annotations

import re

import phonenumbers

from ._base import _Validator


class PhoneValidator(_Validator):
    """E.164 / international phone numbers via libphonenumber."""

    LABEL = "PHONE"
    # Candidate shape: optional +, then 7-17 digits with possible
    # separators (space, hyphen, dot, parentheses). Permissive -- the
    # phonenumbers.is_valid_number() call is the real filter.
    PATTERN = re.compile(
        r"\+?\d[\d \-.()]{6,20}\d",
    )

    def validate(self, candidate: str) -> bool:
        # Try to parse as international first (region=None). If that
        # fails, the candidate isn't a valid number we can confirm.
        try:
            num = phonenumbers.parse(candidate, None)
            return phonenumbers.is_valid_number(num)
        except phonenumbers.NumberParseException:
            return False
