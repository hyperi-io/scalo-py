"""
Logging filters for hyperi-pylib logger.

This module provides logging filters for common use cases like masking
sensitive data in log records and rate-limiting repeated messages.

**Sensitive data masking (two-tier approach):**
- **Tier 1 (default):** Fast regex-based filter (SensitiveDataFilter)
- **Tier 2 (opt-in):** ML-based Presidio filter (PresidioSensitiveDataFilter)

**Rate limiting:**
- RateLimitFilter: Suppress repeated log messages to prevent log spam from tight loops

Use `get_sensitive_filter()` to automatically select the best available filter.
"""

import logging
import re
import time
import warnings
from collections import defaultdict
from typing import Any

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


class SensitiveDataFilter(logging.Filter):
    """
    Masks sensitive data in log records (passwords, tokens, API keys, etc.).

    Applied automatically by default logger. Supports JSON, form data,
    key-value pairs, and database URLs.

    Custom fields:
        SensitiveDataFilter.add_sensitive_fields({"employee_id", "ssn"})

    Disable (not recommended):
        export HYPERI_LIB_LOGGING__MASK_SENSITIVE_DATA=false
    """

    # Class-level set for global custom fields
    _custom_fields: set[str] = set()

    def __init__(self, extra_fields: set[str] | None = None):
        """
        Initialize the sensitive data filter.

        Args:
            extra_fields: Additional fields to mask (optional)
        """
        super().__init__()
        self._instance_fields = extra_fields or set()

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

        Args:
            text: String to mask

        Returns:
            String with sensitive fields masked
        """
        if not isinstance(text, str):
            return text

        masked = text
        fields = self._get_all_sensitive_fields()

        # Database connection strings: ://user:password@host or ://:password@host
        # Pattern matches: postgres://user:secret@localhost and redis://:password@host
        # Must run before field-specific patterns to avoid double-masking
        masked = re.sub(
            r"(://[^:/@]*:)([^@]+)(@)",
            rf"\1{MASK_VALUE}\3",
            masked,
        )

        # Bearer tokens (space-separated): "bearer <token>"
        # Pattern matches: "bearer eyJhbGci..." or "Bearer eyJhbGci..."
        masked = re.sub(
            r"\bbearer\s+([^\s]+)",
            rf"bearer {MASK_VALUE}",
            masked,
            flags=re.IGNORECASE,
        )

        for field in fields:
            # Field names with underscores/hyphens don't need escaping
            # They should be matched literally

            # Pattern 1: JSON with quotes ("field":"value")
            pattern1 = rf'("{field}"\s*:\s*)"([^"]*)"'
            masked = re.sub(pattern1, rf'\1"{MASK_VALUE}"', masked, flags=re.IGNORECASE)

            # Pattern 2: JSON without key quotes (field:"value")
            pattern2 = rf'(\b{field}\s*:\s*)"([^"]*)"'
            masked = re.sub(pattern2, rf'\1"{MASK_VALUE}"', masked, flags=re.IGNORECASE)

            # Pattern 3: Form data (field=value&) or query params
            pattern3 = rf"(\b{field})=([^\s&\n]*)"
            masked = re.sub(pattern3, rf"\1={MASK_VALUE}", masked, flags=re.IGNORECASE)

            # Pattern 4: Key-value in logs without quotes (field: value)
            # Only match if not already quoted (to avoid double-masking)
            pattern4 = rf'(\b{field}\s*:\s*)([^\s\n,"}}]+)(?=[\s\n,}}]|$)'
            masked = re.sub(pattern4, rf"\1{MASK_VALUE}", masked, flags=re.IGNORECASE)

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


class PresidioSensitiveDataFilter(SensitiveDataFilter):
    """
    ML-based filter using Microsoft Presidio (50+ entity types).

    Extends SensitiveDataFilter with better accuracy for PII detection.
    Falls back to regex if Presidio not installed.

    Requires: pip install hyperi-pylib[presidio]

    Note: Slower than regex (5-50ms vs <1ms). Use for compliance-critical logs.
    """

    def __init__(self, preset: str = "standard", extra_fields: set[str] | None = None, score_threshold: float = 0.5):
        """
        Initialize Presidio-based filter.

        Args:
            preset: Entity preset ("minimal", "standard", "compliance")
            extra_fields: Additional regex fields to mask
            score_threshold: Presidio confidence threshold (0.0-1.0)
        """
        super().__init__(extra_fields=extra_fields)

        try:
            from hyperi_pylib.anonymizer import AnonymizationStrategy, Anonymizer

            self._anonymizer = Anonymizer(
                preset=preset, strategy=AnonymizationStrategy.REDACT, score_threshold=score_threshold
            )
            self._presidio_available = True
        except ImportError:
            warnings.warn(
                "Presidio not installed. Install with: pip install hyperi-pylib[presidio]. "
                "Falling back to regex-based filter.",
                ImportWarning,
                stacklevel=2,
            )
            self._presidio_available = False

    def _mask_sensitive_string(self, text: str) -> str:
        """
        Mask sensitive data using Presidio + regex fallback.

        Args:
            text: String to mask

        Returns:
            String with sensitive data masked
        """
        if not isinstance(text, str) or not text:
            return text

        # Try Presidio first (if available)
        if self._presidio_available:
            try:
                text = self._anonymizer.anonymize(text)
            except Exception as e:
                # Fall back to regex on any Presidio error
                warnings.warn(f"Presidio error: {e}. Falling back to regex filter.", RuntimeWarning, stacklevel=2)

        # Always apply regex patterns (catches Presidio misses + field names)
        return super()._mask_sensitive_string(text)


def get_sensitive_filter(
    level: str = "simple", preset: str = "standard", extra_fields: set[str] | None = None, score_threshold: float = 0.5
) -> SensitiveDataFilter:
    """
    Get appropriate sensitive data filter based on configuration.

    **Two-tier approach:**
    - **level="simple"** (default) - Fast regex-based filter
    - **level="advanced"** - ML-based Presidio filter (falls back to regex if not installed)

    Args:
        level: Filter level ("simple" or "advanced")
        preset: Presidio preset for advanced mode ("minimal", "standard", "compliance")
        extra_fields: Additional fields to mask
        score_threshold: Presidio confidence threshold (advanced mode only)

    Returns:
        SensitiveDataFilter or PresidioSensitiveDataFilter instance

    Example:
        >>> from hyperi_pylib.logger.filters import get_sensitive_filter
        >>>
        >>> # Simple (fast, regex-only)
        >>> filter = get_sensitive_filter(level="simple")
        >>>
        >>> # Advanced (ML-based, compliance mode)
        >>> filter = get_sensitive_filter(
        ...     level="advanced",
        ...     preset="compliance",
        ...     score_threshold=0.7
        ... )
    """
    if level == "advanced":
        return PresidioSensitiveDataFilter(preset=preset, extra_fields=extra_fields, score_threshold=score_threshold)
    else:
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
