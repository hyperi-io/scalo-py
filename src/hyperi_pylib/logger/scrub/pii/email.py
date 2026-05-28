#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/email.py
#  Purpose:   Email address validator
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Email validator -- strong-structural.

Detects email addresses via a pragmatic RFC 5322 subset. python-stdnum
has no email module; the structural regex IS the validation -- we
trust the pattern (no separate is_valid() call). False-positive rate
is low for the structural shape.
"""

from __future__ import annotations

import re

from ._base import _Validator


class EmailValidator(_Validator):
    """Email addresses per RFC 5322 subset."""

    LABEL = "EMAIL"
    # Pragmatic RFC 5322 subset. Allow Unicode in local part and domain
    # (IDN supported in direct form per spec §10a.6). \w includes
    # Unicode word characters by default in Python 3.
    PATTERN = re.compile(
        r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b",
        re.UNICODE,
    )

    def validate(self, candidate: str) -> bool:
        # The structural regex is the validator. No separate stdnum
        # check for emails. Return True for any pattern hit.
        return True
