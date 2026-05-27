"""Logging filters for hyperi-pylib logger.

This module provides logging filters for sensitive-data masking by
*field name* and for rate-limiting repeated messages.

For PII-value detection (emails, phones, credit cards, national IDs,
etc.) use the newer ``hyperi_pylib.logger.scrub`` pipeline -- that is
the canonical Layer 3 in the cross-language log-scrub spec. NLP/NER
scrubbing has been dropped from scope; this module ships only the
deterministic field-name regex filter.

**Components:**

- :class:`SensitiveDataFilter`: regex-on-field-names masker
  (``password=...``, ``"token":"..."``, bearer tokens, DB URLs).
- :class:`RateLimitFilter`: suppress repeated log messages from
  tight loops; reports the suppressed-count on the next message.

Use :func:`get_sensitive_filter` for the legacy three-tier selector --
``"advanced"`` and ``"advanced-ner"`` emit deprecation warnings and
return the field-name filter.
"""

import logging
import re
import time
import warnings
from collections import defaultdict
from typing import Any

from .secrets_leak import SecretsLeakFilter

# Sensitive fields that should be masked in logs
SENSITIVE_FIELDS: set[str] = {
    # Passwords
    "password",
    "passwd",
    "pwd",
    # Tokens
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "session_token",
    "api_token",
    "bearer",
    # API Keys
    "api_key",
    "apikey",
    "api_secret",
    # Secrets
    "secret",
    "client_secret",
    "secret_key",
    "private_key",
    "secret_access_key",
    "aws_secret_access_key",
    # Auth
    "authorization",
    "auth",
    # Session
    "session_id",
    "sessionid",
    # Certificates
    "certificate",
    "cert",
    "ssl_cert",
    # Credentials
    "credentials",
    "creds",
    # Database
    "db_password",
    "database_password",
    "connection_string",
}

MASK_VALUE = "***REDACTED***"

# Static patterns shared across all SensitiveDataFilter instances.
# Compiled once at module load instead of per-call to _mask_sensitive_string.
_DB_URL_RE = re.compile(r"(://[^:/@]*:)([^@]+)(@)")
_BEARER_RE = re.compile(r"\bbearer\s+([^\s]+)", re.IGNORECASE)


