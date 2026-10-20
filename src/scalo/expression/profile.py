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

import functools
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


@functools.cache
def _read_cascade_profile() -> ProfileConfig:
    from scalo.config import settings

    return ProfileConfig.from_mapping(settings.get("expression", None))


def cascade_profile() -> ProfileConfig:
    """Return the profile the config cascade sets under ``expression``.

    The first clean read is kept for the life of the process. A cascade that cannot be
    read gives the default profile and is tried again next call.

    Returns:
        The cascade's profile, or :class:`ProfileConfig` with every restriction on.
    """
    try:
        return _read_cascade_profile()
    except Exception:
        # An unreadable cascade keeps every restriction on rather than failing the caller.
        return ProfileConfig()


def _skip_string_literal(data: bytes, start: int) -> int:
    """Return the index after the literal that opens at ``start``, or the end of input."""
    quote = data[start]
    i = start + 1
    while i < len(data):
        if data[i] == 0x5C:  # backslash escapes the next byte
            i += 2
            continue
        if data[i] == quote:
            return i + 1
        i += 1
    return len(data)


def _is_ident_start(byte: int) -> bool:
    return (0x41 <= byte <= 0x5A) or (0x61 <= byte <= 0x7A) or byte == 0x5F


def _is_ident_char(byte: int) -> bool:
    return _is_ident_start(byte) or (0x30 <= byte <= 0x39)


def scan_profile(expr: str, profile: ProfileConfig | None = None) -> list[Diagnostic]:
    """Find each call the profile refuses, with the byte span of its function name.

    The scan skips single- and double-quoted string literals, so a name inside a quoted
    value is never reported.

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
        if byte in (0x22, 0x27):
            i = _skip_string_literal(data, i)
            continue
        if not _is_ident_start(byte):
            i += 1
            continue
        start = i
        while i < len(data) and _is_ident_char(data[i]):
            i += 1
        name = data[start:i].decode("ascii")
        peek = i
        while peek < len(data) and data[peek] == 0x20:
            peek += 1
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
