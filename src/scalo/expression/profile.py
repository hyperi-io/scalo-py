# Project:   scalo
# File:      expression/profile.py
# Purpose:   expression profile -- allowed subset of CEL
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Expression Profile -- the allowed subset of CEL.

The profile restricts CEL to operations with a bounded cost per record. Regex,
per-element iteration and time functions are restricted by default, and each
category is unlocked by a :class:`ProfileConfig` flag, which apps set under the
``expression`` key of the config cascade.

See: docs/api/EXPRESSION.md
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from .diagnostic import Diagnostic, Span

__all__ = [
    "ALLOWED_FUNCTIONS",
    "DISALLOWED_FUNCTIONS",
    "KNOWN_FUNCTIONS",
    "RESTRICTED_ITERATION",
    "RESTRICTED_REGEX",
    "RESTRICTED_TIME",
    "ProfileConfig",
    "cascade_profile",
    "check_profile",
    "scan_profile",
]

# Functions allowed in the expression profile.
#
# This is an ALLOWLIST and is enforced as one: a function that appears in neither
# this set nor DISALLOWED_FUNCTIONS is rejected. Adding a function here is what
# permits it, so anything CEL supports and the profile should accept has to be
# listed -- the cost of omission is a valid expression refused.
ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {
        # String methods
        "contains",
        "startsWith",
        "endsWith",
        # Size / existence
        "size",
        "has",
        # Type casts
        "int",
        "uint",
        "double",
        "string",
        "bool",
        "bytes",
        # Type introspection. Constant-time, and `dyn()` only relaxes static
        # type-checking; neither iterates.
        "type",
        "dyn",
        # Timestamp and duration accessors. Cheap field reads on a value that is
        # already a timestamp -- and since `timestamp()` and `duration()` are
        # denied, these are only reachable when the datastore hands the
        # expression a typed value rather than a JSON scalar. Listed so that case
        # is not refused.
        "getDate",
        "getDayOfMonth",
        "getDayOfWeek",
        "getDayOfYear",
        "getFullYear",
        "getHours",
        "getMilliseconds",
        "getMinutes",
        "getMonth",
        "getSeconds",
    }
)

# Restricted categories, each blocked until its ProfileConfig flag is set.
RESTRICTED_REGEX: frozenset[str] = frozenset({"matches"})
RESTRICTED_ITERATION: frozenset[str] = frozenset({"map", "filter", "exists", "all", "exists_one"})
RESTRICTED_TIME: frozenset[str] = frozenset({"timestamp", "duration"})

# Every restricted function, whatever unlocks it.
DISALLOWED_FUNCTIONS: frozenset[str] = RESTRICTED_REGEX | RESTRICTED_ITERATION | RESTRICTED_TIME

# Known function names (union of allowed + disallowed) for error messages.
KNOWN_FUNCTIONS: frozenset[str] = ALLOWED_FUNCTIONS | DISALLOWED_FUNCTIONS

_REASONS: dict[str, str] = {
    **dict.fromkeys(
        RESTRICTED_REGEX,
        "Regex has unbounded cost per record. Use contains()/startsWith()/endsWith() instead, "
        "or set allow_regex: true in expression config.",
    ),
    **dict.fromkeys(
        RESTRICTED_ITERATION,
        "Per-element iteration has O(n) cost proportional to collection size. "
        "Set allow_iteration: true in expression config to permit.",
    ),
    **dict.fromkeys(
        RESTRICTED_TIME,
        "Time functions excluded -- ClickHouse handles time natively. "
        "Set allow_time: true in expression config to permit.",
    ),
}

# CEL allows whitespace between a function name and its `(`, so a call written `map\n(` is still a call.
_CALL_GAP: frozenset[int] = frozenset(b" \t\r\n\f\v")

_QUOTES: frozenset[int] = frozenset(b"\"'")
_BACKSLASH = 0x5C
_BACKTICK = 0x60

# A name of exactly these letters directly before a quote opens a string or bytes literal, raw with r or R.
_LITERAL_PREFIXES: frozenset[bytes] = frozenset({b"r", b"R", b"b", b"B", b"br", b"bR", b"Br", b"BR"})

# The bytes CEL's lexer allows inside a backtick-quoted identifier.
_ESCAPED_IDENT_BYTES: frozenset[int] = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-/ ")

# Keywords and built-ins that read like a call but are never refused.
_SKIP_NAMES: frozenset[str] = frozenset(
    {"true", "false", "null", "in", "has", "int", "uint", "double", "string", "bool"}
)


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    """Which restricted categories an expression may use. Every flag defaults off.

    Attributes:
        allow_regex: Permit ``matches()``, whose cost per record is unbounded.
        allow_iteration: Permit ``map()``, ``filter()``, ``exists()``, ``all()`` and
            ``exists_one()``, whose cost grows with the collection.
        allow_time: Permit ``timestamp()`` and ``duration()``.
    """

    allow_regex: bool = False
    allow_iteration: bool = False
    allow_time: bool = False

    def blocked_functions(self) -> frozenset[str]:
        """Return the functions this profile refuses beyond the unknown ones."""
        blocked: set[str] = set()
        if not self.allow_regex:
            blocked |= RESTRICTED_REGEX
        if not self.allow_iteration:
            blocked |= RESTRICTED_ITERATION
        if not self.allow_time:
            blocked |= RESTRICTED_TIME
        return frozenset(blocked)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> ProfileConfig:
        """Build a profile from the ``expression`` config section.

        Args:
            raw: The section, or ``None`` for an absent one. Keys other than the three
                flags are ignored.

        Returns:
            The profile the section describes.

        Raises:
            ValueError: A flag is set to something other than a boolean.
        """
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise ValueError(f"the expression config is not a mapping: {raw!r}")
        flags: dict[str, bool] = {}
        for flag in fields(cls):
            value = raw.get(flag.name, False)
            if not isinstance(value, bool):
                raise ValueError(f"expression.{flag.name} is {value!r}, not true or false")
            flags[flag.name] = value
        return cls(**flags)