class SensitiveDataFilter(logging.Filter):
    """
    Masks sensitive data in log records (passwords, tokens, API keys, etc.).

    Applied automatically by default logger. Supports JSON, form data,
    key-value pairs, and database URLs.

    Two composable scrubbing layers (applied in this order):

    1. **Secrets-leak detection** (``SecretsLeakFilter``, optional) --
       gitleaks-style: AWS keys, GitHub tokens, JWTs, private keys.
       On by default at ``level="full"``; opt-down via config to
       ``"lite"`` or ``"off"``.
    2. **Field-name regex** (this class) -- ``password=...``,
       ``"token":"..."``, bearer tokens, DB URLs.

    For PII-value detection (emails, phones, credit cards, national
    IDs, etc.) use the newer ``hyperi_pylib.logger.scrub`` pipeline,
    which exposes a richer Layer 3 with algorithmic validators
    (Luhn, mod-97 IBAN, libphonenumber, TOML-driven national IDs).

    Custom fields:
        SensitiveDataFilter.add_sensitive_fields({"employee_id", "ssn"})

    Disable (not recommended):
        export HYPERI_LIB_LOGGING__MASK_SENSITIVE_DATA=false
    """

    # Class-level set for global custom fields
    _custom_fields: set[str] = set()

    def __init__(
        self,
        extra_fields: set[str] | None = None,
        secrets_leak: SecretsLeakFilter | None = None,
    ):
        """
        Initialize the sensitive data filter.

        Args:
            extra_fields: Additional fields to mask (optional)
            secrets_leak: Optional secrets-artefact scrubber applied
                BEFORE field-name regex. Composable for callers that
                want a one-shot field-name + secrets pass.
        """
        super().__init__()
        self._instance_fields = extra_fields or set()
        self._secrets_leak = secrets_leak
        # Pre-compile per-field patterns once. Cache invalidates when
        # the global SENSITIVE_FIELDS or _custom_fields set changes,
        # since _build_field_patterns reads them at call time.
        self._field_patterns_cache: tuple[set[str], list[tuple[re.Pattern, str]]] | None = None

    def _build_field_patterns(self) -> list[tuple[re.Pattern, str]]:
        """Return cached (pattern, replacement) pairs for all sensitive fields.

        Rebuilds if the underlying field set changed (e.g. caller invoked
        ``add_sensitive_fields`` between log lines).
        """
        fields = self._get_all_sensitive_fields()
        if self._field_patterns_cache is not None and self._field_patterns_cache[0] == fields:
            return self._field_patterns_cache[1]

        pairs: list[tuple[re.Pattern, str]] = []
        for field in fields:
            # 1: JSON with quotes ("field":"value")
            pairs.append((re.compile(rf'("{field}"\s*:\s*)"([^"]*)"', re.IGNORECASE), rf'\1"{MASK_VALUE}"'))
            # 2: JSON without key quotes (field:"value")
            pairs.append((re.compile(rf'(\b{field}\s*:\s*)"([^"]*)"', re.IGNORECASE), rf'\1"{MASK_VALUE}"'))
            # 3: Form data / query params
            pairs.append((re.compile(rf"(\b{field})=([^\s&\n]*)", re.IGNORECASE), rf"\1={MASK_VALUE}"))
            # 4: Key-value without quotes (field: value)
            pairs.append(
                (
                    re.compile(rf'(\b{field}\s*:\s*)([^\s\n,"}}]+)(?=[\s\n,}}]|$)', re.IGNORECASE),
                    rf"\1{MASK_VALUE}",
                )
            )

        self._field_patterns_cache = (fields, pairs)
        return pairs

    @classmethod
    def add_sensitive_fields(cls, fields: set[str]) -> None:
        """
        Add custom sensitive fields to mask globally.

        Args:
            fields: Set of field names to mask (case-insensitive)
        """
        cls._custom_fields.update(f.lower() for f in fields)

    def _get_all_sensitive_fields(self) -> set[str]:
        """Get combined set of all sensitive fields."""
        return SENSITIVE_FIELDS | self._custom_fields | self._instance_fields

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record to mask sensitive data.

        Args:
            record: The log record to filter

        Returns:
            True to allow the record to be logged
        """
        # Mask the main message
        if isinstance(record.msg, str):
            record.msg = self._mask_sensitive_string(record.msg)
        elif isinstance(record.msg, dict):
            record.msg = self._mask_sensitive_dict(record.msg)

        # Mask any arguments
        if record.args:
            if isinstance(record.args, dict):
                record.args = self._mask_sensitive_dict(record.args)
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(self._mask_value(arg) for arg in record.args)

        return True

    def _mask_value(self, value: Any) -> Any:
        """Mask a single value based on its type."""
        if isinstance(value, str):
            return self._mask_sensitive_string(value)
        elif isinstance(value, dict):
            return self._mask_sensitive_dict(value)
        elif isinstance(value, (list, tuple)):
            return type(value)(self._mask_value(item) for item in value)
        return value

    def _mask_sensitive_string(self, text: str) -> str:
        """
        Mask sensitive fields in a string using regex patterns.

        Handles multiple formats:
        - URL parameters: `field=value&`
        - JSON: `"field":"value"` or `field:"value"`
        - Key-value pairs: `field: value` or `field=value`
        - Database URLs: `://user:password@host`

        Runs the secrets-leak scrubber first (if configured), then
        applies the field-name regex pass.

        Args:
            text: String to mask

        Returns:
            String with sensitive fields masked
        """
        if not isinstance(text, str):
            return text

        # First pass: secrets-artefact scrubber (gitleaks-style)
        if self._secrets_leak is not None:
            text = self._secrets_leak.scrub(text)

        # DB URLs: postgres://user:secret@host -> postgres://user:***@host
        masked = _DB_URL_RE.sub(rf"\1{MASK_VALUE}\3", text)
        # Bearer tokens
        masked = _BEARER_RE.sub(f"bearer {MASK_VALUE}", masked)
        # Per-field patterns (pre-compiled, cached on instance)
        for pattern, repl in self._build_field_patterns():
            masked = pattern.sub(repl, masked)

        return masked

    def _mask_sensitive_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively mask sensitive fields in a dictionary.

        Args:
            data: Dictionary potentially containing sensitive fields

        Returns:
            New dictionary with sensitive fields masked
        """
        if not isinstance(data, dict):
            return data

        masked_data = {}
        fields = self._get_all_sensitive_fields()

        for key, value in data.items():
            if key.lower() in fields:
                # Mask this field entirely
                masked_data[key] = MASK_VALUE
            elif isinstance(value, dict):
                # Recursively mask nested dictionaries
                masked_data[key] = self._mask_sensitive_dict(value)
            elif isinstance(value, (list, tuple)):
                # Handle lists/tuples
                masked_data[key] = type(value)(self._mask_value(item) for item in value)
            elif isinstance(value, str):
                # Mask sensitive patterns in strings
                masked_data[key] = self._mask_sensitive_string(value)
            else:
                masked_data[key] = value

        return masked_data


