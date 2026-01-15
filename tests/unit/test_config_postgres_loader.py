"""Unit tests for PostgreSQL configuration loader."""

import os
import time
from unittest.mock import MagicMock, patch

import pytest


class TestPostgresConfigLoaderImport:
    """Test module imports and basic structure."""

    def test_import_postgres_loader_module(self):
        """Test that postgres_loader module can be imported."""
        from hs_pylib.config import postgres_loader

        assert hasattr(postgres_loader, "PostgresConfigLoader")
        assert hasattr(postgres_loader, "PostgresConfigError")
        assert hasattr(postgres_loader, "load_postgres_config")
        assert hasattr(postgres_loader, "get_default_loader")

    def test_import_from_config_package(self):
        """Test that postgres loader exports are available from config package."""
        from hs_pylib.config import (
            PostgresConfigError,
            PostgresConfigLoader,
            get_default_loader,
            load_postgres_config,
        )

        assert PostgresConfigLoader is not None
        assert PostgresConfigError is not None
        assert callable(load_postgres_config)
        assert callable(get_default_loader)

    def test_postgres_config_error_is_exception(self):
        """Test that PostgresConfigError is a proper exception."""
        from hs_pylib.config import PostgresConfigError

        assert issubclass(PostgresConfigError, Exception)

        # Test it can be raised and caught
        with pytest.raises(PostgresConfigError, match="test error"):
            raise PostgresConfigError("test error")


class TestPostgresConfigLoaderInit:
    """Test PostgresConfigLoader initialisation."""

    def test_init_with_no_args_reads_env(self):
        """Test initialisation reads from environment variables."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://user:pass@host/db",
                "HS_CONFIG_TABLE": "my_config",
                "HS_CONFIG_NAMESPACE": "my-app",
                "HS_CONFIG_CACHE_TTL": "120",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.dsn == "postgresql://user:pass@host/db"
            assert loader.table_name == "my_config"
            assert loader.namespace == "my-app"
            assert loader.cache_ttl == 120
            assert loader.enabled is True

    def test_init_with_explicit_args(self):
        """Test initialisation with explicit arguments."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://test@localhost/testdb",
            table_name="test_config",
            namespace="test-ns",
            cache_ttl=30,
        )

        assert loader.dsn == "postgresql://test@localhost/testdb"
        assert loader.table_name == "test_config"
        assert loader.namespace == "test-ns"
        assert loader.cache_ttl == 30
        assert loader.enabled is True

    def test_init_without_dsn_is_disabled(self):
        """Test that loader is disabled when no DSN provided."""
        from hs_pylib.config import PostgresConfigLoader

        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            # Remove HS_CONFIG_DSN if it exists
            os.environ.pop("HS_CONFIG_DSN", None)

            loader = PostgresConfigLoader()

            assert loader.dsn is None
            assert loader.enabled is False

    def test_init_defaults(self):
        """Test default values when no env vars set."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {"HS_CONFIG_DSN": "postgresql://x@y/z"}, clear=True):
            loader = PostgresConfigLoader()

            assert loader.table_name == "config_values"
            assert loader.namespace == "default"
            assert loader.cache_ttl == 60


class TestPostgresConfigLoaderMaskDsn:
    """Test DSN masking for secure logging."""

    def test_mask_dsn_hides_password(self):
        """Test that password is masked in DSN."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://user:secretpass@host:5432/db")

        masked = loader._mask_dsn(loader.dsn)

        assert "secretpass" not in masked
        assert "***" in masked
        assert "user" in masked
        assert "host" in masked

    def test_mask_dsn_without_password(self):
        """Test masking DSN without password."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://user@host/db")

        masked = loader._mask_dsn(loader.dsn)

        assert masked == "postgresql://user@host/db"

    def test_mask_dsn_invalid_url_returns_as_is(self):
        """Test that invalid DSN without password is returned as-is."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="not-a-valid-url")

        # Invalid URLs without password component are returned as-is
        # (no password to mask)
        masked = loader._mask_dsn("not-a-valid-url")

        assert masked == "not-a-valid-url"


class TestPostgresConfigLoaderSetNested:
    """Test nested dictionary key setting."""

    def test_set_nested_simple_key(self):
        """Test setting a simple (non-nested) key."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")
        d = {}

        loader._set_nested(d, "key", "value")

        assert d == {"key": "value"}

    def test_set_nested_two_levels(self):
        """Test setting a two-level nested key."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")
        d = {}

        loader._set_nested(d, "database.host", "localhost")

        assert d == {"database": {"host": "localhost"}}

    def test_set_nested_three_levels(self):
        """Test setting a three-level nested key."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")
        d = {}

        loader._set_nested(d, "cache.redis.enabled", True)

        assert d == {"cache": {"redis": {"enabled": True}}}

    def test_set_nested_preserves_existing(self):
        """Test that setting nested key preserves existing siblings."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")
        d = {"database": {"port": 5432}}

        loader._set_nested(d, "database.host", "localhost")

        assert d == {"database": {"host": "localhost", "port": 5432}}


