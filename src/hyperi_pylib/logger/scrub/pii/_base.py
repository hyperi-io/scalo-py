#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/_base.py
#  Purpose:   Shared detection/redaction machinery for L3 validators
#  Language:  Python
#
#  License:   BUSL-1.1
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

from ..labeler import LabelFn, _static_label
from ..metrics import ScrubMetrics


class _Validator:
    """Base PII validator. Subclass to add a specific validator.

    Implements :class:`Scrubber` Protocol via duck typing -- no
    inheritance required at the call site.

    Per spec §4.4, the label format is controlled by an injected
    :data:`LabelFn`. The default produces ``[LABEL_REDACTED]``; the
    factory swaps in a deterministic-hash labeler when
    ``scrub.hash_redaction: true`` is set.
    """

    LABEL: ClassVar[str] = ""
    PATTERN: ClassVar[re.Pattern[str]]
    KEYWORDS: ClassVar[tuple[str, ...]] = ()
    PROXIMITY: ClassVar[int] = 30
    """How many characters back from the candidate to search for keywords."""

    labeler: LabelFn = staticmethod(_static_label)
    """Label producer. Override per-instance via constructor or assignment."""

    metrics: ScrubMetrics
    """Metric emitter. Defaults to a no-op for bare instantiation."""

    def __init__(
        self,
        labeler: LabelFn | None = None,
        metrics: ScrubMetrics | None = None,
    ) -> None:
        """Optionally accept a per-instance labeler and metrics.

        Subclasses that don't override ``__init__`` get this signature
        for free -- strong-structural validators (credit_card, email,
        iban, phone) just call ``super().__init__(labeler=...)``
        or rely on this default if instantiated bare.
        """
        if labeler is not None:
            self.labeler = labeler  # type: ignore[method-assign]
        self.metrics = metrics if metrics is not None else ScrubMetrics.noop()

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
            # Every regex hit counts as a match -- observe-only mode and
            # metric dashboards both want to see the detection rate
            # before validation/context filtering.
            self.metrics.inc_match("L3", self.LABEL)
            if self.KEYWORDS and not self._has_keyword_context(text, match.start()):
                return candidate
            if not self.validate(candidate):
                return candidate
            self.metrics.inc_redaction("L3", self.LABEL)
            return self.labeler(self.LABEL, candidate)

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
