# Project:   hs-pylib
# File:      cache/__init__.py
# Purpose:   Disk-backed cache module with per-source TTLs
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
hs-pylib Cache Module - Disk-Backed Caching with Per-Source TTLs.

Provides async-first caching using Cashews with DiskCache backend (SQLite).
Designed for caching HTTP fetches, web searches, DB queries, and remote files.

Quick Start:
    >>> from hs_pylib.cache import configure_cache, cached, cache
    >>>
    >>> # Configure at app startup
    >>> configure_cache(
    ...     directory="/tmp/app-cache",
    ...     default_ttl="1h",
    ...     source_ttls={"http": "24h", "tavily": "1h", "db": "30m"}
    ... )
    >>>
    >>> # Decorate async functions
    >>> @cached("http", key="{url}")
    ... async def fetch_url(url: str) -> dict:
    ...     async with httpx.AsyncClient() as client:
    ...         return (await client.get(url)).json()
    >>>
    >>> # Direct cache access
    >>> await cache.set("http:example.com", data, expire="24h")
    >>> result = await cache.get("http:example.com")

Cache Tuple Structure:
    (source, identifier, value, time)
    - source: Cache category (http, tavily, db, file)
    - identifier: Actual fetch key (URL, query, SQL)
    - value: Cached result (JSON, bytes, objects)
    - time: TTL with per-source overrides

Dependencies:
    pip install hs-pylib[cache]  # Installs cashews[diskcache]
"""

from .cache import (
    cache,
    cached,
    configure_cache,
    get_cached,
    get_ttl,
    invalidate_source,
    set_cached,
)

__all__ = [
    "cache",
    "configure_cache",
    "cached",
    "get_ttl",
    "get_cached",
    "set_cached",
    "invalidate_source",
]
