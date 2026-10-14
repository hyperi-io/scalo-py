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
- :func:`mask_url_userinfo`: masks the password of every
  ``scheme://user:password@host`` in a string.
- :class:`SensitiveDataFilter`: masks by field name in text and dicts
  (``password=...``, ``"token":"..."``, bearer tokens, URL userinfo).
- :class:`RateLimitFilter`: suppress repeated log messages from
  tight loops; reports the suppressed-count on the next message.

Use :func:`get_sensitive_filter` for the legacy three-tier selector --
``"advanced"`` and ``"advanced-ner"`` emit deprecation warnings and
return the field-name filter.
"""

import array
import bisect
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

# The password runs to the last `@` a host follows, and stops at whitespace or `://` so a long line scans in linear time.
# Its runs between colons are single-class repeats, which hold no stack frame, so memory grows with a password's colons, not its length.
_URL_USERINFO_RE = re.compile(
    r"(?P<head>://[^\s:/@]*:)(?P<password>[^\s:]*(?::(?!//)[^\s:]*)*)(?=@[^\s@/?#]*(?:[/?#\s]|\Z))"
)
_BEARER_RE = re.compile(r"\bbearer\s+([^\s]+)", re.IGNORECASE)

# A key in text: a run of name characters no other name character precedes, then an optional closing quote.
_TEXT_KEY = r"(?<![A-Za-z0-9_.\-])(?P<key>[A-Za-z0-9_.\-]+)[\"']?"
_COLON_HEAD_RE = re.compile(rf"{_TEXT_KEY}\s*:\s*")
_EQUALS_HEAD_RE = re.compile(rf"{_TEXT_KEY}[ \t]*=(?![=>])[ \t]*")
# An unquoted value runs on across a space into a group that starts with a digit, so `TFN: 123 456 782` goes whole.
_DIGIT_GROUPS = r"(?:[ ][(+]?[0-9]{chars}*)*"
# A quoted value closes at the first quote no backslash escapes; a plain run and an escape never start on the same character, so the scan is linear.
_DOUBLE_QUOTED = r'"[^"\\]*(?:\\[\s\S][^"\\]*)*"'
_DOUBLE_QUOTED_LINE = r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"'
_SINGLE_QUOTED_LINE = r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'"
# A quoted value with no unescaped closing quote closes at its next quote instead, so honouring escapes never masks less than ignoring them.
_PLAIN_DOUBLE_QUOTED = r'"[^"]*"'
_PLAIN_DOUBLE_QUOTED_LINE = r'"[^"\n]*"'
_PLAIN_SINGLE_QUOTED_LINE = r"'[^'\n]*'"
# `key: "value"` (JSON): the quotes stay so the line is still valid JSON
_JSON_VALUE_RE = re.compile(f"{_DOUBLE_QUOTED}|{_PLAIN_DOUBLE_QUOTED}")
# `key: 'value'` (Python repr) or `key: value` (YAML, headers)
_COLON_VALUE_RE = re.compile(
    f"{_SINGLE_QUOTED_LINE}|{_PLAIN_SINGLE_QUOTED_LINE}|"
    + r"""[^\s,"}]+"""
    + _DIGIT_GROUPS.format(chars=r"""[^\s,"}]""")
    + r"(?=[\s,}]|$)"
)
# `key=value` (env, form data, TOML, INI): a quoted value goes whole, quotes included
_EQUALS_VALUE_RE = re.compile(
    f"{_DOUBLE_QUOTED_LINE}|{_SINGLE_QUOTED_LINE}|{_PLAIN_DOUBLE_QUOTED_LINE}|{_PLAIN_SINGLE_QUOTED_LINE}|"
    + r"[^\s&]*"
    + _DIGIT_GROUPS.format(chars=r"[^\s&]")
)
# The longest `Name(...)` value read as one value, in UTF-8 bytes as scalo-rs counts it; a longer one is read as unquoted text.
_MAX_WRAPPER_LEN = 4096
_WRAPPER_OPEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\(")
# A parenthesis, or a quote with the backslashes before it; an even run escapes nothing, so the quote can close a string.
_WRAPPER_TOKEN_RE = re.compile(r"""[()]|(?<!\\)(\\*+)["']""")


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


def mask_url_userinfo(text: str, mask: str = MASK_VALUE, *, keep_user: bool = True) -> str:
    """Return ``text`` with the password of every ``scheme://user:password@host`` in it masked.

    The password runs to the last ``@`` a host follows, so one holding ``@``,
    ``/``, ``?`` or ``#`` is masked whole. Nothing tells such a password from
    an ``@`` later in the path or query, so ``https://u:p@host/x?to=ops@example.com``
    is masked through to ``example.com``, and ``https://host:8443/@scope/pkg``
    loses its port. A URL with no ``:`` in its userinfo, such as
    ``ssh://git@host``, is left alone. The scan stops at whitespace and at the
    next ``://``, so a long line costs linear time.

    Args:
        text: Any text: a log line, an error message, a config value.
        mask: What replaces the password, inserted as written.
        keep_user: Keep the user, so the text still says whose credential it
            was. False replaces the whole ``user:password``.

    Returns:
        ``text`` with every URL password masked.
    """
    if keep_user:
        return _URL_USERINFO_RE.sub(lambda found: found["head"] + mask if found["password"] else found[0], text)
    return _URL_USERINFO_RE.sub(lambda _found: "://" + mask, text)


class _Wrappers:
    """Find where each ``Name(...)`` value in one text ends, such as ``Some("...")`` or ``Token(value='...')``.

    Parentheses nest, and a string inside, single or double quoted, is skipped
    past its backslash escapes and may span lines.

    The walk on from any parenthesis or quote is the same whichever value
    reached it, so one pass from the right records, for every such token, the
    first token on its walk one nesting level further out. A group ends just
    before that token as seen from the token after its ``(``. The pass costs
    linear time and 9 bytes a token, and runs only for a text holding a
    ``Name(`` value.
    """

    __slots__ = ("_positions", "_rises", "_text")

    def __init__(self, text: str) -> None:
        self._text = text
        typecode = "i" if len(text) < 2**31 else "q"
        self._positions = array.array(typecode)
        # Token index -> the first token further out on its walk, or -1 when an unclosed string ends the walk first.
        self._rises = array.array(typecode)

    def end(self, start: int) -> int | None:
        """Return the end of the ``Name(...)`` value at ``start``, or None when none closes within the window."""
        opened = _WRAPPER_OPEN_RE.match(self._text, start)
        if opened is None:
            return None
        if not self._rises:
            self._index()
        rise = self._rises[bisect.bisect_left(self._positions, opened.end() - 1) + 1]
        if rise < 0:
            return None
        end = self._positions[rise - 1] + 1
        if end - start > _MAX_WRAPPER_LEN:
            return None
        # A character is at most 4 UTF-8 bytes, so only a longer value needs counting.
        if end - start > _MAX_WRAPPER_LEN // 4:
            if len(self._text[start:end].encode("utf-8", "surrogatepass")) > _MAX_WRAPPER_LEN:
                return None
        return end

    def _index(self) -> None:
        """Run the pass from the right over every parenthesis and quote in the text."""
        text, positions = self._text, self._positions
        closable = bytearray()
        for found in _WRAPPER_TOKEN_RE.finditer(text):
            positions.append(found.end() - 1)
            closable.append(found[1] is not None and len(found[1]) % 2 == 0)
        count = len(positions)
        # Index `count` stands for the end of the text, which nothing lies beyond.
        rises = array.array(positions.typecode, [-1]) * (count + 1)
        # The nearest quote ahead that can close a string, by quote character.
        closer = {'"': -1, "'": -1}
        for index in range(count - 1, -1, -1):
            char = text[positions[index]]
            if char == ")":
                rises[index] = index + 1
            elif char == "(":
                inside = rises[index + 1]
                rises[index] = rises[inside] if inside >= 0 else -1
            else:
                close = closer[char]
                rises[index] = rises[close + 1] if close >= 0 else -1
                if closable[index]:
                    closer[char] = index
        self._rises = rises


def _value_end(text: str, start: int, values: tuple[tuple[re.Pattern[str], str], ...]) -> tuple[int, str] | None:
    """Return where the first of ``values`` that matches at ``start`` ends, and what replaces it."""
    for value_re, replacement in values:
        value = value_re.match(text, start)
        if value is not None:
            return value.end(), replacement
    return None


def _mask_pairs(
    text: str,
    head_re: re.Pattern[str],
    values: tuple[tuple[re.Pattern[str], str], ...],
    pattern: re.Pattern[str],
) -> str:
    """Mask the value after every ``head_re`` key that names a credential.

    Only a credential key's value is consumed, so a key inside another pair's
    value, as in ``config:password:x``, is still judged. ``values`` pairs a
    value shape with what replaces it, tried in order. A ``Name(...)`` value
    such as ``Some("a b")`` goes whole whenever it runs further than that
    shape, so a Rust ``Debug`` dump or a Python repr of a wrapped credential
    is masked.
    """
    out: list[str] = []
    pos = 0
    wrappers = _Wrappers(text)
    for head in head_re.finditer(text):
        if head.start() < pos or not _names_credential(head["key"], "", pattern):
            continue
        value = _value_end(text, head.end(), values)
        wrapped = wrappers.end(head.end())
        if wrapped is not None and (value is None or wrapped > value[0]):
            value = (wrapped, MASK_VALUE)
        if value is None:
            continue
        out.append(text[pos : head.end()])
        out.append(value[1])
        pos = value[0]
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
        - Rust `Debug` and Python repr wrappers: `field: Some("value")`
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

        masked = mask_url_userinfo(text)
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
