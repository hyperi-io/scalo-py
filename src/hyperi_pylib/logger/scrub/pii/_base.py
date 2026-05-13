#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/_base.py
#  Purpose:   Shared detection/redaction machinery for L3 validators
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Base class for L3 PII validators.

Implements the detection-validation-redaction loop per spec §9.3.
Subclasses provide:

- ``LABEL``: redaction-label slug (e.g. ``"CREDIT_CARD"``)
- ``PATTERN``: structural regex for finding candidates
- ``KEYWORDS``: tuple of keywords required nearby (empty for
  strong-structural validators)
- ``validate(candidate)``: returns True if the candidate is a
  valid X (typically delegates to ``python-stdnum``)
"""

from __future__ import annotations

import re
from typing import ClassVar


class _Validator:
    """Base PII validator. Subclass to add a specific validator.

    Implements :class:`Scrubber` Protocol via duck typing — no
    inheritance required at the call site.
    """

    LABEL: ClassVar[str] = ""
    PATTERN: ClassVar[re.Pattern[str]]
    KEYWORDS: ClassVar[tuple[str, ...]] = ()
    PROXIMITY: ClassVar[int] = 30
    """How many characters back from the candidate to search for keywords."""

    def validate(self, candidate: str) -> bool:
        """Return True if ``candidate`` is a valid instance of this PII type.

        Subclasses override to call the appropriate stdnum or
        equivalent validator.
        """
        raise NotImplementedError

    def scrub(self, text: str) -> str:
        """Find candidates, optionally check context, validate, redact."""
        if not text:
            return text

        def _repl(match: re.Match[str]) -> str:
            candidate = match.group()
            if self.KEYWORDS and not self._has_keyword_context(text, match.start()):
                return candidate
            if not self.validate(candidate):
                return candidate
            return f"[{self.LABEL}_REDACTED]"

        return self.PATTERN.sub(_repl, text)

    def _has_keyword_context(self, text: str, candidate_start: int) -> bool:
        """Return True if any keyword appears within ``PROXIMITY`` chars
        preceding the candidate's start position. Case-insensitive."""
        start = max(0, candidate_start - self.PROXIMITY)
        preceding = text[start:candidate_start].lower()
        return any(kw in preceding for kw in self.KEYWORDS)

    def __repr__(self) -> str:
        kind = "context-required" if self.KEYWORDS else "strong-structural"
        return f"{type(self).__name__}({kind}, label={self.LABEL!r})"
