# Project:   hs-pylib
# File:      cache/cache.py
# Purpose:   Cashews wrapper with disk backend and per-source TTLs
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""Cashews wrapper with disk-backed cache and per-source TTL configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, TypeVar

from cashews import cache as _cashews_cache

from hs_pylib.logger import logger

if TYPE_CHECKING:
    from hs_pylib.metrics.manager import MetricsManager

# Re-export the global cache instance
cache = _cashews_cache

# Type variable for decorated functions
T = TypeVar("T")

# Source TTL configuration storage
_source_ttls: dict[str, str] = {"_default": "1h"}
_configured: bool = False
_metrics: MetricsManager | None = None
_hits_counter: Any = None
_misses_counter: Any = None


def configure_cache(
    directory: str = ".cache",
    default_ttl: str = "1h",
    source_ttls: dict[str, str] | None = None,
    size_limit: int | None = None,
    metrics: MetricsManager | None = None,
) -> None:
    """Configure disk-backed cache with per-source TTLs and optional metrics.

    Args:
        directory: Cache directory for SQLite storage
        default_ttl: Default TTL for all sources (e.g., "1h", "30m", "24h")
        source_ttls: Override TTLs per source type
        size_limit: Optional size limit in bytes (None for unlimited)
        metrics: Optional MetricsManager for hit/miss tracking

    Usage:
        >>> from hs_pylib.metrics import create_metrics
        >>> metrics = create_metrics("myapp")
        >>>
        >>> configure_cache(
        ...     directory="/tmp/app-cache",
        ...     default_ttl="1h",
        ...     source_ttls={
        ...         "http": "24h",      # Web fetches cached 24 hours
        ...         "tavily": "1h",     # Search results cached 1 hour
        ...         "db": "30m",        # DB queries cached 30 minutes
        ...         "file": "12h",      # Remote files cached 12 hours
        ...     },
        ...     metrics=metrics,  # Enable hit/miss metrics
        ... )

    Metrics (when enabled):
        - cache_hits_total: Counter with labels [source]
        - cache_misses_total: Counter with labels [source]

    Note:
        Call this once at application startup, before using cache.
    """
    global _source_ttls, _configured, _metrics, _hits_counter, _misses_counter

    # Build disk URL with optional size limit
    disk_url = f"disk://?directory={directory}&timeout=1"
    if size_limit is not None:
        disk_url += f"&size_limit={size_limit}"

    cache.setup(disk_url)

    # Store TTL configuration
    _source_ttls = {"_default": default_ttl}
    if source_ttls:
        _source_ttls.update(source_ttls)

    # Setup metrics if provided
    _metrics = metrics
    if metrics is not None:
        _hits_counter = metrics.counter(
            "cache_hits_total",
            "Total cache hits",
            labels=["source"],
        )
        _misses_counter = metrics.counter(
            "cache_misses_total",
            "Total cache misses",
            labels=["source"],
        )
        logger.debug("Cache metrics enabled")

    _configured = True

    logger.info(
        "Cache configured",
        directory=directory,
        default_ttl=default_ttl,
        sources=list(source_ttls.keys()) if source_ttls else [],
        metrics_enabled=metrics is not None,
    )


def get_ttl(source: str) -> str:
    """Get TTL for a source type.

    Args:
        source: Source type (e.g., "http", "tavily", "db")

    Returns:
        TTL string (e.g., "1h", "24h")
    """
    return _source_ttls.get(source, _source_ttls["_default"])


def cached(
    source: str,
    key: str | None = None,
    ttl: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Cache decorator with source-based TTL.

    Args:
        source: Source type for TTL lookup (e.g., "http", "tavily", "db")
        key: Optional key template with placeholders (e.g., "{url}", "{query}")
        ttl: Optional TTL override (uses source TTL if not specified)

    Returns:
        Decorated function

    Usage:
        >>> @cached("http", key="{url}")
        ... async def fetch_url(url: str) -> dict:
        ...     async with httpx.AsyncClient() as client:
        ...         return (await client.get(url)).json()

        >>> @cached("tavily", key="{query}")
        ... async def search(query: str) -> list:
        ...     return await tavily_client.search(query)

        >>> @cached("db", key="{table}:{query_hash}")
        ... async def query_db(table: str, query_hash: str) -> list:
        ...     return await db.execute(query)

    Key Templates:
        Keys support placeholders that are replaced with function arguments:
        - "{url}" -> replaced with the `url` argument value
        - "{query}" -> replaced with the `query` argument value

        The source is automatically prefixed: "http:{url}" -> "http:https://example.com"
    """
    # Determine TTL
    effective_ttl = ttl or get_ttl(source)

    # Build full key with source prefix
    full_key = f"{source}:{key}" if key else None

    # Return cashews decorator
    return cache(ttl=effective_ttl, key=full_key)


async def invalidate_source(source: str) -> int:
    """Invalidate all cache entries for a source type.

    Args:
        source: Source type to invalidate (e.g., "http", "tavily")

    Returns:
        Number of entries deleted

    Usage:
        >>> await invalidate_source("http")  # Clear all HTTP cache
        >>> await invalidate_source("tavily")  # Clear all search cache
    """
    pattern = f"{source}:*"
    return await cache.delete_match(pattern)


async def get_cached(source: str, identifier: str) -> Any | None:
    """Get cached value by source and identifier.

    Args:
        source: Source type (e.g., "http", "tavily")
        identifier: Cache identifier (e.g., URL, query)

    Returns:
        Cached value or None if not found

    Usage:
        >>> data = await get_cached("http", "https://example.com/api")

    Metrics:
        Records cache_hits_total or cache_misses_total if metrics enabled.
    """
    key = f"{source}:{identifier}"
    value = await cache.get(key)

    # Record metrics if enabled
    if _hits_counter is not None and _misses_counter is not None:
        if value is not None:
            _hits_counter.labels(source=source).inc()
        else:
            _misses_counter.labels(source=source).inc()

    return value


async def set_cached(
    source: str,
    identifier: str,
    value: Any,
    ttl: str | None = None,
) -> None:
    """Set cached value by source and identifier.

    Args:
        source: Source type (e.g., "http", "tavily")
        identifier: Cache identifier (e.g., URL, query)
        value: Value to cache
        ttl: Optional TTL override (uses source TTL if not specified)

    Usage:
        >>> await set_cached("http", "https://example.com/api", response_data)
        >>> await set_cached("db", "users:count", 42, ttl="5m")
    """
    key = f"{source}:{identifier}"
    effective_ttl = ttl or get_ttl(source)
    await cache.set(key, value, expire=effective_ttl)
