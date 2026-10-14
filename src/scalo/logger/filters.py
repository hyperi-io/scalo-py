"""Logging filters for scalo logger.

This module provides logging filters for sensitive-data masking by
*field name* and for rate-limiting repeated messages.

For PII-value detection (emails, phones, credit cards, national IDs,
etc.) use the newer ``scalo.logger.scrub`` pipeline -- that is
the canonical Layer 3 in the cross-language log-scrub spec. NLP/NER
scrubbing has been dropped from scope; this module ships only the
deterministic field-name regex filter.

**Components:**

- :func:`is_credential_name`: the one answer to "does this field name
  hold a credential", used by every masking path in scalo.
- :class:`SensitiveDataFilter`: masks by field name in text and dicts
  (``password=...``, ``"token":"..."``, bearer tokens, URL userinfo).
- :class:`RateLimitFilter`: suppress repeated log messages from
  tight loops; reports the suppressed-count on the next message.

Use :func:`get_sensitive_filter` for the legacy three-tier selector --
``"advanced"`` and ``"advanced-ner"`` emit deprecation warnings and
return the field-name filter.
"""

import functools
import logging
import re
import time
import warnings
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from .secrets_leak import SecretsLeakFilter

# A name holding any of these anywhere in it is a credential; scalo-rs masks by the same substring rule.
SENSITIVE_FIELDS: set[str] = {
    # Passwords
    "password",
    "passwd",
    "pwd",
    "pass",
    "passphrase",
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
    "api-key",
    "api_secret",
    # Secrets
    "secret",
    "client_secret",
    "secret_key",
    "private_key",
    "privatekey",
    "secret_access_key",
    "aws_secret_access_key",
    "aws_secret",
    "access_key",
    "access_key_id",
    # Keys a qualifying word makes a credential, where `routing_key` is not one
    "account_key",
    "azure_key",
    "client_key",
    "encryption_key",
    "gcp_key",
    "hmac_key",
    "integration_key",
    "jwt_key",
    "licence_key",
    "license_key",
    "master_key",
    "sasl_key",
    "shared_key",
    "signing_key",
    "ssh_key",
    "ssl_key",
    "tls_key",
    # Auth
    "authorization",
    "auth",
    "jaas_config",
    "header_value",
    "headers_value",
    # Session
    "session",
    "session_id",
    "sessionid",
    "cookie",
    "csrf",
    # Certificates
    "certificate",
    "cert",
    "ssl_cert",
    "private",
    # Credentials
    "credential",
    "credentials",
    "creds",
    # Database
    "db_password",
    "database_password",
    "connection_string",
    # Personal data
    "ssn",
    "tfn",
    "medicare",
    "credit_card",
    "creditcard",
    "card_number",
    "cvv",
    "pin",
    "email",
    "phone",
}

MASK_VALUE = "***REDACTED***"

# One word of a name: an acronym, a capitalised or lower-case run, or a run of digits.
_NAME_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")

# A name that says nothing until its parent qualifies it, as `tls` does `key`.
_BARE_NAMES = frozenset({"key", "keys", "value", "values"})

# Matches nothing, for a term set with no spelling in it.
_NEVER = re.compile(r"(?!)")

# The password in `scheme://user:password@host`: it runs to the `@` the host follows, so one holding `@` goes whole.
# It stops at the next `://`, so each scan ends where the next starts and a long line costs linear time.
_URL_USERINFO_RE = re.compile(r"(://[^\s:/@]*:)(?:(?!://)\S)+?(?=@[^\s@/?#]*(?:[/?#\s]|$))")
_BEARER_RE = re.compile(r"\bbearer\s+([^\s]+)", re.IGNORECASE)

