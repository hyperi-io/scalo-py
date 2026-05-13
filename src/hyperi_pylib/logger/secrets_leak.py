#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/secrets_leak.py
#  Purpose:   Security-artefact (gitleaks-style) masking for log lines
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Detect and redact secret artefacts (API keys, tokens, private keys).

Distinct from :class:`SensitiveDataFilter` (which matches *field
names* like ``password=``) and :class:`DataFogSensitiveDataFilter`
(which matches *PII values* like emails and SSNs). Secret artefacts
are a security category: AWS keys, GitHub tokens, JWTs, private
keys, third-party SaaS API tokens — the things a gitleaks scan
catches in code commits, applied at log-write time.

Backed by Yelp's ``detect-secrets`` library, which ships ~28
purpose-built detectors. We exclude the high-entropy and keyword
detectors here because they fire on normal English prose (regular
words become "Base64 High Entropy String" findings).

Two cascade levels mirror the PII tier:

- ``"full"`` — all curated detectors (24 types: AWS, Azure, GitHub,
  GitLab, Stripe, Slack, OpenAI, Twilio, SendGrid, JWT, Private Key,
  IBM Cloud, Mailchimp, npm, Artifactory, Discord, Telegram, PyPI,
  Square, public IP, Basic Auth, Cloudant, Softlayer).
- ``"lite"`` — high-signal-only subset (7 types: AWS, GitHub, GitLab,
  Stripe, JWT, Private Key, OpenAI). Fastest, lowest false-positive
  rate.
- ``"off"`` — disabled.

Redaction is two-step: detect-secrets identifies the *type* of secret
present; a per-type regex performs the *replacement* (because some
detect-secrets plugins return only a prefix, not the full token).
"""

from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .scrub.labeler import LabelFn

__all__ = [
    "SECRETS_PLUGINS_FULL",
    "SECRETS_PLUGINS_LITE",
    "SecretsLeakFilter",
]


# Curated plugin set — full coverage minus the noisy high-entropy and
# keyword detectors (which would re-do what SensitiveDataFilter already
# does for field names and would FP on normal English).
SECRETS_PLUGINS_FULL: list[dict[str, Any]] = [
    {"name": "AWSKeyDetector"},
    {"name": "AzureStorageKeyDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "GitLabTokenDetector"},
    {"name": "StripeDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "PrivateKeyDetector"},
    {"name": "SlackDetector"},
    {"name": "OpenAIDetector"},
    {"name": "TwilioKeyDetector"},
    {"name": "SendGridDetector"},
    {"name": "TelegramBotTokenDetector"},
    {"name": "DiscordBotTokenDetector"},
    {"name": "PypiTokenDetector"},
    {"name": "IbmCloudIamDetector"},
    {"name": "MailchimpDetector"},
    {"name": "NpmDetector"},
    {"name": "ArtifactoryDetector"},
    {"name": "SquareOAuthDetector"},
    {"name": "IbmCosHmacDetector"},
    {"name": "SoftlayerDetector"},
    {"name": "CloudantDetector"},
    {"name": "IPPublicDetector"},
    {"name": "BasicAuthDetector"},
]

# High-signal subset — types where the regex is specific enough to
# have near-zero false-positives on prose. Use for hot-ish paths
# where the full plugin set is too slow.
SECRETS_PLUGINS_LITE: list[dict[str, Any]] = [
    {"name": "AWSKeyDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "GitLabTokenDetector"},
    {"name": "StripeDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "PrivateKeyDetector"},
    {"name": "OpenAIDetector"},
]


# Redaction regex per detect-secrets type. detect-secrets reports the
# TYPE confidently but `secret_value` is sometimes a prefix only
# (e.g. "ghp" for GitHub tokens). We use these regex for the actual
# in-line replacement so the full secret is removed from log output.
_REDACTION_REGEX: dict[str, re.Pattern[str]] = {
    "AWS Access Key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Azure Storage Account access key": re.compile(
        r"[A-Za-z0-9+/]{86}==",
    ),
    "GitHub Token": re.compile(
        r"\b(?:gh[opsur]_[0-9a-zA-Z]{36,}|github_pat_[0-9a-zA-Z_]{82,})\b",
    ),
    "GitLab Token": re.compile(r"\bglpat-[0-9a-zA-Z_\-]{20}\b"),
    "Stripe Access Key": re.compile(
        r"\b[rsp]k_(?:live|test)_[0-9a-zA-Z]{24,99}\b",
    ),
    "JSON Web Token": re.compile(
        r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*\b",
    ),
    "Private Key": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----",
        re.MULTILINE,
    ),
    "Slack Token": re.compile(r"\bxox[abprs]-[0-9a-zA-Z\-]{10,48}\b"),
    "OpenAI Token": re.compile(r"\bsk-(?:proj-|svcacct-)?[a-zA-Z0-9_\-]{20,200}\b"),
    "Twilio API Key": re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
    "SendGrid API Key": re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b"),
    "Telegram Bot Token": re.compile(r"\b\d{8,11}:[A-Za-z0-9_\-]{35}\b"),
    "Discord Bot Token": re.compile(r"\b[MN][A-Za-z\d]{23,28}\.[A-Za-z\d_\-]{6,7}\.[A-Za-z\d_\-]{27,38}\b"),
    "PyPI upload token": re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{60,}\b"),
    "Mailchimp Access Key": re.compile(r"\b[0-9a-f]{32}-us\d{1,2}\b"),
    "npm Access Token": re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    "Square OAuth Secret": re.compile(r"\bsq0csp-[ 0-9A-Za-z\-_]{43}\b"),
}


def _label_slug(secret_type: str) -> str:
    """Convert ``"GitHub Token"`` to ``"GITHUB_TOKEN"`` (no brackets, no suffix)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", secret_type).strip("_").upper()


