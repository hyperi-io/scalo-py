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
- :func:`url_passwords`: lists the URL passwords that masker would mask.
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
from collections.abc import Iterable, Iterator
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

# Where a URL's user ends, since it holds no whitespace, `:`, `/` or `@`.
_URL_USER_END_RE = re.compile(r"[\s:/@]")
# Where a URL's password run ends: whitespace, or the next `://`.
_URL_RUN_END_RE = re.compile(r"\s|://")
_BEARER_RE = re.compile(r"\bbearer\s+([^\s]+)", re.IGNORECASE)
# A query parameter right after `?` or `&` whose value is a signature or a session token, the names scalo-rs reads too.
_QUERY_SIGNATURE_RE = re.compile(
    r"(?<=[?&])(?P<name>sig|x-amz-signature|x-amz-security-token|x-goog-signature)=[^&\s\"']*",
    re.IGNORECASE,
)
# httpx's error quotes a refused header value whole, auth scheme and all, so the quoted value goes whole, and an unclosed one to the end of its line.
_REFUSED_HEADER_VALUE_RE = re.compile(
    r"(?P<head>\billegal header value b?)(?P<quote>['\"])(?:(?!(?P=quote))[^\\\n]|\\.)*(?P=quote)?",
    re.IGNORECASE,
)


def _mask_refused_header_value(match: re.Match[str]) -> str:
    """Keep the message and the quotes, and replace the refused header value."""
    return f"{match['head']}{match['quote']}{MASK_VALUE}{match['quote']}"


# A key in text: a run of name characters no other name character precedes, then an optional closing quote.
_TEXT_KEY = r"(?<![A-Za-z0-9_.\-])(?P<key>[A-Za-z0-9_.\-]+)[\"']?"
# `key::value` separates with both colons, so the value starts after the second.
_COLON_HEAD_RE = re.compile(rf"{_TEXT_KEY}\s*::?\s*")
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
_JSON_MASK = f'"{MASK_VALUE}"'
# `key: 'value'` (Python repr)
_SINGLE_QUOTED_VALUE_RE = re.compile(f"{_SINGLE_QUOTED_LINE}|{_PLAIN_SINGLE_QUOTED_LINE}")
# `key: value` (YAML, headers)
_COLON_UNQUOTED_RE = re.compile(r"""[^\s,"}]+""" + _DIGIT_GROUPS.format(chars=r"""[^\s,"}]""") + r"(?=[\s,}]|$)")
# `key="value"` (env, form data, TOML, INI): a quoted value goes whole, quotes included
_EQUALS_QUOTED_RE = re.compile(
    f"{_DOUBLE_QUOTED_LINE}|{_SINGLE_QUOTED_LINE}|{_PLAIN_DOUBLE_QUOTED_LINE}|{_PLAIN_SINGLE_QUOTED_LINE}"
)
# `key=value`, which may be empty
_EQUALS_UNQUOTED_RE = re.compile(r"[^\s&]*" + _DIGIT_GROUPS.format(chars=r"[^\s&]"))
# The longest `Name(...)` value read as one value, in UTF-8 bytes as scalo-rs counts it.
_MAX_WRAPPER_LEN = 4096
_WRAPPER_OPEN_RE = re.compile(r"[A-Za-z0-9_]+\(")
# A parenthesis, or a quote with the backslashes before it; an even run escapes nothing, so the quote can close a string.
_WRAPPER_TOKEN_RE = re.compile(r"""[()]|(?<!\\)(\\*+)["']""")
# A key holding this names an authorization header, whose value is a scheme followed by its credentials.
_AUTHORIZATION = "authorization"
# HTTP authentication schemes, the IANA registry then vendor ones, the list scalo-rs carries too.
_AUTH_SCHEMES = frozenset(
    {
        "basic",
        "bearer",
        "concealed",
        "digest",
        "dpop",
        "gnap",
        "hoba",
        "mutual",
        "negotiate",
        "oauth",
        "privatetoken",
        "scram-sha-1",
        "scram-sha-256",
        "vapid",
        "apikey",
        "aws4-hmac-sha256",
        "ntlm",
        "sharedaccesssignature",
        "sharedkey",
        "sharedkeylite",
        "splunk",
        "ssws",
        "token",
    }
)
_BLANKS_RE = re.compile(r"[ \t]++")
# A credential item: runs up to white space, `,`, `}` or `"`, joined by a quoted string opened at its start or after `=`.
_CREDENTIAL_RUN_RE = re.compile(r'[^\s,}"]++')
# After `=` an item also ends at `&`, which separates form fields there.
_FORM_CREDENTIAL_RUN_RE = re.compile(r'[^\s,&}"]++')
_CREDENTIAL_QUOTED_RE = re.compile(f"{_DOUBLE_QUOTED_LINE}|{_PLAIN_DOUBLE_QUOTED_LINE}")
_CREDENTIAL_COMMA_RE = re.compile(r"[ \t]*+,[ \t]*+")


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
    out: list[str] = []
    copied = 0
    for head, colon, at in _url_userinfo(text):
        if not keep_user:
            out.append(text[copied:head] + "://" + mask)
            copied = at
        elif at > colon + 1:
            out.append(text[copied : colon + 1] + mask)
            copied = at
    out.append(text[copied:])
    return "".join(out)


