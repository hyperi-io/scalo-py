#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/types.py
#  Purpose:   Scrubber Protocol -- discrete-object contract per spec §2.3
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Protocol every scrubber satisfies.

See spec §2.3 -- the scrubber is a first-class object/protocol, not a
free function or global mutable state. Implementations:

- :class:`LayeredScrubber` -- the canonical multi-layer scrubber
- :class:`NoOpScrubber` -- pass-through for testing
- Consumer code may implement custom scrubbers for special use cases
  (audit-log channels with relaxed rules, etc.)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Scrubber(Protocol):
    """A scrubber redacts sensitive content from a log-record string.

    Implementations MUST satisfy these properties:

    - **Stateless from the caller's perspective.** Each call to
      :meth:`scrub` is independent. Internal caches (e.g. token
      efficiency) are an implementation detail.
    - **Thread-safe**. Loggers call from many threads; the scrubber
      method must be safe to invoke concurrently.
    - **Idempotent on already-redacted input.** Calling :meth:`scrub`
      twice on the same input produces the same output as calling
      it once (no double-redaction labels, no progressive damage).
    - **Fail-safe** (spec §5.1). If internal state fails, return the
      input unchanged and emit a one-time warning; never raise to
      the caller.
    """

    def scrub(self, text: str) -> str:
        """Return ``text`` with sensitive content redacted.

        Args:
            text: The log record content as a string. May span
                multiple lines, contain non-ASCII codepoints, and
                include arbitrary user data.

        Returns:
            The redacted string. If no redaction was needed, returns
            the input unchanged (may be the same object).
        """
        ...
