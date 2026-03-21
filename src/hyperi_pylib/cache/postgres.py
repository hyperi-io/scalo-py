# Project:   hyperi-pylib
# File:      cache/postgres.py
# Purpose:   PostgreSQL-backed cache for multi-pod deployments
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""PostgreSQL-backed cache for shared multi-instance deployments.

This module provides a PostgreSQL-backed cache that can be shared across
multiple pod instances, unlike the disk-based cache which is local to each pod.

Usage:
    >>> from hyperi_pylib.cache.postgres import PostgresCache, generate_cache_key
    >>>
    >>> # Create cache with DSN
    >>> cache = PostgresCache(dsn="postgresql://user:pass@host/db")
    >>> await cache.init()  # Creates table if not exists
    >>>
    >>> # Basic operations
    >>> await cache.set("key", {"data": "value"}, ttl_seconds=300)
    >>> value = await cache.get("key")
    >>> await cache.delete("key")
    >>>
    >>> # Bulk operations
    >>> await cache.invalidate_by_prefix("analytics:")
    >>> await cache.invalidate_by_org("acme-corp")
    >>> count = await cache.cleanup_expired()
    >>>
    >>> # Cleanup
    >>> await cache.close()

Schema:
    CREATE TABLE IF NOT EXISTS cache_entries (
        cache_key TEXT PRIMARY KEY,
        namespace TEXT NOT NULL DEFAULT 'default',
        org_id TEXT,
        value BYTEA NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,
        hit_count INTEGER DEFAULT 0,
        size_bytes INTEGER
    );
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import msgpack
from psycopg_pool import AsyncConnectionPool

from hyperi_pylib.logger import logger

if TYPE_CHECKING:
    from hyperi_pylib.metrics.manager import MetricsManager


class PostgresCacheError(Exception):
    """Base exception for PostgreSQL cache errors."""