def get_sensitive_filter(
    level: str = "simple",
    extra_fields: set[str] | None = None,
) -> SensitiveDataFilter:
    """Return a :class:`SensitiveDataFilter` for the requested tier.

    Backwards-compatible shim. The tiering system collapsed when NLP
    was dropped from the spec -- all ``level`` values now resolve to
    the same field-name regex filter. For PII-value detection (emails,
    phones, credit cards, etc.) use the newer ``logger.scrub.*``
    pipeline (see :class:`hyperi_pylib.logger.scrub.LayeredScrubber`).

    Args:
        level: kept for backward compatibility. ``"advanced"`` and
            ``"advanced-ner"`` emit a one-shot deprecation warning and
            then act like ``"simple"``.
        extra_fields: additional field names to mask via the regex pass.

    Returns:
        A :class:`SensitiveDataFilter` instance.
    """
    if level in ("advanced", "advanced-ner"):
        warnings.warn(
            f"get_sensitive_filter(level={level!r}) is deprecated. NLP/NER "
            "scrubbing was dropped from hyperi-pylib (false-positive rate on "
            "logs was unacceptable). Use the new ``logger.scrub.*`` pipeline "
            "for PII-value detection, or pass ``level='simple'`` to silence "
            "this warning.",
            DeprecationWarning,
            stacklevel=2,
        )
    return SensitiveDataFilter(extra_fields=extra_fields)


