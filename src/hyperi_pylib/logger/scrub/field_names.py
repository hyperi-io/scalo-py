#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/field_names.py
#  Purpose:   Layer 2 — field-name regex scrubber
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Layer 2 — field-name regex scrubber.

Matches the existing ``SensitiveDataFilter`` field-name patterns —
``password=...``, ``"token":"..."``, bearer tokens, DB URLs — and
exposes them via the :class:`Scrubber` Protocol.

Once the field-name list moves to
``hyperi-ai/standards/patterns/field_names.toml`` (per spec §3.2),
this class reads from there. For now it delegates to the existing
``SensitiveDataFilter._mask_sensitive_string`` to preserve current
behaviour and avoid a forced restructure mid-flight.
"""

from __future__ import annotations

from ..filters import SensitiveDataFilter


class FieldNameScrubber:
    """L2 — field-name regex (``password=hunter2`` → ``password=***REDACTED***``)."""

    def __init__(self, extra_fields: set[str] | None = None) -> None:
        self._inner = SensitiveDataFilter(extra_fields=extra_fields)

    def scrub(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        return self._inner._mask_sensitive_string(text)

    def __repr__(self) -> str:
        return "FieldNameScrubber()"