def _redaction_label(secret_type: str) -> str:
    """Convert ``"GitHub Token"`` to ``"[GITHUB_TOKEN_REDACTED]"`` (static mode only)."""
    return f"[{_label_slug(secret_type)}_REDACTED]"


class SecretsLeakFilter:
    """Detect and redact secret artefacts in log lines.

    Wraps Yelp's ``detect-secrets``. Use as a composable scrubber:

        leak_filter = SecretsLeakFilter(level="full")
        clean = leak_filter.scrub(log_line)

    Args:
        level: ``"full"`` (default, 24 detector types), ``"lite"``
            (7 high-signal types), or ``"off"`` (no detection).
        extra_patterns: Additional ``(type_name, regex_pattern)``
            tuples for org-specific secret formats. Detection AND
            redaction use the regex.

    Raises:
        ImportError caught silently — if detect-secrets is not
        installed (impossible currently as it's a core dep, but
        defensive), the filter becomes a no-op with a warning.
    """

    def __init__(
        self,
        level: str = "full",
        extra_patterns: list[tuple[str, str]] | None = None,
        labeler: "LabelFn | None" = None,
    ) -> None:
        from .scrub.labeler import _static_label

        self.level = level
        self._enabled = level != "off"
        self._labeler = labeler if labeler is not None else _static_label

        if level == "full":
            self._plugins = SECRETS_PLUGINS_FULL
        elif level == "lite":
            self._plugins = SECRETS_PLUGINS_LITE
        else:
            self._plugins = []
            self._enabled = False

        # Per-type redaction regex, plus any caller-supplied extras.
        self._redaction: dict[str, re.Pattern[str]] = dict(_REDACTION_REGEX)
        if extra_patterns:
            for name, pattern in extra_patterns:
                self._redaction[name] = re.compile(pattern)

        # Lazy-import detect-secrets so a misconfigured environment
        # doesn't break logger setup entirely.
        try:
            from detect_secrets.core.scan import scan_line
            from detect_secrets.settings import transient_settings

            self._scan_line = scan_line
            self._transient_settings = transient_settings
            self._detect_secrets_available = True
        except ImportError:
            warnings.warn(
                "detect-secrets not installed; SecretsLeakFilter is a no-op. "
                "Install hyperi-pylib core or run: pip install detect-secrets",
                ImportWarning,
                stacklevel=2,
            )
            self._scan_line = None
            self._transient_settings = None
            self._detect_secrets_available = False

    def scrub(self, text: str) -> str:
        """Return text with detected secret artefacts redacted."""
        if not self._enabled or not self._detect_secrets_available or not text:
            return text

        # First: detect-secrets detection pass.
        try:
            with self._transient_settings({"plugins_used": self._plugins}):  # type: ignore[misc]
                findings = list(self._scan_line(text))  # type: ignore[misc]
        except Exception as e:  # pragma: no cover — never let logging break
            warnings.warn(
                f"detect-secrets error: {e}. Skipping secret-leak masking.",
                RuntimeWarning,
                stacklevel=2,
            )
            return text

        if not findings:
            return text

        # Second: redact via per-type regex first (catches the whole
        # match — important for multi-line patterns like private keys
        # where the BEGIN marker is the value detect-secrets returns
        # but the regex covers the full ``BEGIN...END`` block).
        #
        # Each regex.sub() callback computes the label per match so
        # hash-redaction picks up the actual matched value, not just
        # the type slug. Static mode returns the same label per type
        # regardless of value.
        #
        # For types lacking a redaction regex (rare — covers types we
        # haven't given a pattern yet) we fall back to replacing each
        # detect-secrets finding's value directly.
        seen_types = {f.type for f in findings}
        for secret_type in seen_types:
            slug = _label_slug(secret_type)
            regex = self._redaction.get(secret_type)
            if regex is not None:
                text = regex.sub(
                    lambda m, slug=slug: self._labeler(slug, m.group(0)),
                    text,
                )
            else:
                # Fallback: replace each detect-secrets-reported value.
                type_values = {
                    f.secret_value
                    for f in findings
                    if f.type == secret_type and f.secret_value
                }
                for value in type_values:
                    if len(value) <= 5:
                        continue
                    text = text.replace(value, self._labeler(slug, value))

        return text