def url_passwords(text: str) -> list[str]:
    """Return every non-empty URL password in ``text``, in order, as :func:`mask_url_userinfo` masks them.

    Both read the text with one scanner, so a password listed here is exactly
    one the masker replaces.

    Args:
        text: Any text: a log line, an error message, a config value.

    Returns:
        The password of each ``scheme://user:password@host``, left to right.
    """
    return [text[colon + 1 : at] for _head, colon, at in _url_userinfo(text) if at > colon + 1]


def _url_userinfo(text: str) -> Iterator[tuple[int, int, int]]:
    """Yield where the ``://``, the ``:`` ending the user, and the ``@`` ending the password sit, for each URL.

    The password runs from the user's ``:`` to the last ``@`` before
    whitespace or the next ``://``; a host always follows that ``@``. The next
    URL is looked for from that ``@``. Each part is found with a string search
    or a single-class pattern, so the scan holds no memory per character and
    costs linear time.
    """
    head = text.find("://")
    while head != -1:
        user_end = _URL_USER_END_RE.search(text, head + 3)
        colon = user_end.start() if user_end else len(text)
        if text.startswith(":", colon):
            run_end = _URL_RUN_END_RE.search(text, colon + 1)
            at = text.rfind("@", colon + 1, run_end.start() if run_end else len(text))
            if at != -1:
                yield head, colon, at
                head = text.find("://", at)
                continue
        head = text.find("://", head + 1)