class PostgresCache:
    """PostgreSQL-backed cache for multi-instance deployments.

    Provides shared cache storage accessible by all pod instances,
    using PostgreSQL BYTEA with msgpack serialization.

    Features:
        - Multi-instance shared cache (vs local disk cache)
        - BYTEA + msgpack storage for any serializable data
        - Namespace and org_id scoping for isolation
        - Automatic expiration with lazy + scheduled cleanup
        - Hit count tracking for cache analytics

    Args:
        dsn: PostgreSQL connection string
        table_name: Cache table name (default: cache_entries)
        default_ttl_seconds: Default TTL in seconds (default: 3600)
        pool_min_size: Minimum pool connections (default: 2)
        pool_max_size: Maximum pool connections (default: 10)
        create_table: Auto-create table on init (default: True)
        metrics: Optional MetricsManager for hit/miss tracking
    """

    def __init__(
        self,
        dsn: str,
        table_name: str = "cache_entries",
        default_ttl_seconds: int = 3600,
        pool_min_size: int = 2,
        pool_max_size: int = 10,
        create_table: bool = True,
        metrics: MetricsManager | None = None,
    ) -> None:
        self._dsn = dsn
        self._table_name = table_name
        self._default_ttl_seconds = default_ttl_seconds
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size
        self._create_table = create_table
        self._pool: AsyncConnectionPool | None = None
        self._initialized = False

        # Metrics
        self._metrics = metrics
        self._hits_counter: Any = None
        self._misses_counter: Any = None

    async def init(self) -> None:
        """Initialize connection pool and create table if needed.

        Creates the cache_entries table with indexes for efficient
        lookups by expiry, namespace, and org_id.

        This is idempotent and safe to call multiple times.
        """
        if self._initialized:
            return

        # Create connection pool
        self._pool = AsyncConnectionPool(
            conninfo=self._dsn,
            min_size=self._pool_min_size,
            max_size=self._pool_max_size,
            open=False,
        )
        await self._pool.open()

        # Create table if requested
        if self._create_table:
            await self._ensure_table()

        # Setup metrics if provided
        if self._metrics is not None:
            self._hits_counter = self._metrics.counter(
                "postgres_cache_hits_total",
                "Total PostgreSQL cache hits",
                labels=["namespace"],
            )
            self._misses_counter = self._metrics.counter(
                "postgres_cache_misses_total",
                "Total PostgreSQL cache misses",
                labels=["namespace"],
            )
            logger.debug("PostgreSQL cache metrics enabled")

        self._initialized = True
        logger.info(
            "PostgreSQL cache initialized",
            table=self._table_name,
            pool_size=f"{self._pool_min_size}-{self._pool_max_size}",
        )

    async def _ensure_table(self) -> None:
        """Create cache table and indexes if they don't exist."""
        async with self._pool.connection() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    cache_key TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL DEFAULT 'default',
                    org_id TEXT,
                    value BYTEA NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    size_bytes INTEGER
                )
                """  # nosec B608 - table_name is constructor param, not user input
            )

            # Create indexes if they don't exist
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_expires
                ON {self._table_name}(expires_at)
                """  # nosec B608
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_namespace
                ON {self._table_name}(namespace)
                """  # nosec B608
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_org
                ON {self._table_name}(org_id)
                """  # nosec B608
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_ns_org
                ON {self._table_name}(namespace, org_id)
                """  # nosec B608
            )
            await conn.commit()

        logger.debug("PostgreSQL cache table ensured", table=self._table_name)

    async def close(self) -> None:
        """Close connection pool and release resources."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.debug("PostgreSQL cache closed")

    async def __aenter__(self) -> PostgresCache:
        """Async context manager entry."""
        await self.init()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def _check_initialized(self) -> None:
        """Raise if not initialized."""
        if not self._initialized or self._pool is None:
            raise PostgresCacheError("PostgresCache not initialized. Call init() first.")

    async def get(self, key: str) -> Any | None:
        """Get cached value by key.

        Implements lazy expiration - returns None for expired entries
        and schedules async deletion.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            result = await conn.execute(
                f"""
                SELECT value, expires_at, namespace FROM {self._table_name}
                WHERE cache_key = %s
                """,  # nosec B608
                (key,),
            )
            row = await result.fetchone()

            if row is None:
                # Record miss metric
                if self._misses_counter is not None:
                    self._misses_counter.labels(namespace="unknown").inc()
                logger.debug("Cache miss", key=key)
                return None

            value_bytes, expires_at, namespace = row

            # Check expiration (lazy deletion)
            if expires_at < datetime.now(UTC):
                # Fire-and-forget delete
                asyncio.create_task(self._delete_key(key))
                # Record miss metric
                if self._misses_counter is not None:
                    self._misses_counter.labels(namespace=namespace).inc()
                logger.debug("Cache expired", key=key)
                return None

            # Update hit count (fire-and-forget)
            asyncio.create_task(self._increment_hit_count(key))

            # Record hit metric
            if self._hits_counter is not None:
                self._hits_counter.labels(namespace=namespace).inc()

            logger.debug("Cache hit", key=key)
            return msgpack.unpackb(value_bytes, raw=False)

    async def _delete_key(self, key: str) -> None:
        """Delete a single key (internal, fire-and-forget)."""
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    f"DELETE FROM {self._table_name} WHERE cache_key = %s",  # nosec B608
                    (key,),
                )
                await conn.commit()
        except Exception as e:
            logger.warning("Failed to delete expired key", key=key, error=str(e))

    async def _increment_hit_count(self, key: str) -> None:
        """Increment hit count for a key (internal, fire-and-forget)."""
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    f"UPDATE {self._table_name} SET hit_count = hit_count + 1 WHERE cache_key = %s",  # nosec B608
                    (key,),
                )
                await conn.commit()
        except Exception as e:
            logger.warning("Failed to increment hit count", key=key, error=str(e))

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
        namespace: str = "default",
        org_id: str | None = None,
    ) -> None:
        """Set cached value with TTL.

        Uses atomic upsert (ON CONFLICT DO UPDATE) for safe concurrent access.

        Args:
            key: Cache key
            value: Value to cache (must be msgpack-serializable)
            ttl_seconds: Time-to-live in seconds (uses default if None)
            namespace: Cache namespace (e.g., "analytics", "metrics")
            org_id: Optional organisation ID for scoped invalidation
        """
        self._check_initialized()

        effective_ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        expires_at = datetime.now(UTC) + timedelta(seconds=effective_ttl)
        value_bytes = msgpack.packb(value, use_bin_type=True)
        size_bytes = len(value_bytes)

        async with self._pool.connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self._table_name}
                    (cache_key, namespace, org_id, value, expires_at, size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET
                    value = EXCLUDED.value,
                    namespace = EXCLUDED.namespace,
                    org_id = EXCLUDED.org_id,
                    expires_at = EXCLUDED.expires_at,
                    hit_count = 0,
                    size_bytes = EXCLUDED.size_bytes
                """,  # nosec B608
                (key, namespace, org_id, value_bytes, expires_at, size_bytes),
            )
            await conn.commit()

        logger.debug("Cache set", key=key, ttl=effective_ttl, namespace=namespace)

    async def delete(self, key: str) -> bool:
        """Delete cached value by key.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if not found
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._table_name} WHERE cache_key = %s",  # nosec B608
                (key,),
            )
            await conn.commit()
            deleted = result.rowcount > 0

        if deleted:
            logger.debug("Cache deleted", key=key)
        return deleted

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired.

        Args:
            key: Cache key to check

        Returns:
            True if key exists and is not expired
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            result = await conn.execute(
                f"""
                SELECT 1 FROM {self._table_name}
                WHERE cache_key = %s AND expires_at > %s
                """,  # nosec B608
                (key, datetime.now(UTC)),
            )
            row = await result.fetchone()
            return row is not None

    async def invalidate_by_prefix(self, prefix: str) -> int:
        """Invalidate all cache entries with matching key prefix.

        Args:
            prefix: Key prefix to match (e.g., "analytics:")

        Returns:
            Number of entries deleted
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._table_name} WHERE cache_key LIKE %s",  # nosec B608
                (f"{prefix}%",),
            )
            await conn.commit()
            count = result.rowcount

        logger.info("Cache invalidated by prefix", prefix=prefix, count=count)
        return count

    async def invalidate_by_namespace(
        self,
        namespace: str,
        org_id: str | None = None,
    ) -> int:
        """Invalidate all cache entries in a namespace.

        Args:
            namespace: Namespace to invalidate
            org_id: Optional org_id to scope invalidation

        Returns:
            Number of entries deleted
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            if org_id:
                result = await conn.execute(
                    f"DELETE FROM {self._table_name} WHERE namespace = %s AND org_id = %s",  # nosec B608
                    (namespace, org_id),
                )
            else:
                result = await conn.execute(
                    f"DELETE FROM {self._table_name} WHERE namespace = %s",  # nosec B608
                    (namespace,),
                )
            await conn.commit()
            count = result.rowcount

        logger.info(
            "Cache invalidated by namespace",
            namespace=namespace,
            org_id=org_id,
            count=count,
        )
        return count

    async def invalidate_by_org(self, org_id: str) -> int:
        """Invalidate all cache entries for an organisation.

        Useful for cache clearing after data loads or tenant deletion.

        Args:
            org_id: Organisation ID to invalidate

        Returns:
            Number of entries deleted
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._table_name} WHERE org_id = %s",  # nosec B608
                (org_id,),
            )
            await conn.commit()
            count = result.rowcount

        logger.info("Cache invalidated by org", org_id=org_id, count=count)
        return count

    async def cleanup_expired(self) -> int:
        """Delete all expired cache entries.

        Should be run periodically (e.g., every 5 minutes) via scheduler.

        Returns:
            Number of entries deleted
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            result = await conn.execute(
                f"DELETE FROM {self._table_name} WHERE expires_at < %s",  # nosec B608
                (datetime.now(UTC),),
            )
            await conn.commit()
            count = result.rowcount

        if count > 0:
            logger.info("Cache cleanup completed", deleted=count)
        return count

    async def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with entry_count, total_size_bytes, expired_count, namespaces
        """
        self._check_initialized()

        async with self._pool.connection() as conn:
            now = datetime.now(UTC)

            # Entry count and size (non-expired)
            result = await conn.execute(
                f"""
                SELECT
                    COUNT(*) as entry_count,
                    COALESCE(SUM(size_bytes), 0) as total_size_bytes
                FROM {self._table_name}
                WHERE expires_at > %s
                """,  # nosec B608
                (now,),
            )
            row = await result.fetchone()
            entry_count = row[0] if row else 0
            total_size_bytes = row[1] if row else 0

            # Expired count
            result = await conn.execute(
                f"SELECT COUNT(*) FROM {self._table_name} WHERE expires_at <= %s",  # nosec B608
                (now,),
            )
            expired_row = await result.fetchone()
            expired_count = expired_row[0] if expired_row else 0

            # Namespace breakdown
            result = await conn.execute(
                f"""
                SELECT namespace, COUNT(*) as count, COALESCE(SUM(size_bytes), 0) as size
                FROM {self._table_name}
                WHERE expires_at > %s
                GROUP BY namespace
                """,  # nosec B608
                (now,),
            )
            namespaces = {r[0]: {"count": r[1], "size_bytes": r[2]} for r in await result.fetchall()}

        return {
            "entry_count": entry_count,
            "total_size_bytes": total_size_bytes,
            "expired_count": expired_count,
            "namespaces": namespaces,
        }


def generate_cache_key(
    namespace: str,
    identifier: str,
    org_id: str | None = None,
    params: dict | None = None,
) -> str:
    """Generate deterministic cache key from components.

    Args:
        namespace: Cache namespace (e.g., "analytics", "metrics", "clickhouse")
        identifier: Primary identifier (e.g., query_id, "events_by_day")
        org_id: Optional organisation ID
        params: Optional parameters to include in key hash

    Returns:
        Deterministic cache key string

    Example:
        >>> key = generate_cache_key(
        ...     namespace="clickhouse",
        ...     identifier="events_by_day",
        ...     org_id="acme-corp",
        ...     params={"start": "2025-01-01", "end": "2025-01-15"}
        ... )
        >>> # Returns: "clickhouse:acme-corp:events_by_day:a1b2c3d4e5f6g7h8"
    """
    parts = [namespace]
    if org_id:
        parts.append(org_id)
    parts.append(identifier)

    if params:
        # Create deterministic hash of params
        params_str = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
        parts.append(params_hash)

    return ":".join(parts)
