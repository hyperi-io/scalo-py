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