class _Wrappers:
    """Find where each ``Name(...)`` value in one text ends, such as ``Some("...")`` or ``Token(value='...')``.

    Parentheses nest, and a string inside, single or double quoted, may span
    lines. A string closes at its first quote no backslash escapes or, when the
    text holds no such quote after it, at its next quote.

    The walk on from any parenthesis or quote is the same whichever value
    reached it, so one pass from the right records, for every such token, the
    first token on its walk one nesting level further out, and whether a
    string on the way closed at an escaped quote. A group ends just before
    that token as seen from the token after its ``(``. The pass costs linear
    time and 10 bytes a token, and runs only for a text holding a ``Name(``
    value.
    """

    __slots__ = ("_escaped", "_positions", "_rises", "_text")

    def __init__(self, text: str) -> None:
        self._text = text
        typecode = "i" if len(text) < 2**31 else "q"
        self._positions = array.array(typecode)
        # Token index -> the first token further out on its walk, or -1 when an unclosed string ends the walk first.
        self._rises = array.array(typecode)
        # Token index -> whether a string on that walk closed at a quote a backslash escapes.
        self._escaped = bytearray()

    def read(self, start: int, never: int) -> tuple[int | None, int | None]:
        """Return where a pass ends the ``Name(...)`` value at ``start``, and how far the value runs.

        A pass ends the value at its close only when the name starts with a
        letter or ``_``, every string in it closes at a quote no backslash
        escapes, and it closes within the window; otherwise the first is None.
        The value runs to its close, or to ``never`` when it does not close
        within the window. Both are None when no ``Name(`` starts at ``start``.
        """
        opened = _WRAPPER_OPEN_RE.match(self._text, start)
        if opened is None:
            return None, None
        close = self._close(start, opened.end())
        if close is None:
            return None, never
        end, escaped = close
        return (None if escaped or self._text[start].isdigit() else end), end

    def _close(self, start: int, inside: int) -> tuple[int, bool] | None:
        """Return where the value at ``start``, whose ``(`` ends at ``inside``, closes within the window, and whether a string in it closed at an escaped quote."""
        if not self._rises:
            self._index()
        token = bisect.bisect_left(self._positions, inside - 1) + 1
        rise = self._rises[token]
        if rise < 0:
            return None
        end = self._positions[rise - 1] + 1
        if end - start > _MAX_WRAPPER_LEN:
            return None
        # A character is at most 4 UTF-8 bytes, so only a longer value needs counting.
        if end - start > _MAX_WRAPPER_LEN // 4:
            if len(self._text[start:end].encode("utf-8", "surrogatepass")) > _MAX_WRAPPER_LEN:
                return None
        return end, bool(self._escaped[token])

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
        escaped = bytearray(count + 1)
        # The nearest quote ahead that can close a string, and the nearest of either kind, by quote character.
        closer = {'"': -1, "'": -1}
        nearest = {'"': -1, "'": -1}
        for index in range(count - 1, -1, -1):
            char = text[positions[index]]
            if char == ")":
                rises[index] = index + 1
            elif char == "(":
                inside = rises[index + 1]
                if inside >= 0:
                    rises[index] = rises[inside]
                    escaped[index] = escaped[index + 1] | escaped[inside]
            else:
                close = closer[char]
                plain = close < 0
                if plain:
                    close = nearest[char]
                if close >= 0:
                    rises[index] = rises[close + 1]
                    escaped[index] = plain | escaped[close + 1]
                if closable[index]:
                    closer[char] = index
                nearest[char] = index
        self._rises = rises
        self._escaped = escaped


# A span of text and what replaces it; None cuts it, for a run straight after a mask.
type _Span = tuple[int, int, str | None]


