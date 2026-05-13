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
from .gitleaks_toml import GitleaksTomlScrubber, load_gitleaks_rules
from .metrics import ScrubMetrics

if TYPE_CHECKING:
    from .labeler import LabelFn


# Minimal subset of high-signal rule IDs from upstream gitleaks.toml —
# used when patterns="minimal". Matches the historical SECRETS_PLUGINS_LITE
# list using the upstream rule IDs.
_MINIMAL_RULES: frozenset[str] = frozenset({
    "aws-access-token",
    "github-pat",
    "github-fine-grained-pat",
    "github-app-token",
    "github-oauth",
    "gitlab-pat",
    "gitlab-pat-routable",
    "stripe-access-token",
    "jwt",
    "private-key",
    "openai-api-key",
    "slack-bot-token",
    "slack-user-token",
})


class SecretsScrubber:
    """L1 — secret artefacts.

    Two implementations selectable via ``patterns``:

    - ``"gitleaks"`` (default) — TOML-driven, loads the bundled
      ``gitleaks.toml`` (vendored from
      ``hyperi-ai/standards/patterns/gitleaks.toml``). Cross-language
      parity contract per spec §3.2.
    - ``"minimal"`` — TOML-driven, restricted to a high-signal subset
      (~7 rules) for hot-ish paths.
    - ``"detect-secrets"`` — legacy path using the ``detect-secrets``
      package, including its entropy heuristics. Kept available for
      callers that want entropy-based detection that the TOML rules
      don't cover.
    - ``"off"`` — no-op.

    Args:
        patterns: rule-set selector (see above).
        extra_patterns: org-specific ``(type_name, regex)`` tuples
            for in-house token formats. Currently honoured only by the
            ``detect-secrets`` path — the TOML path will gain a
            corresponding ``[[rules]]``-append mechanism in a future
            step.
        labeler: redaction-label producer. Defaults to static
            ``[LABEL_REDACTED]``; pass the result of
            :func:`make_hash_labeler` for deterministic-hash mode.
        metrics: :class:`ScrubMetrics` instance. Defaults to no-op.
    """

    # Map config-schema names to SecretsLeakFilter levels (legacy path only).
    _DETECT_SECRETS_LEVEL_MAP = {
        "detect-secrets": "full",
        "detect-secrets-minimal": "lite",
        "off": "off",
    }

    def __init__(
        self,
        patterns: str = "gitleaks",
        extra_patterns: list[tuple[str, str]] | None = None,
        labeler: LabelFn | None = None,
        metrics: ScrubMetrics | None = None,
    ) -> None:
        self._metrics = metrics if metrics is not None else ScrubMetrics.noop()
        self.patterns = patterns

        if patterns in ("gitleaks", "minimal"):
            rule_ids = _MINIMAL_RULES if patterns == "minimal" else None
            self._inner: GitleaksTomlScrubber | SecretsLeakFilter = (
                GitleaksTomlScrubber(
                    labeler=labeler,
                    metrics=self._metrics,
                    rule_ids=rule_ids,
                )
            )
        elif patterns in self._DETECT_SECRETS_LEVEL_MAP:
            level = self._DETECT_SECRETS_LEVEL_MAP[patterns]
            self._inner = SecretsLeakFilter(
                level=level,
                extra_patterns=extra_patterns,
                labeler=labeler,
                metrics=self._metrics,
            )
        else:
            # Unknown selector — default to the canonical TOML path.
            self._inner = GitleaksTomlScrubber(
                labeler=labeler,
                metrics=self._metrics,
            )

    def scrub(self, text: str) -> str:
        return self._inner.scrub(text)

    def __repr__(self) -> str:
        return f"SecretsScrubber(patterns={self.patterns!r})"


# Re-export for callers wanting to interrogate the bundled rule set.
__all__ = ["SecretsScrubber", "load_gitleaks_rules"]
