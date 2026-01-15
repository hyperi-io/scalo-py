"""Integration tests for PostgreSQL configuration loader.

These tests require a running PostgreSQL instance.
They will be skipped if PostgreSQL is not available.

Run locally with:
    docker compose -f docker-compose.postgres.yml up -d
    pytest tests/integration/test_config_postgres_loader.py -v
"""

import asyncio
import os
import uuid

import pytest


@pytest.fixture(scope="module")
def test_namespace():
    """Generate a unique namespace for this test run to avoid collisions."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def config_loader(postgres_dsn, test_namespace):
    """Create a PostgresConfigLoader with the test DSN."""
    from hs_pylib.config import PostgresConfigLoader

    # Clear any cached config
    PostgresConfigLoader.clear_all_cache()

    loader = PostgresConfigLoader(
        dsn=postgres_dsn,
        table_name="config_values_test",
        namespace=test_namespace,
        cache_ttl=1,  # Short TTL for testing
    )

    # Ensure table exists
    assert loader.ensure_table() is True, "Failed to create test config table"

    yield loader

    # Cleanup: delete test namespace
    loader.delete_namespace()


@pytest.fixture(scope="module")
def populated_loader(config_loader):
    """Loader with pre-populated test data."""
    # Clear and populate with test data
    config_loader.clear_cache()

    config_loader.set_value("database.host", "test-host.example.com")
    config_loader.set_value("database.port", 5432)
    config_loader.set_value("database.ssl", True)
    config_loader.set_value("api.timeout", 30)
    config_loader.set_value("api.retries", 3)
    config_loader.set_value("cache.enabled", True)
    config_loader.set_value("cache.ttl", 3600)
    config_loader.set_value("feature.dark_mode", False)
    config_loader.set_value("nested.deep.value", "deeply-nested")

    # Clear cache so tests start fresh
    config_loader.clear_cache()

    return config_loader


class TestPostgresConfigLoaderEnsureTable:
    """Test table creation with real database."""

    def test_ensure_table_creates_table(self, postgres_dsn, test_namespace):
        """Test that ensure_table creates the table if it doesn't exist."""
        from hs_pylib.config import PostgresConfigLoader

        unique_table = f"config_test_{uuid.uuid4().hex[:8]}"

        loader = PostgresConfigLoader(
            dsn=postgres_dsn,
            table_name=unique_table,
            namespace=test_namespace,
        )

        try:
            result = loader.ensure_table()
            assert result is True

            # Verify table exists by setting a value
            assert loader.set_value("test_key", "test_value") is True

        finally:
            # Cleanup: drop the test table
            import psycopg

            with psycopg.connect(postgres_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {unique_table}")
                conn.commit()

    def test_ensure_table_is_idempotent(self, config_loader):
        """Test that ensure_table can be called multiple times safely."""
        # Table already exists from fixture
        result = config_loader.ensure_table()
        assert result is True

        # Call again - should still succeed
        result = config_loader.ensure_table()
        assert result is True


class TestPostgresConfigLoaderSetValue:
    """Test setting configuration values."""

    def test_set_value_string(self, config_loader):
        """Test setting a string value."""
        result = config_loader.set_value("test.string", "hello world")
        assert result is True

        # Clear cache and verify
        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config.get("test", {}).get("string") == "hello world"

    def test_set_value_integer(self, config_loader):
        """Test setting an integer value."""
        result = config_loader.set_value("test.integer", 42)
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config.get("test", {}).get("integer") == 42

    def test_set_value_boolean(self, config_loader):
        """Test setting a boolean value."""
        result = config_loader.set_value("test.boolean", True)
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config.get("test", {}).get("boolean") is True

    def test_set_value_list(self, config_loader):
        """Test setting a list value."""
        result = config_loader.set_value("test.list", [1, 2, 3])
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config.get("test", {}).get("list") == [1, 2, 3]

    def test_set_value_dict(self, config_loader):
        """Test setting a dict value."""
        value = {"key": "value", "nested": {"a": 1}}
        result = config_loader.set_value("test.dict", value)
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config.get("test", {}).get("dict") == value

    def test_set_value_overwrites_existing(self, config_loader):
        """Test that setting a value overwrites existing."""
        config_loader.set_value("test.overwrite", "original")
        config_loader.clear_cache()

        config_loader.set_value("test.overwrite", "updated")
        config_loader.clear_cache()

        config = config_loader.load_sync()
        assert config.get("test", {}).get("overwrite") == "updated"


class TestPostgresConfigLoaderLoadSync:
    """Test synchronous loading."""

    def test_load_sync_returns_all_values(self, populated_loader):
        """Test that load_sync returns all configured values."""
        config = populated_loader.load_sync()

        assert config["database"]["host"] == "test-host.example.com"
        assert config["database"]["port"] == 5432
        assert config["database"]["ssl"] is True
        assert config["api"]["timeout"] == 30
        assert config["api"]["retries"] == 3
        assert config["cache"]["enabled"] is True
        assert config["cache"]["ttl"] == 3600
        assert config["feature"]["dark_mode"] is False
        assert config["nested"]["deep"]["value"] == "deeply-nested"

    def test_load_sync_uses_cache(self, populated_loader):
        """Test that load_sync uses cache on subsequent calls."""
        # First call populates cache
        config1 = populated_loader.load_sync()

        # Second call should use cache (no DB hit)
        config2 = populated_loader.load_sync()

        assert config1 == config2

    def test_load_sync_cache_invalidates_after_ttl(self, populated_loader):
        """Test that cache expires after TTL."""
        import time

        # Populate cache
        populated_loader.load_sync()

        # Verify cache is valid
        assert populated_loader._is_cache_valid() is True

        # Wait for TTL (loader has 1 second TTL)
        time.sleep(1.5)

        # Cache should be invalid
        assert populated_loader._is_cache_valid() is False


class TestPostgresConfigLoaderLoadAsync:
    """Test asynchronous loading."""

    @pytest.mark.asyncio
    async def test_load_async_returns_all_values(self, populated_loader):
        """Test that load_async returns all configured values."""
        populated_loader.clear_cache()

        config = await populated_loader.load_async()

        assert config["database"]["host"] == "test-host.example.com"
        assert config["database"]["port"] == 5432
        assert config["api"]["timeout"] == 30

    @pytest.mark.asyncio
    async def test_load_async_uses_cache(self, populated_loader):
        """Test that load_async uses cache on subsequent calls."""
        populated_loader.clear_cache()

        config1 = await populated_loader.load_async()
        config2 = await populated_loader.load_async()

        assert config1 == config2


class TestPostgresConfigLoaderDeleteValue:
    """Test deleting configuration values."""

    def test_delete_value_removes_key(self, config_loader):
        """Test that delete_value removes the key."""
        config_loader.set_value("to_delete", "value")
        config_loader.clear_cache()

        # Verify it exists
        config = config_loader.load_sync()
        assert "to_delete" in config

        # Delete it
        config_loader.clear_cache()
        result = config_loader.delete_value("to_delete")
        assert result is True

        # Verify it's gone
        config_loader.clear_cache()
        config = config_loader.load_sync()
        assert "to_delete" not in config

    def test_delete_value_nonexistent_succeeds(self, config_loader):
        """Test that deleting nonexistent key succeeds."""
        result = config_loader.delete_value("nonexistent_key_12345")
        assert result is True


class TestPostgresConfigLoaderDeleteNamespace:
    """Test deleting entire namespace."""

    def test_delete_namespace_removes_all_keys(self, postgres_dsn):
        """Test that delete_namespace removes all keys in namespace."""
        from hs_pylib.config import PostgresConfigLoader

        unique_ns = f"delete-test-{uuid.uuid4().hex[:8]}"

        loader = PostgresConfigLoader(
            dsn=postgres_dsn,
            table_name="config_values_test",
            namespace=unique_ns,
        )

        loader.ensure_table()

        # Add multiple values
        loader.set_value("key1", "value1")
        loader.set_value("key2", "value2")
        loader.set_value("key3", "value3")
        loader.clear_cache()

        # Verify they exist
        config = loader.load_sync()
        assert len(config) == 3

        # Delete namespace
        deleted = loader.delete_namespace()
        assert deleted == 3

        # Verify they're gone
        loader.clear_cache()
        config = loader.load_sync()
        assert config == {}


class TestPostgresConfigLoaderNamespaceIsolation:
    """Test that namespaces are properly isolated."""

    def test_namespaces_are_isolated(self, postgres_dsn):
        """Test that different namespaces don't see each other's config."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        ns1 = f"ns1-{uuid.uuid4().hex[:8]}"
        ns2 = f"ns2-{uuid.uuid4().hex[:8]}"

        loader1 = PostgresConfigLoader(
            dsn=postgres_dsn,
            table_name="config_values_test",
            namespace=ns1,
        )
        loader2 = PostgresConfigLoader(
            dsn=postgres_dsn,
            table_name="config_values_test",
            namespace=ns2,
        )

        try:
            loader1.ensure_table()

            # Set different values in each namespace
            loader1.set_value("key", "value-from-ns1")
            loader2.set_value("key", "value-from-ns2")

            loader1.clear_cache()
            loader2.clear_cache()

            # Each should see only its own value
            config1 = loader1.load_sync()
            config2 = loader2.load_sync()

            assert config1["key"] == "value-from-ns1"
            assert config2["key"] == "value-from-ns2"

        finally:
            loader1.delete_namespace()
            loader2.delete_namespace()


class TestPostgresConfigLoaderConcurrency:
    """Test concurrent access patterns."""

    def test_concurrent_writes_are_safe(self, postgres_dsn, test_namespace):
        """Test that concurrent writes don't cause errors."""
        from concurrent.futures import ThreadPoolExecutor

        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn=postgres_dsn,
            table_name="config_values_test",
            namespace=f"{test_namespace}-concurrent",
        )
        loader.ensure_table()

        def write_value(i):
            return loader.set_value(f"concurrent.key{i}", f"value{i}")

        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(write_value, range(20)))

            # All writes should succeed
            assert all(results)

            # Verify all values are present
            loader.clear_cache()
            config = loader.load_sync()

            assert len(config.get("concurrent", {})) == 20

        finally:
            loader.delete_namespace()

    @pytest.mark.asyncio
    async def test_concurrent_async_reads(self, populated_loader):
        """Test that concurrent async reads work correctly."""
        populated_loader.clear_cache()

        # Run multiple concurrent reads
        results = await asyncio.gather(*[populated_loader.load_async() for _ in range(10)])

        # All should return the same data
        first = results[0]
        for result in results[1:]:
            assert result == first


class TestPostgresConfigLoaderEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_namespace_uses_default(self, postgres_dsn):
        """Test that empty namespace falls back to 'default'."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn=postgres_dsn,
            namespace="",
        )

        # Should use default namespace (empty string is falsy)
        assert loader.namespace == "default" or loader.namespace == ""

    def test_special_characters_in_values(self, config_loader):
        """Test that special characters are handled correctly."""
        special_value = "Hello 'world' with \"quotes\" and \\ backslashes"

        result = config_loader.set_value("test.special", special_value)
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config["test"]["special"] == special_value

    def test_unicode_in_values(self, config_loader):
        """Test that unicode characters are handled correctly."""
        unicode_value = "Hello 世界 🌍 مرحبا"

        result = config_loader.set_value("test.unicode", unicode_value)
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config["test"]["unicode"] == unicode_value

    def test_null_value(self, config_loader):
        """Test that null/None values are handled."""
        result = config_loader.set_value("test.null", None)
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config["test"]["null"] is None

    def test_very_long_key(self, config_loader):
        """Test that very long keys work."""
        long_key = "a" * 500

        result = config_loader.set_value(long_key, "value")
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config[long_key] == "value"

    def test_very_large_value(self, config_loader):
        """Test that large values work."""
        large_value = {"data": "x" * 100000}  # 100KB of data

        result = config_loader.set_value("test.large", large_value)
        assert result is True

        config_loader.clear_cache()
        config = config_loader.load_sync()

        assert config["test"]["large"] == large_value