@dataclass(slots=True)
class _Latch:
    """The profile the cascade supplied, once it has supplied one."""

    profile: ProfileConfig | None = None


_LATCH = _Latch()


def cascade_profile() -> ProfileConfig:
    """Return the profile the config cascade sets under ``expression``.

    Once the cascade has an ``expression`` section that reads cleanly, that profile is
    kept for the life of the process. Until then the default profile is returned and not
    kept, so a read before config loads never pins the defaults.

    Returns:
        The cascade's profile, or :class:`ProfileConfig` with every restriction on.
    """
    if _LATCH.profile is not None:
        return _LATCH.profile
    try:
        from scalo.config import settings

        raw = settings.get("expression", None)
        if raw is None:
            return ProfileConfig()
        profile = ProfileConfig.from_mapping(raw)
    except Exception:
        # An unreadable cascade keeps every restriction on rather than failing the caller.
        return ProfileConfig()
    _LATCH.profile = profile
    return profile


def _string_end(data: bytes, quote_at: int, raw: bool) -> int:
    """Return the index after the string literal whose opening quote is at ``quote_at``.

    The literal is read as CEL's lexer reads it: three quotes open a triple-quoted
    literal that runs to the next three, a raw literal has no escapes, and a one-line
    literal ends at a newline, which CEL refuses.
    """
    quote = data[quote_at]
    triple = bytes((quote, quote, quote))
    if data.startswith(triple, quote_at):
        i = quote_at + 3
        while i < len(data):
            if data.startswith(triple, i):
                return i + 3
            i += 2 if not raw and data[i] == _BACKSLASH else 1
        # With no closing triple, CEL reads an empty literal, then a new one at the third quote.
        return quote_at + 2
    i = quote_at + 1
    while i < len(data):
        byte = data[i]
        if byte == quote:
            return i + 1
        if byte in (0x0A, 0x0D):
            return i
        i += 2 if not raw and byte == _BACKSLASH else 1
    return len(data)


def _gap_end(data: bytes, i: int) -> int:
    """Return the index after the whitespace and ``//`` comments starting at ``i``."""
    while i < len(data):
        if data[i] in _CALL_GAP:
            i += 1
        elif data.startswith(b"//", i):
            newline = data.find(b"\n", i)
            i = len(data) if newline == -1 else newline
        else:
            break
    return i


def _escaped_ident_end(data: bytes, start: int) -> int:
    """Return the index after a backtick-quoted identifier at ``start``, or after the lone backtick."""
    i = start + 1
    while i < len(data) and data[i] in _ESCAPED_IDENT_BYTES:
        i += 1
    if i > start + 1 and i < len(data) and data[i] == _BACKTICK:
        return i + 1
    return start + 1


def _is_ident_start(byte: int) -> bool:
    return (0x41 <= byte <= 0x5A) or (0x61 <= byte <= 0x7A) or byte == 0x5F


def _is_ident_char(byte: int) -> bool:
    return _is_ident_start(byte) or (0x30 <= byte <= 0x39)


def scan_profile(expr: str, profile: ProfileConfig | None = None) -> list[Diagnostic]:
    """Find each call the profile refuses, with the byte span of its function name.

    The scan reads string and bytes literals (quoted, triple-quoted and raw), ``//``
    comments and backtick-quoted identifiers the way CEL's lexer does, so a name inside
    one is never reported, and whitespace or a comment between a name and its ``(``
    does not hide a call.

    Args:
        expr: CEL expression text.
        profile: The profile to scan under. ``None`` means the cascade's.

    Returns:
        One diagnostic per refused call, in the order they appear. Empty when the
        expression stays inside the profile.
    """
    blocked = (profile if profile is not None else cascade_profile()).blocked_functions()
    data = expr.encode("utf-8")
    found: list[Diagnostic] = []
    i = 0
    while i < len(data):
        byte = data[i]
        if byte in _QUOTES:
            i = _string_end(data, i, raw=False)
            continue
        if data.startswith(b"//", i):
            i = _gap_end(data, i)
            continue
        if byte == _BACKTICK:
            i = _escaped_ident_end(data, i)
            continue
        if not _is_ident_start(byte):
            i += 1
            continue
        start = i
        while i < len(data) and _is_ident_char(data[i]):
            i += 1
        word = data[start:i]
        if i < len(data) and data[i] in _QUOTES and word in _LITERAL_PREFIXES:
            i = _string_end(data, i, raw=b"r" in word.lower())
            continue
        name = word.decode("ascii")
        peek = _gap_end(data, i)
        if peek >= len(data) or data[peek] != 0x28 or name in _SKIP_NAMES:
            continue
        span = Span(start, i)
        if name in blocked:
            message = f"Function '{name}()' is not allowed in the expression profile. {_REASONS[name]}"
            found.append(Diagnostic(message, span))
        elif name not in KNOWN_FUNCTIONS:
            message = (
                f"Function '{name}()' is not in the expression profile. Check the spelling, "
                "or add it to ALLOWED_FUNCTIONS if it belongs in the profile."
            )
            found.append(Diagnostic(message, span))
    return found


def check_profile(expr: str, profile: ProfileConfig | None = None) -> list[str]:
    """Return :func:`scan_profile`'s messages without their spans.

    Args:
        expr: CEL expression text.
        profile: The profile to check under. ``None`` means the cascade's.

    Returns:
        One message per refused call. Empty when the expression stays inside the profile.
    """
    return [diagnostic.message for diagnostic in scan_profile(expr, profile)]
