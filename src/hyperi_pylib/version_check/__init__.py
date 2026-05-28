# Project:   hyperi-pylib
# File:      version_check/__init__.py
# Purpose:   Startup version check against HyperI version API
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
hyperi-pylib Version Check - Non-blocking startup version check.

Calls the HyperI version API on startup to check if a newer version is
available. The check runs in a self-terminating daemon thread that logs
the result and exits. It never blocks, never raises, and never affects
application startup.

Quick Start:
    >>> from hyperi_pylib.version_check import check_on_startup
    >>>
    >>> # Fire-and-forget -- spawns a daemon thread, returns immediately
    >>> check_on_startup(product="dfe-receiver", version="1.2.0")

Configuration:
    Environment variables override defaults:
    - VERSION_CHECK_DISABLED=true  -- disable the check entirely
    - VERSION_CHECK_URL=https://...  -- override the API endpoint

Dependencies:
    - httpx (optional, from hyperi-pylib[http])
    - Falls back gracefully if httpx is not installed
"""

from .checker import VersionCheckConfig, VersionCheckResponse, check_on_startup

__all__ = [
    "VersionCheckConfig",
    "VersionCheckResponse",
    "check_on_startup",
]
