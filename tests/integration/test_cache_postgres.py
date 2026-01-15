# Project:   hs-pylib
# File:      tests/integration/test_cache_postgres.py
# Purpose:   Integration tests for PostgreSQL cache backend with real database
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Integration tests for hs_pylib.cache.postgres module.

These tests require a running PostgreSQL database. The test framework automatically:

1. Tries remote PostgreSQL from DFE_POSTGRES_* env vars if reachable
2. Falls back to local Docker PostgreSQL (localhost:5432) if available
3. Auto-starts Docker PostgreSQL via docker-compose.postgres.yml if needed

Configure remote PostgreSQL via .env:

    DFE_POSTGRES_HOST=your-host.com
    DFE_POSTGRES_PORT=5432
    DFE_POSTGRES_USER=postgres
    DFE_POSTGRES_PASSWORD=yourpassword
    DFE_POSTGRES_DATABASE=hs_pylib_test

Or start local PostgreSQL manually:

    docker compose -f docker-compose.postgres.yml up -d

Run with: pytest tests/integration/test_cache_postgres.py -v -m integration
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
import pytest_asyncio

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration

# Note: postgres_dsn fixture is provided by conftest.py (session-scoped)
# It automatically tries remote PostgreSQL, then falls back to Docker


class TestPostgresCacheLifecycle:
    """Integration tests for PostgresCache lifecycle management."""

    @pytest.mark.asyncio
    async def test_init_creates_table(self, postgres_dsn):
        """Should create cache table on init."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_test_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
        )

        try:
            await cache.init()

            assert cache._initialized is True
            assert cache._pool is not None

            print(f"\n  Created table: {unique_table}")
            print("  Cache initialized successfully")
        finally:
            # Cleanup: drop the test table
            if cache._pool is not None:
                async with cache._pool.connection() as conn:
                    await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
                    await conn.commit()
            await cache.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, postgres_dsn):
        """Should work as async context manager."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_ctx_{uuid.uuid4().hex[:8]}"

        async with PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
        ) as cache:
            assert cache._initialized is True
            # Set and get to verify it works
            await cache.set("ctx_test_key", {"test": "value"})
            value = await cache.get("ctx_test_key")
            assert value == {"test": "value"}
            print("\n  Context manager works correctly")

            # Cleanup
            async with cache._pool.connection() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
                await conn.commit()

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, postgres_dsn):
        """Should properly close pool and release resources."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_close_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
        )
        await cache.init()

        # Cleanup before close
        async with cache._pool.connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
            await conn.commit()

        await cache.close()

        assert cache._initialized is False
        assert cache._pool is None
        print("\n  Resources released correctly")


class TestPostgresCacheCRUD:
    """Integration tests for basic CRUD operations."""

    @pytest_asyncio.fixture
    async def cache(self, postgres_dsn):
        """Provide an initialized cache instance with unique table."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_crud_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
        )
        await cache.init()

        yield cache

        # Cleanup
        async with cache._pool.connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
            await conn.commit()
        await cache.close()

    @pytest.mark.asyncio
    async def test_set_and_get_string(self, cache):
        """Should store and retrieve string values."""
        await cache.set("string_key", "hello world")
        value = await cache.get("string_key")

        assert value == "hello world"
        print("\n  String value stored and retrieved correctly")

    @pytest.mark.asyncio
    async def test_set_and_get_dict(self, cache):
        """Should store and retrieve dict values."""
        test_data = {
            "name": "test",
            "count": 42,
            "nested": {"a": 1, "b": [1, 2, 3]},
            "active": True,
        }

        await cache.set("dict_key", test_data)
        value = await cache.get("dict_key")

        assert value == test_data
        print("\n  Dict value stored and retrieved correctly")

    @pytest.mark.asyncio
    async def test_set_and_get_list(self, cache):
        """Should store and retrieve list values."""
        test_list = [1, 2, "three", {"four": 4}, [5, 6]]

        await cache.set("list_key", test_list)
        value = await cache.get("list_key")

        assert value == test_list
        print("\n  List value stored and retrieved correctly")

    @pytest.mark.asyncio
    async def test_set_and_get_bytes(self, cache):
        """Should store and retrieve bytes values."""
        test_bytes = b"binary data \x00\x01\x02"

        await cache.set("bytes_key", test_bytes)
        value = await cache.get("bytes_key")

        assert value == test_bytes
        print("\n  Bytes value stored and retrieved correctly")

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, cache):
        """Should return None for nonexistent key."""
        value = await cache.get("nonexistent_key_12345")

        assert value is None
        print("\n  Nonexistent key returns None correctly")

    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self, cache):
        """Should overwrite existing value on set."""
        await cache.set("overwrite_key", "original")
        await cache.set("overwrite_key", "updated")

        value = await cache.get("overwrite_key")
        assert value == "updated"
        print("\n  Value overwrite works correctly")

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache):
        """Should delete existing key and return True."""
        await cache.set("delete_key", "to be deleted")

        result = await cache.delete("delete_key")
        assert result is True

        value = await cache.get("delete_key")
        assert value is None
        print("\n  Key deleted successfully")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, cache):
        """Should return False when deleting nonexistent key."""
        result = await cache.delete("nonexistent_delete_key")

        assert result is False
        print("\n  Delete nonexistent key returns False correctly")

    @pytest.mark.asyncio
    async def test_exists_for_valid_key(self, cache):
        """Should return True for existing non-expired key."""
        await cache.set("exists_key", "exists")

        result = await cache.exists("exists_key")
        assert result is True
        print("\n  Exists returns True for valid key")

    @pytest.mark.asyncio
    async def test_exists_for_nonexistent_key(self, cache):
        """Should return False for nonexistent key."""
        result = await cache.exists("nonexistent_exists_key")

        assert result is False
        print("\n  Exists returns False for nonexistent key")


