#  Project:   scalo
#  File:      src/scalo/logger/scrub/pii/email.py
#  Purpose:   Email address validator
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Email validator -- strong-structural.

Detects email addresses via a pragmatic RFC 5322 subset, both literal and
percent-encoded the way a URL query string carries them: ``%40`` or the
double-encoded ``%2540`` for ``@``, and ``%2B`` / ``%252B`` for ``+`` in the
local part, hex in either case. Only the address is redacted, so an escape
just before it (the ``%22`` of an encoded quote, the ``%3D`` of an encoded
``=``) survives. python-stdnum has no email module; the structural regex IS
the validation -- we trust the pattern (no separate is_valid() call).
"""

import re
from typing import override

from ._base import _Validator

_HEX = "[0-9A-Fa-f]"


class EmailValidator(_Validator):
    """Email addresses per RFC 5322 subset, literal or percent-encoded."""

    LABEL = "EMAIL"
    # \w is Unicode-aware, so IDN local parts and domains match in direct form (spec Section 10a.6).
    PATTERN = re.compile(
        rf"""
        (?:                                            # the address starts at
            \b(?!(?<=%){_HEX}{{2}})                    #   a word boundary that is not inside a %XX escape,
          | (?<=%{_HEX}{{2}})(?!(?<=%25){_HEX}{{2}})   #   the end of a %XX escape that does not open %25XX,
          | (?<=%25{_HEX}{{2}})                        #   or the end of a double-encoded %25XX escape
        )
        [\w.+\-]+(?:%(?:25)?2[Bb][\w.+\-]*)*           # local part; %2B and %252B are an encoded +
        (?:@|%(?:25)?40)                               # @, %40, or %2540
        [\w\-]+(?:\.[\w\-]+)+\b                        # domain with at least one dot
        """,
        re.UNICODE | re.VERBOSE,
    )

    @override
    def scrub(self, text: str) -> str:
        """Return ``text`` with email addresses redacted.

        Every match contains ``@``, ``%40`` or ``%2540``, so a string with none
        of them returns unchanged without running the regex.
        """
        if "@" not in text and "%40" not in text and "%2540" not in text:
            return text
        return super().scrub(text)

    @override
    def validate(self, candidate: str) -> bool:
        # The structural regex is the validator. No separate stdnum
        # check for emails. Return True for any pattern hit.
        return True
