# Project:   scalo
# File:      expression/profile.py
# Purpose:   expression profile -- allowed subset of CEL
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Expression Profile -- the allowed subset of CEL.

The expression profile restricts CEL to high-performance operations only.
Per-element iteration (map/filter/exists/all) is excluded because
it has unpredictable performance on large lists in a data pipeline.

See: docs/EXPRESSIONS-CEL.md
"""

from __future__ import annotations

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
        "matches",
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

# Functions explicitly banned -- per-element iteration is too expensive.
DISALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {
        "map",
        "filter",
        "exists",
        "exists_one",
        "all",
        "timestamp",
        "duration",
    }
)

# Known function names (union of allowed + disallowed) for error messages.
KNOWN_FUNCTIONS: frozenset[str] = ALLOWED_FUNCTIONS | DISALLOWED_FUNCTIONS
