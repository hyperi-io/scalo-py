# Project:   hyperi-pylib
# File:      cache/__init__.py
# Purpose:   Cache module with disk and PostgreSQL backends
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
hyperi-pylib Cache Module - Disk and PostgreSQL Cache Backends.

Provides async-first caching with two backend options:
1. **Disk (default)**: Local SQLite via Cashews - fast, per-pod
2. **PostgreSQL**: Shared across pods - for multi-instance deployments

Disk Cache (single pod):
    >>> from hyperi_pylib.cache import configure_cache, cached, cache
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

PostgreSQL Cache (multi-pod):
    >>> from hyperi_pylib.cache import PostgresCache, generate_cache_key
    >>>
    >>> cache = PostgresCache(dsn="postgresql://user:pass@host/db")
    >>> await cache.init()
    >>>
    >>> key = generate_cache_key("analytics", "events", org_id="acme")
    >>> await cache.set(key, {"data": [...]}, ttl_seconds=300, namespace="analytics")
    >>> value = await cache.get(key)
    >>>
    >>> await cache.close()

Dependencies:
    pip install hyperi-pylib[cache]  # Installs cashews, msgpack, psycopg
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

# PostgreSQL cache imports - optional, requires psycopg
try:
    from .postgres import (
        PostgresCache,
        PostgresCacheError,
        generate_cache_key,
    )

    _postgres_available = True
except ImportError:
    _postgres_available = False

    # Provide stub for type checking
    class PostgresCache:  # type: ignore[no-redef]
        """PostgreSQL cache (requires psycopg)."""

        def __init__(self, *args, **kwargs):
            raise ImportError("PostgresCache requires psycopg. Install with: pip install hyperi-pylib[cache]")

    class PostgresCacheError(Exception):  # type: ignore[no-redef]
        """PostgreSQL cache error (requires psycopg)."""

    def generate_cache_key(*args, **kwargs) -> str:  # type: ignore[no-redef]
        """Generate cache key (requires psycopg)."""
        raise ImportError("generate_cache_key requires psycopg. Install with: pip install hyperi-pylib[cache]")


__all__ = [
    # Disk cache (cashews)
    "cache",
    "configure_cache",
    "cached",
    "get_ttl",
    "get_cached",
    "set_cached",
    "invalidate_source",
    # PostgreSQL cache
    "PostgresCache",
    "PostgresCacheError",
    "generate_cache_key",
]