class TestPostgresCacheExpiration:
    """Integration tests for cache expiration behavior."""

    @pytest_asyncio.fixture
    async def cache(self, postgres_dsn):
        """Provide an initialized cache instance with unique table."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_exp_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
            default_ttl_seconds=3600,
        )
        await cache.init()

        yield cache

        # Cleanup
        async with cache._pool.connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
            await conn.commit()
        await cache.close()

    @pytest.mark.asyncio
    async def test_custom_ttl(self, cache):
        """Should use custom TTL when specified."""
        await cache.set("custom_ttl_key", "value", ttl_seconds=60)

        # Verify the entry exists
        exists = await cache.exists("custom_ttl_key")
        assert exists is True

        # Verify expiration is set correctly (approximately)
        async with cache._pool.connection() as conn:
            result = await conn.execute(
                f"SELECT expires_at FROM {cache._table_name} WHERE cache_key = %s",
                ("custom_ttl_key",),
            )
            row = await result.fetchone()

        assert row is not None
        expires_at = row[0]
        expected_min = datetime.now(UTC) + timedelta(seconds=55)
        expected_max = datetime.now(UTC) + timedelta(seconds=65)
        assert expected_min <= expires_at <= expected_max
        print("\n  Custom TTL applied correctly")

    @pytest.mark.asyncio
    async def test_lazy_expiration_on_get(self, cache):
        """Should return None for expired entries on get."""
        # Insert directly with expired timestamp
        async with cache._pool.connection() as conn:
            expired_time = datetime.now(UTC) - timedelta(hours=1)
            await conn.execute(
                f"""
                INSERT INTO {cache._table_name}
                    (cache_key, namespace, value, expires_at, size_bytes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                ("expired_key", "default", b"\x81\xa4test\xa5value", expired_time, 10),
            )
            await conn.commit()

        # Get should return None for expired entry
        value = await cache.get("expired_key")
        assert value is None
        print("\n  Lazy expiration works on get")

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_expired(self, cache):
        """Should return False for expired entries on exists check."""
        # Insert directly with expired timestamp
        async with cache._pool.connection() as conn:
            expired_time = datetime.now(UTC) - timedelta(hours=1)
            await conn.execute(
                f"""
                INSERT INTO {cache._table_name}
                    (cache_key, namespace, value, expires_at, size_bytes)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET expires_at = EXCLUDED.expires_at
                """,
                ("expired_exists_key", "default", b"\x81\xa4test\xa5value", expired_time, 10),
            )
            await conn.commit()

        # Exists should return False for expired entry
        exists = await cache.exists("expired_exists_key")
        assert exists is False
        print("\n  Exists returns False for expired entries")

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache):
        """Should delete expired entries on cleanup."""
        # Insert multiple entries with different expiration times
        async with cache._pool.connection() as conn:
            now = datetime.now(UTC)
            expired_time = now - timedelta(hours=1)
            valid_time = now + timedelta(hours=1)

            # Insert expired entries
            for i in range(5):
                await conn.execute(
                    f"""
                    INSERT INTO {cache._table_name}
                        (cache_key, namespace, value, expires_at, size_bytes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (f"cleanup_expired_{i}", "default", b"\x81\xa4test\xa5value", expired_time, 10),
                )

            # Insert valid entries
            for i in range(3):
                await conn.execute(
                    f"""
                    INSERT INTO {cache._table_name}
                        (cache_key, namespace, value, expires_at, size_bytes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (f"cleanup_valid_{i}", "default", b"\x81\xa4test\xa5value", valid_time, 10),
                )

            await conn.commit()

        # Run cleanup
        deleted = await cache.cleanup_expired()

        assert deleted == 5
        print(f"\n  Cleanup deleted {deleted} expired entries")

        # Verify valid entries still exist
        for i in range(3):
            exists = await cache.exists(f"cleanup_valid_{i}")
            assert exists is True


class TestPostgresCacheBulkInvalidation:
    """Integration tests for bulk invalidation operations."""

    @pytest_asyncio.fixture
    async def cache(self, postgres_dsn):
        """Provide an initialized cache instance with unique table."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_bulk_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
        )
        await cache.init()

        yield cache

        # Cleanup
        async with cache._pool.connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
            await conn.commit()
        await cache.close()

    @pytest.mark.asyncio
    async def test_invalidate_by_prefix(self, cache):
        """Should delete all entries with matching prefix."""
        # Insert entries with different prefixes
        await cache.set("analytics:query1", {"result": 1})
        await cache.set("analytics:query2", {"result": 2})
        await cache.set("analytics:query3", {"result": 3})
        await cache.set("metrics:cpu", {"value": 50})
        await cache.set("metrics:memory", {"value": 80})

        # Invalidate analytics prefix
        deleted = await cache.invalidate_by_prefix("analytics:")

        assert deleted == 3

        # Verify analytics entries are gone
        assert await cache.get("analytics:query1") is None
        assert await cache.get("analytics:query2") is None
        assert await cache.get("analytics:query3") is None

        # Verify metrics entries still exist
        assert await cache.get("metrics:cpu") is not None
        assert await cache.get("metrics:memory") is not None

        print(f"\n  Invalidated {deleted} entries by prefix")

    @pytest.mark.asyncio
    async def test_invalidate_by_namespace(self, cache):
        """Should delete all entries in a namespace."""
        # Insert entries in different namespaces
        await cache.set("key1", "value1", namespace="analytics")
        await cache.set("key2", "value2", namespace="analytics")
        await cache.set("key3", "value3", namespace="metrics")
        await cache.set("key4", "value4", namespace="default")

        # Invalidate analytics namespace
        deleted = await cache.invalidate_by_namespace("analytics")

        assert deleted == 2

        # Verify analytics entries are gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

        # Verify other namespace entries still exist
        assert await cache.get("key3") is not None
        assert await cache.get("key4") is not None

        print(f"\n  Invalidated {deleted} entries by namespace")

    @pytest.mark.asyncio
    async def test_invalidate_by_namespace_with_org(self, cache):
        """Should delete entries in namespace scoped by org."""
        # Insert entries in same namespace but different orgs
        await cache.set("key1", "value1", namespace="analytics", org_id="acme")
        await cache.set("key2", "value2", namespace="analytics", org_id="acme")
        await cache.set("key3", "value3", namespace="analytics", org_id="globex")
        await cache.set("key4", "value4", namespace="analytics", org_id="globex")

        # Invalidate analytics namespace for acme only
        deleted = await cache.invalidate_by_namespace("analytics", org_id="acme")

        assert deleted == 2

        # Verify acme entries are gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

        # Verify globex entries still exist
        assert await cache.get("key3") is not None
        assert await cache.get("key4") is not None

        print(f"\n  Invalidated {deleted} entries by namespace+org")

    @pytest.mark.asyncio
    async def test_invalidate_by_org(self, cache):
        """Should delete all entries for an organisation."""
        # Insert entries for different orgs in different namespaces
        await cache.set("key1", "value1", namespace="analytics", org_id="acme")
        await cache.set("key2", "value2", namespace="metrics", org_id="acme")
        await cache.set("key3", "value3", namespace="analytics", org_id="globex")
        await cache.set("key4", "value4", namespace="default")  # No org

        # Invalidate all entries for acme
        deleted = await cache.invalidate_by_org("acme")

        assert deleted == 2

        # Verify acme entries are gone
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

        # Verify other entries still exist
        assert await cache.get("key3") is not None
        assert await cache.get("key4") is not None

        print(f"\n  Invalidated {deleted} entries by org")


class TestPostgresCacheStats:
    """Integration tests for cache statistics."""

    @pytest_asyncio.fixture
    async def cache(self, postgres_dsn):
        """Provide an initialized cache instance with unique table."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_stats_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
        )
        await cache.init()

        yield cache

        # Cleanup
        async with cache._pool.connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
            await conn.commit()
        await cache.close()

    @pytest.mark.asyncio
    async def test_stats_empty_cache(self, cache):
        """Should return zero counts for empty cache."""
        stats = await cache.stats()

        assert stats["entry_count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["expired_count"] == 0
        assert stats["namespaces"] == {}

        print("\n  Empty cache stats correct")

    @pytest.mark.asyncio
    async def test_stats_with_entries(self, cache):
        """Should return correct counts for populated cache."""
        # Add entries in different namespaces
        await cache.set("key1", {"data": "x" * 100}, namespace="analytics")
        await cache.set("key2", {"data": "y" * 200}, namespace="analytics")
        await cache.set("key3", {"data": "z" * 50}, namespace="metrics")

        stats = await cache.stats()

        assert stats["entry_count"] == 3
        assert stats["total_size_bytes"] > 0
        assert stats["expired_count"] == 0

        assert "analytics" in stats["namespaces"]
        assert "metrics" in stats["namespaces"]
        assert stats["namespaces"]["analytics"]["count"] == 2
        assert stats["namespaces"]["metrics"]["count"] == 1

        print(f"\n  Stats: {stats['entry_count']} entries, {stats['total_size_bytes']} bytes")
        print(f"  Namespaces: {list(stats['namespaces'].keys())}")

    @pytest.mark.asyncio
    async def test_stats_excludes_expired(self, cache):
        """Should exclude expired entries from active count."""
        # Add valid entries
        await cache.set("valid1", "data")
        await cache.set("valid2", "data")

        # Insert expired entry directly
        async with cache._pool.connection() as conn:
            expired_time = datetime.now(UTC) - timedelta(hours=1)
            await conn.execute(
                f"""
                INSERT INTO {cache._table_name}
                    (cache_key, namespace, value, expires_at, size_bytes)
                VALUES (%s, %s, %s, %s, %s)
                """,
                ("expired", "default", b"\x81\xa4test\xa5value", expired_time, 10),
            )
            await conn.commit()

        stats = await cache.stats()

        assert stats["entry_count"] == 2  # Only valid entries
        assert stats["expired_count"] == 1

        print(f"\n  Active: {stats['entry_count']}, Expired: {stats['expired_count']}")


class TestPostgresCacheConcurrency:
    """Integration tests for concurrent access."""

    @pytest_asyncio.fixture
    async def cache(self, postgres_dsn):
        """Provide an initialized cache instance with unique table."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_conc_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
            pool_min_size=5,
            pool_max_size=20,
        )
        await cache.init()

        yield cache

        # Cleanup
        async with cache._pool.connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
            await conn.commit()
        await cache.close()

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, cache):
        """Should handle concurrent writes without errors."""
        num_concurrent = 50

        async def write_entry(i: int):
            await cache.set(f"concurrent_key_{i}", {"index": i, "data": "x" * 100})

        # Run all writes concurrently
        await asyncio.gather(*[write_entry(i) for i in range(num_concurrent)])

        # Verify all entries were written
        count = 0
        for i in range(num_concurrent):
            value = await cache.get(f"concurrent_key_{i}")
            if value is not None:
                count += 1

        assert count == num_concurrent
        print(f"\n  {count} concurrent writes completed successfully")

    @pytest.mark.asyncio
    async def test_concurrent_reads(self, cache):
        """Should handle concurrent reads without errors."""
        # Setup: write some entries
        for i in range(10):
            await cache.set(f"read_key_{i}", {"index": i})

        num_concurrent = 100

        async def read_entry(i: int):
            key = f"read_key_{i % 10}"
            return await cache.get(key)

        # Run all reads concurrently
        results = await asyncio.gather(*[read_entry(i) for i in range(num_concurrent)])

        # All reads should succeed
        assert all(r is not None for r in results)
        print(f"\n  {num_concurrent} concurrent reads completed successfully")

    @pytest.mark.asyncio
    async def test_concurrent_upserts(self, cache):
        """Should handle concurrent upserts to same key correctly."""
        num_concurrent = 20
        key = "upsert_contention_key"

        async def upsert_entry(i: int):
            await cache.set(key, {"final_index": i})

        # Run all upserts concurrently
        await asyncio.gather(*[upsert_entry(i) for i in range(num_concurrent)])

        # Key should exist with one of the values
        value = await cache.get(key)
        assert value is not None
        assert "final_index" in value
        assert 0 <= value["final_index"] < num_concurrent

        print(f"\n  Concurrent upserts completed, final value: {value}")


class TestGenerateCacheKeyIntegration:
    """Integration tests for cache key generation helper."""

    @pytest_asyncio.fixture
    async def cache(self, postgres_dsn):
        """Provide an initialized cache instance with unique table."""
        from hs_pylib.cache.postgres import PostgresCache

        unique_table = f"cache_keygen_{uuid.uuid4().hex[:8]}"

        cache = PostgresCache(
            dsn=postgres_dsn,
            table_name=unique_table,
        )
        await cache.init()

        yield cache

        # Cleanup
        async with cache._pool.connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {unique_table}")
            await conn.commit()
        await cache.close()

    @pytest.mark.asyncio
    async def test_generate_cache_key_with_cache(self, cache):
        """Should generate and use cache key correctly."""
        from hs_pylib.cache.postgres import generate_cache_key

        # Generate key with params
        key = generate_cache_key(
            namespace="clickhouse",
            identifier="events_by_day",
            org_id="acme-corp",
            params={"start": "2025-01-01", "end": "2025-01-15"},
        )

        # Use key with cache
        test_data = {"rows": [{"date": "2025-01-01", "count": 100}]}
        await cache.set(key, test_data, namespace="clickhouse", org_id="acme-corp")

        # Retrieve with same key
        retrieved = await cache.get(key)
        assert retrieved == test_data

        print(f"\n  Generated key: {key}")
        print("  Data stored and retrieved successfully")

    @pytest.mark.asyncio
    async def test_different_params_produce_different_keys(self, cache):
        """Should generate different keys for different params."""
        from hs_pylib.cache.postgres import generate_cache_key

        key1 = generate_cache_key("ns", "id", params={"page": 1})
        key2 = generate_cache_key("ns", "id", params={"page": 2})

        assert key1 != key2

        # Both keys should work independently
        await cache.set(key1, {"page": 1})
        await cache.set(key2, {"page": 2})

        val1 = await cache.get(key1)
        val2 = await cache.get(key2)

        assert val1 == {"page": 1}
        assert val2 == {"page": 2}

        print(f"\n  Key 1: {key1}")
        print(f"  Key 2: {key2}")
        print("  Different params produce different keys correctly")
