# Project:   hs-pylib
# File:      tests/unit/test_cache_postgres.py
# Purpose:   Unit tests for PostgreSQL cache backend
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""Unit tests for hs_pylib.cache.postgres module."""

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPostgresCacheImports:
    """Test PostgreSQL cache module imports."""

    def test_import_postgres_cache(self):
        """Test PostgresCache can be imported."""
        from hs_pylib.cache import PostgresCache

        assert PostgresCache is not None

    def test_import_postgres_cache_error(self):
        """Test PostgresCacheError can be imported."""
        from hs_pylib.cache import PostgresCacheError

        assert PostgresCacheError is not None

    def test_import_generate_cache_key(self):
        """Test generate_cache_key can be imported."""
        from hs_pylib.cache import generate_cache_key

        assert generate_cache_key is not None

    def test_direct_import_from_postgres_module(self):
        """Test direct imports from postgres module."""
        from hs_pylib.cache.postgres import (
            PostgresCache,
            PostgresCacheError,
            generate_cache_key,
        )

        assert PostgresCache is not None
        assert PostgresCacheError is not None
        assert generate_cache_key is not None


class TestGenerateCacheKey:
    """Tests for generate_cache_key function."""

    def test_basic_key_generation(self):
        """Test basic key with namespace and identifier."""
        from hs_pylib.cache.postgres import generate_cache_key

        key = generate_cache_key(namespace="analytics", identifier="query1")
        assert key == "analytics:query1"

    def test_key_with_org_id(self):
        """Test key with org_id included."""
        from hs_pylib.cache.postgres import generate_cache_key

        key = generate_cache_key(
            namespace="metrics",
            identifier="events_by_day",
            org_id="acme-corp",
        )
        assert key == "metrics:acme-corp:events_by_day"

    def test_key_with_params(self):
        """Test key with params generates hash suffix."""
        from hs_pylib.cache.postgres import generate_cache_key

        key = generate_cache_key(
            namespace="clickhouse",
            identifier="query",
            params={"start": "2025-01-01", "end": "2025-01-15"},
        )

        # Should have 4 parts: namespace:identifier:hash
        parts = key.split(":")
        assert len(parts) == 3
        assert parts[0] == "clickhouse"
        assert parts[1] == "query"
        assert len(parts[2]) == 16  # SHA256 hex truncated to 16 chars

    def test_key_with_org_and_params(self):
        """Test key with both org_id and params."""
        from hs_pylib.cache.postgres import generate_cache_key

        key = generate_cache_key(
            namespace="analytics",
            identifier="events",
            org_id="hypersec",
            params={"filter": "active"},
        )

        parts = key.split(":")
        assert len(parts) == 4
        assert parts[0] == "analytics"
        assert parts[1] == "hypersec"
        assert parts[2] == "events"
        assert len(parts[3]) == 16

    def test_deterministic_key_generation(self):
        """Test that same inputs always generate same key."""
        from hs_pylib.cache.postgres import generate_cache_key

        params = {"a": 1, "b": "test", "c": [1, 2, 3]}

        key1 = generate_cache_key("ns", "id", "org", params)
        key2 = generate_cache_key("ns", "id", "org", params)

        assert key1 == key2

    def test_params_order_does_not_affect_key(self):
        """Test that params dict order doesn't affect key."""
        from hs_pylib.cache.postgres import generate_cache_key

        params1 = {"z": 1, "a": 2, "m": 3}
        params2 = {"a": 2, "m": 3, "z": 1}

        key1 = generate_cache_key("ns", "id", params=params1)
        key2 = generate_cache_key("ns", "id", params=params2)

        assert key1 == key2

    def test_params_hash_matches_expected(self):
        """Test that params hash is computed correctly."""
        from hs_pylib.cache.postgres import generate_cache_key

        params = {"key": "value"}
        params_str = json.dumps(params, sort_keys=True, default=str)
        expected_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]

        key = generate_cache_key("ns", "id", params=params)
        actual_hash = key.split(":")[-1]

        assert actual_hash == expected_hash

    def test_none_org_id_excluded_from_key(self):
        """Test that None org_id is not included in key."""
        from hs_pylib.cache.postgres import generate_cache_key

        key = generate_cache_key("ns", "id", org_id=None)
        assert key == "ns:id"

    def test_empty_params_excluded_from_key(self):
        """Test that empty params dict is excluded from key."""
        from hs_pylib.cache.postgres import generate_cache_key

        key_no_params = generate_cache_key("ns", "id", params=None)
        key_empty_params = generate_cache_key("ns", "id", params={})

        # None params - no hash
        assert key_no_params == "ns:id"
        # Empty dict - still generates hash (truthy empty dict)
        # Actually {} is falsy in Python, so it should behave like None
        # Let me check the implementation - yes, `if params:` treats {} as falsy
        assert key_empty_params == "ns:id"


