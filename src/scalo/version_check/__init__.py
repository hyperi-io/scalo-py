# Project:   scalo
# File:      version_check/__init__.py
# Purpose:   Non-blocking startup version check (opt-in)
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
scalo Version Check - Non-blocking, OPT-IN startup version check.

When enabled, calls a configured version API on startup to check whether a
newer version is available. The check runs in a self-terminating daemon
thread that logs the result and exits. It never blocks, never raises, and
never affects application startup.

The check is OPT-IN and ships no default endpoint -- the consuming app
enables it and supplies its own URL through the config cascade:

    version_check:
      enabled: true
      api_url: "https://releases.example.com/api/v1/check"

Quick Start:
    >>> from scalo.version_check import check_on_startup
    >>>
    >>> # Fire-and-forget -- spawns a daemon thread, returns immediately.
    >>> # No-op unless version_check.enabled and version_check.api_url are set.
    >>> check_on_startup(product="my-service", version="1.2.0")

Dependencies:
    - httpx (optional, from scalo[http])
    - Falls back gracefully if httpx is not installed
"""

from .checker import VersionCheckConfig, VersionCheckResponse, check_on_startup

__all__ = [
    "VersionCheckConfig",
    "VersionCheckResponse",
    "check_on_startup",
]
