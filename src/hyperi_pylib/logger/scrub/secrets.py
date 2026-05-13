#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/secrets.py
#  Purpose:   Layer 1 — gitleaks-style secret-artefact scrubber
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Layer 1 — secret-artefact scrubber.

Detects gitleaks-style secrets (AWS keys, GitHub tokens, JWTs,
private keys, third-party SaaS API keys) and exposes them via the
:class:`Scrubber` Protocol.

Currently delegates to the existing :class:`SecretsLeakFilter`
backed by ``detect-secrets``. Per spec §3.1, this will migrate to
direct compilation from ``hyperi-ai/standards/patterns/gitleaks.toml``
in Step 10 — the public API of this class is the same after that
swap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..secrets_leak import SecretsLeakFilter

if TYPE_CHECKING:
    from .labeler import LabelFn


class SecretsScrubber:
    """L1 — secret artefacts.

    Args:
        patterns: ``"gitleaks"`` (all 24 curated detectors),
            ``"minimal"`` (7 high-signal types), or ``"off"`` (no-op).
            Mirrors ``ScrubConfig.secrets.patterns`` for consistency.
        extra_patterns: org-specific ``(type_name, regex)`` tuples
            for in-house token formats.
        labeler: redaction-label producer. Defaults to static
            ``[LABEL_REDACTED]``; pass the result of
            :func:`make_hash_labeler` for deterministic-hash mode.
    """

    # Map config-schema names to SecretsLeakFilter levels.
    _LEVEL_MAP = {
        "gitleaks": "full",
        "minimal": "lite",
        "off": "off",
    }

    def __init__(
        self,
        patterns: str = "gitleaks",
        extra_patterns: list[tuple[str, str]] | None = None,
        labeler: LabelFn | None = None,
    ) -> None:
        level = self._LEVEL_MAP.get(patterns, "full")
        self._inner = SecretsLeakFilter(
            level=level,
            extra_patterns=extra_patterns,
            labeler=labeler,
        )
        self.patterns = patterns

    def scrub(self, text: str) -> str:
        return self._inner.scrub(text)

    def __repr__(self) -> str:
        return f"SecretsScrubber(patterns={self.patterns!r})"