# A key in text: a run of name characters no other name character precedes, then an optional closing quote.
_TEXT_KEY = r"(?<![A-Za-z0-9_.\-])(?P<key>[A-Za-z0-9_.\-]+)[\"']?"
_COLON_HEAD_RE = re.compile(rf"{_TEXT_KEY}\s*:\s*")
_EQUALS_HEAD_RE = re.compile(rf"{_TEXT_KEY}[ \t]*=(?![=>])[ \t]*")
# An unquoted value runs on across a space into a group that starts with a digit, so `TFN: 123 456 782` goes whole.
_DIGIT_GROUPS = r"(?:[ ][(+]?[0-9]{chars}*)*"
# `key: "value"` (JSON): the quotes stay so the line is still valid JSON
_JSON_VALUE_RE = re.compile(r'"[^"]*"')
# `key: 'value'` (Python repr) or `key: value` (YAML, headers)
_COLON_VALUE_RE = re.compile(r"""'[^'\n]*'|[^\s,"}]+""" + _DIGIT_GROUPS.format(chars=r"""[^\s,"}]""") + r"(?=[\s,}]|$)")
# `key=value` (env, form data, TOML, INI): a quoted value goes whole, quotes included
_EQUALS_VALUE_RE = re.compile(r""""[^"\n]*"|'[^'\n]*'|[^\s&]*""" + _DIGIT_GROUPS.format(chars=r"[^\s&]"))


def _spellings(name: str) -> tuple[str, str]:
    """Return ``name`` lower-cased as written, and as its words joined by ``_``.

    The second form reads ``secretAccessKey``, ``x-api-key`` and ``ssl.key.pem``
    as ``secret_access_key``, ``x_api_key`` and ``ssl_key_pem``.
    """
    return name.lower(), "_".join(_NAME_WORD.findall(name)).lower()


@functools.lru_cache(maxsize=64)
def _term_pattern(terms: frozenset[str]) -> re.Pattern[str]:
    """Compile one alternation over both spellings of every term."""
    spellings = {spelling for term in terms for spelling in _spellings(term) if spelling}
    if not spellings:
        return _NEVER
    return re.compile("|".join(re.escape(spelling) for spelling in sorted(spellings)))


def _names_credential(name: str, parent: str, pattern: re.Pattern[str]) -> bool:
    """Return whether ``name``, held under ``parent``, carries a term ``pattern`` matches."""
    lower, joined = _spellings(name)
    if parent and joined in _BARE_NAMES:
        lower, joined = _spellings(f"{parent}_{name}")
    return bool(pattern.search(lower) or pattern.search(joined))


def is_credential_name(name: str, parent: str = "", *, extra: Iterable[str] = ()) -> bool:
    """Return whether a field called ``name`` holds a credential.

    A name is a credential when one of :data:`SENSITIVE_FIELDS`, or a field added
    with :meth:`SensitiveDataFilter.add_sensitive_fields`, sits anywhere in it,
    case-insensitively. Separators and case changes do not hide a term, so
    ``db_password``, ``PGPASSWORD``, ``x-api-key`` and ``secretAccessKey`` all
    match. A name that merely contains a term matches too: ``tokenizer`` and
    ``mapping`` are masked, the same over-masking scalo-rs accepts.

    Args:
        name: The field name as the record, dict or config spells it.
        parent: The name of the mapping or list holding the field. It counts
            only for a bare ``key`` or ``value``, so a ``key`` under ``tls``
            is a credential and one under ``kafka`` is not.
        extra: Further terms for this call only.

    Returns:
        True when the value under ``name`` must be masked.
    """
    return _names_credential(name, parent, _credential_pattern(extra))


def _credential_pattern(extra: Iterable[str] = ()) -> re.Pattern[str]:
    """Return the matcher for the default terms, every globally added field and ``extra``."""
    terms = SensitiveDataFilter._custom_fields | {term.lower() for term in extra}
    return _term_pattern(frozenset(SENSITIVE_FIELDS | terms))


def _mask_pairs(
    text: str,
    head_re: re.Pattern[str],
    values: tuple[tuple[re.Pattern[str], str], ...],
    pattern: re.Pattern[str],
) -> str:
    """Mask the value after every ``head_re`` key that names a credential.

    Only a credential key's value is consumed, so a key inside another pair's
    value, as in ``config:password:x``, is still judged. ``values`` pairs a
    value shape with what replaces it, tried in order.
    """
    out: list[str] = []
    pos = 0
    for head in head_re.finditer(text):
        if head.start() < pos or not _names_credential(head["key"], "", pattern):
            continue
        for value_re, replacement in values:
            value = value_re.match(text, head.end())
            if value is not None:
                out.append(text[pos : head.end()])
                out.append(replacement)
                pos = value.end()
                break
    out.append(text[pos:])
    return "".join(out)