class TestPostgresConfigLoaderCache:
    """Test caching behaviour."""

    def test_cache_is_class_level(self):
        """Test that cache is shared across instances."""
        from hs_pylib.config import PostgresConfigLoader

        # Clear any existing cache
        PostgresConfigLoader.clear_all_cache()

        loader1 = PostgresConfigLoader(dsn="postgresql://x@y/z", namespace="ns1")
        loader2 = PostgresConfigLoader(dsn="postgresql://x@y/z", namespace="ns1")

        # Manually populate cache via loader1
        loader1._set_cache({"key": "value"})

        # loader2 should see the same cache
        assert loader2._get_cached() == {"key": "value"}

    def test_cache_respects_ttl(self):
        """Test that cache expires after TTL."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            namespace="test",
            cache_ttl=1,  # 1 second TTL
        )

        loader._set_cache({"key": "value"})

        # Should be valid immediately
        assert loader._is_cache_valid() is True
        assert loader._get_cached() == {"key": "value"}

        # Wait for TTL to expire
        time.sleep(1.1)

        # Should now be invalid
        assert loader._is_cache_valid() is False
        assert loader._get_cached() is None

    def test_clear_cache_for_namespace(self):
        """Test clearing cache for specific namespace."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader1 = PostgresConfigLoader(dsn="postgresql://x@y/z", namespace="ns1")
        loader2 = PostgresConfigLoader(dsn="postgresql://x@y/z", namespace="ns2")

        loader1._set_cache({"key1": "value1"})
        loader2._set_cache({"key2": "value2"})

        # Clear only ns1
        loader1.clear_cache()

        assert loader1._get_cached() is None
        assert loader2._get_cached() == {"key2": "value2"}

    def test_clear_all_cache(self):
        """Test clearing all caches."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader1 = PostgresConfigLoader(dsn="postgresql://x@y/z", namespace="ns1")
        loader2 = PostgresConfigLoader(dsn="postgresql://x@y/z", namespace="ns2")

        loader1._set_cache({"key1": "value1"})
        loader2._set_cache({"key2": "value2"})

        PostgresConfigLoader.clear_all_cache()

        assert loader1._get_cached() is None
        assert loader2._get_cached() is None


class TestPostgresConfigLoaderLoadSync:
    """Test synchronous loading."""

    def test_load_sync_when_disabled_returns_empty(self):
        """Test that load_sync returns empty dict when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HS_CONFIG_DSN", None)

            loader = PostgresConfigLoader()

            assert loader.load_sync() == {}

    def test_load_sync_returns_cached_if_valid(self):
        """Test that load_sync returns cached data without DB hit."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")
        loader._set_cache({"cached": "data"})

        # Should return cached data without trying to connect
        result = loader.load_sync()

        assert result == {"cached": "data"}

    def test_load_sync_without_psycopg_returns_empty(self):
        """Test that missing psycopg is handled gracefully."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")

        # Mock import to raise ImportError
        with (
            patch.dict("sys.modules", {"psycopg": None}),
            patch("builtins.__import__", side_effect=ImportError("No module named 'psycopg'")),
        ):
            result = loader.load_sync()

        assert result == {}

    def test_load_sync_connection_error_returns_empty(self):
        """Test that connection errors are handled gracefully."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(dsn="postgresql://invalid@nonexistent:9999/db")

        # Mock psycopg to raise connection error
        mock_psycopg = MagicMock()
        mock_psycopg.connect.side_effect = Exception("Connection refused")

        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            result = loader.load_sync()

        assert result == {}

    def test_load_sync_invalid_table_name_raises(self):
        """Test that invalid table names are rejected."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            table_name="invalid;DROP TABLE users;--",
        )

        # Mock successful connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            # Should return empty due to invalid table name (logged as warning)
            result = loader.load_sync()

        assert result == {}


class TestPostgresConfigLoaderSetValue:
    """Test setting values in the database."""

    def test_set_value_when_disabled_returns_false(self):
        """Test that set_value returns False when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HS_CONFIG_DSN", None)

            loader = PostgresConfigLoader()

            assert loader.set_value("key", "value") is False

    def test_set_value_invalid_table_returns_false(self):
        """Test that invalid table name returns False."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            table_name="bad;table",
        )

        # Mock psycopg
        mock_psycopg = MagicMock()
        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            result = loader.set_value("key", "value")

        assert result is False


class TestPostgresConfigLoaderDeleteValue:
    """Test deleting values from the database."""

    def test_delete_value_when_disabled_returns_false(self):
        """Test that delete_value returns False when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HS_CONFIG_DSN", None)

            loader = PostgresConfigLoader()

            assert loader.delete_value("key") is False


class TestPostgresConfigLoaderDeleteNamespace:
    """Test deleting entire namespace."""

    def test_delete_namespace_when_disabled_returns_zero(self):
        """Test that delete_namespace returns 0 when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HS_CONFIG_DSN", None)

            loader = PostgresConfigLoader()

            assert loader.delete_namespace() == 0


class TestPostgresConfigLoaderEnsureTable:
    """Test table creation."""

    def test_ensure_table_when_disabled_returns_false(self):
        """Test that ensure_table returns False when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HS_CONFIG_DSN", None)

            loader = PostgresConfigLoader()

            assert loader.ensure_table() is False


class TestLoadPostgresConfigFunction:
    """Test the convenience function."""

    def test_load_postgres_config_uses_env_vars(self):
        """Test that load_postgres_config reads from environment."""
        from hs_pylib.config import load_postgres_config
        from hs_pylib.config.postgres_loader import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        # When disabled, should return empty dict
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HS_CONFIG_DSN", None)

            result = load_postgres_config()

        assert result == {}


class TestGetDefaultLoader:
    """Test the default loader singleton."""

    def test_get_default_loader_returns_loader(self):
        """Test that get_default_loader returns a PostgresConfigLoader."""
        from hs_pylib.config import get_default_loader
        from hs_pylib.config.postgres_loader import PostgresConfigLoader

        loader = get_default_loader()

        assert isinstance(loader, PostgresConfigLoader)

    def test_get_default_loader_returns_same_instance(self):
        """Test that get_default_loader returns singleton."""
        # Reset the singleton
        import hs_pylib.config.postgres_loader as pl
        from hs_pylib.config import get_default_loader
        from hs_pylib.config.postgres_loader import _default_loader

        pl._default_loader = None

        loader1 = get_default_loader()
        loader2 = get_default_loader()

        assert loader1 is loader2