class TestPostgresCacheConstructor:
    """Tests for PostgresCache constructor."""

    def test_constructor_sets_dsn(self):
        """Test constructor sets DSN correctly."""
        from hs_pylib.cache.postgres import PostgresCache

        cache = PostgresCache(dsn="postgresql://user:pass@host/db")
        assert cache._dsn == "postgresql://user:pass@host/db"

    def test_constructor_default_values(self):
        """Test constructor has correct defaults."""
        from hs_pylib.cache.postgres import PostgresCache

        cache = PostgresCache(dsn="postgresql://localhost/test")

        assert cache._table_name == "cache_entries"
        assert cache._default_ttl_seconds == 3600
        assert cache._pool_min_size == 2
        assert cache._pool_max_size == 10
        assert cache._create_table is True
        assert cache._pool is None
        assert cache._initialized is False

    def test_constructor_custom_values(self):
        """Test constructor accepts custom values."""
        from hs_pylib.cache.postgres import PostgresCache

        cache = PostgresCache(
            dsn="postgresql://localhost/test",
            table_name="custom_cache",
            default_ttl_seconds=7200,
            pool_min_size=5,
            pool_max_size=20,
            create_table=False,
        )

        assert cache._table_name == "custom_cache"
        assert cache._default_ttl_seconds == 7200
        assert cache._pool_min_size == 5
        assert cache._pool_max_size == 20
        assert cache._create_table is False

    def test_constructor_with_metrics(self):
        """Test constructor accepts metrics manager."""
        from hs_pylib.cache.postgres import PostgresCache

        mock_metrics = MagicMock()
        cache = PostgresCache(
            dsn="postgresql://localhost/test",
            metrics=mock_metrics,
        )

        assert cache._metrics is mock_metrics
        # Counters not created until init()
        assert cache._hits_counter is None
        assert cache._misses_counter is None


class TestPostgresCacheError:
    """Tests for PostgresCacheError exception."""

    def test_error_is_exception(self):
        """Test PostgresCacheError is an Exception."""
        from hs_pylib.cache.postgres import PostgresCacheError

        assert issubclass(PostgresCacheError, Exception)

    def test_error_with_message(self):
        """Test PostgresCacheError can be raised with message."""
        from hs_pylib.cache.postgres import PostgresCacheError

        with pytest.raises(PostgresCacheError, match="test error"):
            raise PostgresCacheError("test error")