_COLON_VALUES = ((_JSON_VALUE_RE, f'"{MASK_VALUE}"'), (_COLON_VALUE_RE, MASK_VALUE))
_EQUALS_VALUES = ((_EQUALS_VALUE_RE, MASK_VALUE),)


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
       ``"token":"..."``, bearer tokens, URL passwords. A field name
       is judged by :func:`is_credential_name`.

    For PII-value detection (emails, phones, credit cards, national
    IDs, etc.) use the newer ``scalo.logger.scrub`` pipeline,
    which exposes a richer Layer 3 with algorithmic validators
    (Luhn, mod-97 IBAN, libphonenumber, TOML-driven national IDs).

    Custom fields:
        SensitiveDataFilter.add_sensitive_fields({"employee_id", "ssn"})

    Disable (not recommended):
        export LOGGING__MASK_SENSITIVE_DATA=false
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

    def _credential_pattern(self) -> re.Pattern[str]:
        """Return the credential-name matcher for this filter's fields, global and per-instance."""
        return _term_pattern(frozenset(self._get_all_sensitive_fields()))

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

    def _mask_value(self, value: Any, parent: str = "") -> Any:
        """Mask a single value based on its type; ``parent`` names the mapping or list holding it."""
        if isinstance(value, str):
            return self._mask_sensitive_string(value)
        elif isinstance(value, dict):
            return self._mask_sensitive_dict(value, parent)
        elif isinstance(value, (list, tuple)):
            return type(value)(self._mask_value(item, parent) for item in value)
        return value

    def _mask_sensitive_string(self, text: str) -> str:
        """
        Mask sensitive fields in a string using regex patterns.

        Handles multiple formats:
        - URL parameters: `field=value&`
        - JSON: `"field":"value"` or `field:"value"`
        - Python repr: `'field': 'value'`
        - Key-value pairs: `field: value` or `field=value`
        - Env, TOML and INI: `PREFIX_FIELD=value`, `field = "value"`
        - URL userinfo: `://user:password@host`

        A key is masked when :func:`is_credential_name` says so, so
        `CARGO_REGISTRY_TOKEN`, `x-api-key` and `secretAccessKey` are masked,
        and so are `token_count` and `tokenizer`.

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

        masked = _URL_USERINFO_RE.sub(rf"\1{MASK_VALUE}", text)
        masked = _BEARER_RE.sub(f"bearer {MASK_VALUE}", masked)
        pattern = self._credential_pattern()
        masked = _mask_pairs(masked, _COLON_HEAD_RE, _COLON_VALUES, pattern)
        return _mask_pairs(masked, _EQUALS_HEAD_RE, _EQUALS_VALUES, pattern)

    def _mask_sensitive_dict(self, data: dict[Any, Any], parent: str = "") -> dict[Any, Any]:
        """
        Recursively mask sensitive fields in a dictionary.

        Args:
            data: Dictionary potentially containing sensitive fields; a
                key that is not a string is judged by its ``str()``
            parent: Name of the mapping or list holding ``data``, which
                qualifies a bare ``key`` or ``value`` in it

        Returns:
            New dictionary with sensitive fields masked
        """
        if not isinstance(data, dict):
            return data

        masked_data: dict[Any, Any] = {}
        pattern = self._credential_pattern()

        for key, value in data.items():
            name = str(key)
            if _names_credential(name, parent, pattern):
                # Mask this field entirely
                masked_data[key] = MASK_VALUE
            elif isinstance(value, dict):
                masked_data[key] = self._mask_sensitive_dict(value, name)
            elif isinstance(value, (list, tuple)):
                # An entry is judged under the list's own name
                masked_data[key] = type(value)(self._mask_value(item, name) for item in value)
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
    pipeline (see :class:`scalo.logger.scrub.LayeredScrubber`).

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
            "scrubbing was dropped from scalo (false-positive rate on "
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
        >>> from scalo.logger import logger, setup
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
