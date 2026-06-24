# Project:   scalo
# File:      _env_compat.py
# Purpose:   Configurable-prefix environment variables (bare by default)
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""Environment-variable layer for scalo control knobs and config keys.

scalo does NOT hard-code any brand into its environment variables. There is a
single env-var prefix that is **bare ("") by default**; a consuming
application supplies its own (e.g. ``DFE``) and then *everything* -- scalo's
own control knobs and the app's config-cascade keys alike -- is read as
``<PREFIX>_<KEY>``. With no prefix, names are bare (``DEBUG``,
``DATABASE_HOST``).

Prefix resolution (highest wins):

1. Explicit value via :func:`set_env_prefix` (e.g. from ``ServiceApp``).
2. Bare ``ENV_PREFIX`` environment variable.
3. ``""`` -- bare, unprefixed names.

There is no legacy/deprecated alias handling: consumers migrating onto scalo
set their prefix (or use bare names) directly.
"""

from __future__ import annotations

import os

# Programmatic prefix override (None = resolve from env / bare).
_prefix_override: str | None = None


def set_env_prefix(prefix: str) -> None:
    """Set the env-var prefix the app uses (e.g. ``"DFE"``). ``""`` = bare."""
    global _prefix_override
    _prefix_override = prefix.rstrip("_")


def env_prefix() -> str:
    """Resolve the active env-var prefix (without trailing underscore).

    Returns ``""`` (bare) by default.
    """
    if _prefix_override is not None:
        return _prefix_override
    bare = os.environ.get("ENV_PREFIX")
    if bare is not None:
        return bare.rstrip("_")
    return ""


def _standard_name(suffix: str) -> str:
    prefix = env_prefix()
    return f"{prefix}_{suffix}" if prefix else suffix


def control_var(suffix: str, *, default: str | None = None) -> str | None:
    """Read a scalo control/config variable.

    Resolves ``<PREFIX>_<suffix>`` (bare ``<suffix>`` when no prefix is set),
    else ``default``.
    """
    return os.environ.get(_standard_name(suffix), default)


def control_flag(suffix: str, *, default: bool = False) -> bool:
    """Read a boolean control variable via :func:`control_var`.

    Truthy values are ``1``, ``true``, ``yes`` (case-insensitive).
    """
    raw = control_var(suffix)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


def set_control_var(suffix: str, value: str) -> None:
    """Set the standard (prefix-aware) environment variable for ``suffix``."""
    os.environ[_standard_name(suffix)] = value