class RateLimitFilter:
    """
    Rate-limit repeated log messages to prevent log spam from tight loops.

    This filter suppresses identical (or similar) log messages that occur more
    frequently than the configured period. When messages resume after suppression,
    the filter reports how many messages were skipped.

    **Exact matching (default):**
    Messages are identified by a composite key of (logger name, level, message).

    **Similar matching (normalise_numbers=True):**
    Numbers, UUIDs, and hex strings are normalised to placeholders before matching,
    so messages like "Failed to process order 12345" and "Failed to process order 67890"
    are treated as the same message.

    Example:
        >>> from hyperi_pylib.logger import logger, setup
        >>> setup(rate_limit_sec=30)  # Suppress repeats within 30 seconds
        >>>
        >>> # In a tight loop with errors:
        >>> for i in range(1000):
        ...     logger.error("Connection failed")  # Only logs first, then summary
        >>> # Output:
        >>> # Connection failed
        >>> # Connection failed (suppressed 998 similar messages)

        >>> # With normalise_numbers=True (similar messages):
        >>> setup(rate_limit_sec=30, rate_limit_similar=True)
        >>> for order_id in range(1000):
        ...     logger.error(f"Failed to process order {order_id}")
        >>> # Output:
        >>> # Failed to process order 0
        >>> # Failed to process order 999 (suppressed 998 similar messages)

    Attributes:
        period_sec: Minimum seconds between identical messages (default: 30)
        summary_enabled: Whether to append suppression count to resumed messages
        normalise_numbers: Normalise numbers/UUIDs for similar message matching
    """

    # Patterns for normalising variable parts of messages
    # Order matters - more specific patterns first
    _NORMALISE_PATTERNS = [
        # UUIDs: 550e8400-e29b-41d4-a716-446655440000
        (re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), "<UUID>"),
        # ISO timestamps: 2024-01-15T10:30:00.123Z or 2024-01-15T10:30:00+00:00
        (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TIMESTAMP>"),
        # Hex strings (8+ chars): 0x1a2b3c4d or 1a2b3c4d5e6f
        (re.compile(r"(?:0x)?[0-9a-fA-F]{8,}"), "<HEX>"),
        # IP addresses: 192.168.1.100
        (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<IP>"),
        # Large numbers (4+ digits): 12345, 1234567890
        (re.compile(r"\b\d{4,}\b"), "<NUM>"),
        # Small numbers with context (after common prefixes): id=123, order 42, #99
        (re.compile(r"(?<=[=#])\d+\b"), "<ID>"),
    ]

    def __init__(self, period_sec: int = 30, summary_enabled: bool = True, normalise_numbers: bool = False):
        """
        Initialise the rate limit filter.

        Args:
            period_sec: Minimum seconds between identical messages
            summary_enabled: Append "(suppressed N similar)" when resuming
            normalise_numbers: Normalise numbers/UUIDs/timestamps for similar message matching
        """
        self.period_sec = period_sec
        self.summary_enabled = summary_enabled
        self.normalise_numbers = normalise_numbers
        self._last_seen: dict[tuple, float] = defaultdict(float)
        self._skip_counts: dict[tuple, int] = defaultdict(int)

    def _normalise_message(self, message: str) -> str:
        """
        Normalise variable parts of a message for similar matching.

        Replaces numbers, UUIDs, timestamps, IPs, and hex strings with placeholders
        so that messages differing only in these values are treated as identical.

        Args:
            message: Original log message

        Returns:
            Normalised message with placeholders
        """
        if not self.normalise_numbers:
            return message

        result = message
        for pattern, replacement in self._NORMALISE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def __call__(self, record: dict) -> bool:
        """
        Filter function for Loguru.

        Args:
            record: Loguru log record dict

        Returns:
            True to allow the message, False to suppress
        """
        # Create unique key from logger name, level, and (optionally normalised) message
        message = record["message"]
        normalised = self._normalise_message(message)

        key = (
            record.get("name", ""),
            record["level"].no,
            normalised,
        )

        now = time.time()
        last_time = self._last_seen[key]

        # Check if within rate limit period
        if last_time > 0 and (now - last_time) < self.period_sec:
            self._skip_counts[key] += 1
            return False  # Suppress this message

        # Message allowed - check if we need to add suppression summary
        skip_count = self._skip_counts[key]
        if skip_count > 0 and self.summary_enabled:
            record["message"] = f"{message} (suppressed {skip_count} similar)"
            self._skip_counts[key] = 0

        self._last_seen[key] = now
        return True

    def reset(self) -> None:
        """Reset all rate limit state (useful for testing)."""
        self._last_seen.clear()
        self._skip_counts.clear()

    def get_suppressed_count(self, name: str = "", level: int = 0, message: str = "") -> int:
        """
        Get current suppressed count for a specific message.

        Args:
            name: Logger name
            level: Log level number
            message: Log message (will be normalised if normalise_numbers=True)

        Returns:
            Number of suppressed messages since last emission
        """
        normalised = self._normalise_message(message)
        key = (name, level, normalised)
        return self._skip_counts.get(key, 0)