class _Values:
    """Read the value after each key in one text, keys taken in rising order of position.

    A read returns where the pass ends the value, or None when it replaces
    nothing; the mask that replaces it; and how far the value runs. A quoted
    value that never closes runs to the end of its line, or, when its reading
    may cross lines, as a double-quoted value after ``:`` and a ``Name(...)``
    value may, to the end of the text short of a line break that ends it. A
    ``Name(...)`` value runs to its close, or to the end of the text when it
    does not close within the window. An unquoted value read as an
    authorization header's runs on past its scheme through the credentials
    after it, and so does one whose first word is an authentication scheme.
    """

    __slots__ = ("_line_end", "_text", "_text_end", "_wrappers")

    def __init__(self, text: str) -> None:
        self._text = text
        self._wrappers = _Wrappers(text)
        self._line_end = -1
        self._text_end = len(text) - 1 if text.endswith("\n") else len(text)

    def colon(self, start: int, header: bool) -> tuple[int | None, str, int]:
        """Read the value after a colon at ``start``, as an authorization header's when ``header`` is set."""
        text = self._text
        if text.startswith('"', start):
            found = _JSON_VALUE_RE.match(text, start)
            if found is not None:
                return found.end(), _JSON_MASK, found.end()
            return None, _JSON_MASK, self._text_end
        found = _SINGLE_QUOTED_VALUE_RE.match(text, start)
        if found is not None:
            return found.end(), MASK_VALUE, found.end()
        unquoted = _COLON_UNQUOTED_RE.match(text, start)
        end = None if unquoted is None else unquoted.end()
        if text.startswith("'", start):
            return end, MASK_VALUE, self._line(start)
        return self._unquoted(start, end, header, _CREDENTIAL_RUN_RE)

    def equals(self, start: int, header: bool) -> tuple[int | None, str, int]:
        """Read the value after an equals sign at ``start``, as an authorization header's when ``header`` is set."""
        text = self._text
        found = _EQUALS_QUOTED_RE.match(text, start)
        if found is not None:
            return found.end(), MASK_VALUE, found.end()
        unquoted = _EQUALS_UNQUOTED_RE.match(text, start)
        end = start if unquoted is None else unquoted.end()
        if text.startswith(('"', "'"), start):
            return end, MASK_VALUE, self._line(start)
        return self._unquoted(start, end, header, _FORM_CREDENTIAL_RUN_RE)

    def _unquoted(
        self, start: int, end: int | None, header: bool, run_re: re.Pattern[str]
    ) -> tuple[int | None, str, int]:
        """Read an unquoted value ending at ``end``, or further when a ``Name(...)`` value starts at ``start``.

        With no ``Name(...)`` value there, the value ending at ``end`` is a
        scheme when ``header`` is set or it is one of the authentication
        schemes, and then the credentials after it are read too, each item a
        ``run_re`` run.
        """
        wrapped, reach = self._wrappers.read(start, self._text_end)
        if wrapped is not None and (end is None or wrapped > end):
            end = wrapped
        elif reach is None and end is not None and end > start:
            if header or self._text[start:end].lower() in _AUTH_SCHEMES:
                end = self._credentials(end, run_re)
        low = start if end is None else end
        return end, MASK_VALUE, low if reach is None else max(low, reach)

    def _credentials(self, scheme_end: int, run_re: re.Pattern[str]) -> int:
        """Return where the credentials after a scheme ending at ``scheme_end`` end, or ``scheme_end`` when none follow.

        Spaces or tabs separate the scheme from its credentials, which are
        items separated by commas, as in ``Digest username="u", response="r"``.
        They never cross a line.
        """
        text = self._text
        gap = _BLANKS_RE.match(text, scheme_end)
        if gap is None:
            return scheme_end
        end = scheme_end
        at = gap.end()
        while (item_end := self._credential_item(at, run_re)) > at:
            end = item_end
            comma = _CREDENTIAL_COMMA_RE.match(text, end)
            if comma is None:
                break
            at = comma.end()
        return end

    def _credential_item(self, start: int, run_re: re.Pattern[str]) -> int:
        """Return where the credential item at ``start`` ends, or ``start`` when none starts there.

        The item is ``run_re`` runs joined by quoted strings. A quoted string
        opens at the item's start or after ``=``, and one that does not close
        on its line takes the item to the end of the line.
        """
        text = self._text
        end = start
        while True:
            if text.startswith('"', end) and (end == start or text[end - 1] == "="):
                quoted = _CREDENTIAL_QUOTED_RE.match(text, end)
                if quoted is None:
                    return self._line(end)
                end = quoted.end()
                continue
            run = run_re.match(text, end)
            if run is None:
                return end
            end = run.end()

    def _line(self, start: int) -> int:
        """Return where the line holding ``start`` ends: its line break, or the end of the text."""
        if start > self._line_end:
            found = self._text.find("\n", start)
            self._line_end = len(self._text) if found == -1 else found
        return self._line_end


def _pair_spans(
    text: str, head_re: re.Pattern[str], colon: bool, pattern: re.Pattern[str]
) -> tuple[list[tuple[int, int, str]], list[_Span]]:
    """Return the value after every ``head_re`` key that names a credential, and the run past each one.

    Only a credential key's value is consumed, so a key inside another pair's
    value, as in ``config:password:x``, is still judged.
    """
    values = _Values(text)
    read = values.colon if colon else values.equals
    spans: list[tuple[int, int, str]] = []
    runs: list[_Span] = []
    copied = 0
    for head in head_re.finditer(text):
        key = head["key"]
        if head.start() < copied or not _names_credential(key, "", pattern):
            continue
        start = head.end()
        end, mask, reach = read(start, _AUTHORIZATION in key.lower())
        if end is not None:
            spans.append((start, end, mask))
            copied = end
        low = start if end is None else end
        if reach > low:
            runs.append((low, reach, None if end is not None else mask))
    return spans, runs