class TestPostgresCacheNotInitialized:
    """Tests for operations before initialization."""

    @pytest.mark.asyncio
    async def test_get_raises_when_not_initialized(self):
        """Test get raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.get("key")

    @pytest.mark.asyncio
    async def test_set_raises_when_not_initialized(self):
        """Test set raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.set("key", "value")

    @pytest.mark.asyncio
    async def test_delete_raises_when_not_initialized(self):
        """Test delete raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.delete("key")

    @pytest.mark.asyncio
    async def test_exists_raises_when_not_initialized(self):
        """Test exists raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.exists("key")

    @pytest.mark.asyncio
    async def test_stats_raises_when_not_initialized(self):
        """Test stats raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.stats()

    @pytest.mark.asyncio
    async def test_invalidate_by_prefix_raises_when_not_initialized(self):
        """Test invalidate_by_prefix raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.invalidate_by_prefix("prefix:")

    @pytest.mark.asyncio
    async def test_invalidate_by_namespace_raises_when_not_initialized(self):
        """Test invalidate_by_namespace raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.invalidate_by_namespace("analytics")

    @pytest.mark.asyncio
    async def test_invalidate_by_org_raises_when_not_initialized(self):
        """Test invalidate_by_org raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.invalidate_by_org("org-id")

    @pytest.mark.asyncio
    async def test_cleanup_expired_raises_when_not_initialized(self):
        """Test cleanup_expired raises error when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache, PostgresCacheError

        cache = PostgresCache(dsn="postgresql://localhost/test")

        with pytest.raises(PostgresCacheError, match="not initialized"):
            await cache.cleanup_expired()


class TestPostgresCacheMocked:
    """Mock-based tests for PostgresCache operations."""

    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        pool = AsyncMock()
        pool.open = AsyncMock()
        pool.close = AsyncMock()

        # Create mock connection with context manager support
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()

        # Setup async context manager
        pool.connection = MagicMock()
        pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

        return pool, mock_conn

    @pytest.mark.asyncio
    async def test_init_creates_pool(self, mock_pool):
        """Test init creates connection pool."""
        pool, mock_conn = mock_pool

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            assert cache._initialized is True
            pool.open.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self, mock_pool):
        """Test calling init multiple times is safe."""
        pool, mock_conn = mock_pool

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()
            await cache.init()
            await cache.init()

            # Should only open once
            assert pool.open.call_count == 1

    @pytest.mark.asyncio
    async def test_close_closes_pool(self, mock_pool):
        """Test close closes connection pool."""
        pool, mock_conn = mock_pool

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()
            await cache.close()

            assert cache._initialized is False
            assert cache._pool is None
            pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self):
        """Test close is safe when not initialized."""
        from hs_pylib.cache.postgres import PostgresCache

        cache = PostgresCache(dsn="postgresql://localhost/test")
        # Should not raise
        await cache.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_pool):
        """Test async context manager usage."""
        pool, mock_conn = mock_pool

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            async with PostgresCache(
                dsn="postgresql://localhost/test",
                create_table=False,
            ) as cache:
                assert cache._initialized is True

            # After exiting context, should be closed
            pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_creates_table_when_enabled(self, mock_pool):
        """Test init creates table when create_table=True."""
        pool, mock_conn = mock_pool

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=True)
            await cache.init()

            # Should have executed CREATE TABLE and indexes
            assert mock_conn.execute.call_count >= 1
            mock_conn.commit.assert_called()

    @pytest.mark.asyncio
    async def test_init_sets_up_metrics(self, mock_pool):
        """Test init creates metrics counters when metrics provided."""
        pool, mock_conn = mock_pool
        mock_metrics = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.counter = MagicMock(return_value=mock_counter)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(
                dsn="postgresql://localhost/test",
                create_table=False,
                metrics=mock_metrics,
            )
            await cache.init()

            # Should create two counters: hits and misses
            assert mock_metrics.counter.call_count == 2
            assert cache._hits_counter is not None
            assert cache._misses_counter is not None

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_key(self, mock_pool):
        """Test get returns None for non-existent key."""
        pool, mock_conn = mock_pool

        # Setup mock to return no rows
        mock_result = AsyncMock()
        mock_result.fetchone = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.get("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_none_for_expired_key(self, mock_pool):
        """Test get returns None and schedules delete for expired key."""
        pool, mock_conn = mock_pool

        import msgpack

        # Setup mock to return expired row
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        value = msgpack.packb({"data": "test"}, use_bin_type=True)

        mock_result = AsyncMock()
        mock_result.fetchone = AsyncMock(return_value=(value, expired_time, "default"))
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.get("expired_key")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_value_for_valid_key(self, mock_pool):
        """Test get returns deserialized value for valid key."""
        pool, mock_conn = mock_pool

        import msgpack

        # Setup mock to return valid row
        future_time = datetime.now(UTC) + timedelta(hours=1)
        original_value = {"data": "test", "count": 42}
        value_bytes = msgpack.packb(original_value, use_bin_type=True)

        mock_result = AsyncMock()
        mock_result.fetchone = AsyncMock(return_value=(value_bytes, future_time, "default"))
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.get("valid_key")

            assert result == original_value

    @pytest.mark.asyncio
    async def test_set_uses_default_ttl(self, mock_pool):
        """Test set uses default TTL when not specified."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(
                dsn="postgresql://localhost/test",
                create_table=False,
                default_ttl_seconds=3600,
            )
            await cache.init()

            await cache.set("key", {"data": "value"})

            # Verify execute was called (for the SET operation)
            mock_conn.execute.assert_called()
            mock_conn.commit.assert_called()

    @pytest.mark.asyncio
    async def test_set_uses_custom_ttl(self, mock_pool):
        """Test set uses custom TTL when specified."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            await cache.set("key", {"data": "value"}, ttl_seconds=600)

            mock_conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_deleted(self, mock_pool):
        """Test delete returns True when key was deleted."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.delete("key")

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, mock_pool):
        """Test delete returns False when key not found."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.rowcount = 0
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.delete("nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_valid_key(self, mock_pool):
        """Test exists returns True for non-expired key."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.fetchone = AsyncMock(return_value=(1,))
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.exists("valid_key")

            assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing_key(self, mock_pool):
        """Test exists returns False for non-existent key."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.fetchone = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.exists("nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_by_prefix_returns_count(self, mock_pool):
        """Test invalidate_by_prefix returns deleted count."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.rowcount = 5
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.invalidate_by_prefix("analytics:")

            assert result == 5

    @pytest.mark.asyncio
    async def test_invalidate_by_namespace_returns_count(self, mock_pool):
        """Test invalidate_by_namespace returns deleted count."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.rowcount = 10
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.invalidate_by_namespace("analytics")

            assert result == 10

    @pytest.mark.asyncio
    async def test_invalidate_by_org_returns_count(self, mock_pool):
        """Test invalidate_by_org returns deleted count."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.rowcount = 3
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.invalidate_by_org("acme-corp")

            assert result == 3

    @pytest.mark.asyncio
    async def test_cleanup_expired_returns_count(self, mock_pool):
        """Test cleanup_expired returns deleted count."""
        pool, mock_conn = mock_pool

        mock_result = AsyncMock()
        mock_result.rowcount = 100
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            result = await cache.cleanup_expired()

            assert result == 100

    @pytest.mark.asyncio
    async def test_stats_returns_correct_structure(self, mock_pool):
        """Test stats returns dict with expected keys."""
        pool, mock_conn = mock_pool

        # Setup mock results for stats queries
        mock_count_result = AsyncMock()
        mock_count_result.fetchone = AsyncMock(return_value=(10, 50000))

        mock_expired_result = AsyncMock()
        mock_expired_result.fetchone = AsyncMock(return_value=(2,))

        mock_namespace_result = AsyncMock()
        mock_namespace_result.fetchall = AsyncMock(
            return_value=[
                ("analytics", 5, 25000),
                ("metrics", 5, 25000),
            ]
        )

        # Return different results for different queries
        mock_conn.execute = AsyncMock(side_effect=[mock_count_result, mock_expired_result, mock_namespace_result])

        with patch("hs_pylib.cache.postgres.AsyncConnectionPool", return_value=pool):
            from hs_pylib.cache.postgres import PostgresCache

            cache = PostgresCache(dsn="postgresql://localhost/test", create_table=False)
            await cache.init()

            stats = await cache.stats()

            assert "entry_count" in stats
            assert "total_size_bytes" in stats
            assert "expired_count" in stats
            assert "namespaces" in stats
            assert stats["entry_count"] == 10
            assert stats["total_size_bytes"] == 50000
            assert stats["expired_count"] == 2