def _after(runs: list[_Span], spans: list[tuple[int, int, str]]) -> list[_Span]:
    """Return ``runs``, placed in the text ``spans`` were read from, as they sit once each span is replaced by its mask.

    A run ending inside a span ends after that span's mask.
    """
    starts = [start for start, _end, _mask in spans]
    mask_ends = []
    moved = 0
    for start, end, mask in spans:
        moved += len(mask) - (end - start)
        mask_ends.append(end + moved)

    def place(at: int) -> int:
        index = bisect.bisect_right(starts, at) - 1
        if index < 0:
            return at
        start, end, mask = spans[index]
        if at >= end:
            return mask_ends[index] + at - end
        if at > start:
            return mask_ends[index]
        return mask_ends[index] - len(mask)

    return [(place(start), place(end), mask) for start, end, mask in runs]


def _apply(text: str, spans: Iterable[_Span]) -> str:
    """Return ``text`` with each span replaced by its mask, or cut when it has none.

    Spans that overlap or touch merge, and the first of them decides the mask,
    so a value and the run past it come out as one mask.
    """
    ordered = sorted(spans, key=lambda span: (span[0], span[2] is None))
    out: list[str] = []
    copied = 0
    index = 0
    while index < len(ordered):
        start, end, mask = ordered[index]
        index += 1
        while index < len(ordered) and ordered[index][0] <= end:
            end = max(end, ordered[index][1])
            index += 1
        out.append(text[copied:start])
        if mask is not None:
            out.append(mask)
        copied = end
    out.append(text[copied:])
    return "".join(out)


def _mask_pairs(text: str, pattern: re.Pattern[str]) -> str:
    """Mask the value after every ``key: value``, then every ``key=value``, whose key ``pattern`` names a credential.

    Each pass replaces a value only as far as its first reading goes, and the
    equals pass reads the colon pass's output. The run past a value that never
    closes, or past a ``Name(...)`` value that first reading does not take
    whole, is masked after both passes, so a key inside a run is still read
    and its value still masked.
    """
    spans, runs = _pair_spans(text, _COLON_HEAD_RE, True, pattern)
    text = _apply(text, spans)
    runs = _after(runs, spans)
    spans, more = _pair_spans(text, _EQUALS_HEAD_RE, False, pattern)
    return _apply(text, [*spans, *more, *runs])


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
        - Authorization headers, any scheme: `Authorization: Basic value`,
          `authorization=Digest username="u", response="r"`
        - An authentication scheme after any credential key: `x-api-key: Token value`
        - A key and value joined by `::`: `password::value`
        - URL userinfo: `://user:password@host`
        - Signed URL query parameters: `?sig=`, `&X-Amz-Signature=`,
          `&X-Amz-Security-Token=`, `&X-Goog-Signature=`
        - A header value httpx refused to send: `Illegal header value b'...'`

        A key is masked when :func:`is_credential_name` says so, so
        `CARGO_REGISTRY_TOKEN`, `x-api-key` and `secretAccessKey` are masked,
        and so are `token_count` and `tokenizer`. A quoted or `Name(...)`
        value that never closes is masked to the end of its line, or to the
        end of the text when its reading may cross lines.

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
        masked = _QUERY_SIGNATURE_RE.sub(lambda match: f"{match['name']}={MASK_VALUE}", masked)
        masked = _REFUSED_HEADER_VALUE_RE.sub(_mask_refused_header_value, masked)
        masked = _BEARER_RE.sub(f"bearer {MASK_VALUE}", masked)
        return _mask_pairs(masked, self._credential_pattern())

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
