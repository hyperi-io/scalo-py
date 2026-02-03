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

        # Set retry_attempts=1 to avoid waiting for retries
        loader = PostgresConfigLoader(
            dsn="postgresql://invalid@nonexistent:9999/db",
            retry_attempts=1,
        )

        # Create mock psycopg with proper OperationalError class
        mock_psycopg = MagicMock()
        # Create a real exception class for OperationalError
        mock_psycopg.OperationalError = type("OperationalError", (Exception,), {})
        mock_psycopg.connect.side_effect = mock_psycopg.OperationalError("Connection refused")

        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            result = loader.load_sync()

        assert result == {}

    def test_load_sync_invalid_table_name_returns_empty_when_optional(self):
        """Test that invalid table names return empty dict when optional=True."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            table_name="invalid;DROP TABLE users;--",
            optional=True,  # Default, but explicit for clarity
        )

        # Validation happens before connect, so no mock needed
        # Should return empty due to invalid table name (logged as warning)
        result = loader.load_sync()

        assert result == {}

    def test_load_sync_invalid_table_name_raises_when_not_optional(self):
        """Test that invalid table names raise error when optional=False."""
        from hs_pylib.config import PostgresConfigError, PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            table_name="invalid;DROP TABLE users;--",
            optional=False,
        )

        # Should raise PostgresConfigError due to invalid table name
        with pytest.raises(PostgresConfigError, match="Invalid table name"):
            loader.load_sync()


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


class TestPostgresConfigLoaderConnectionResilience:
    """Test connection resilience features (timeouts, retries, optional flag)."""

    def test_init_connection_timeout_from_env(self):
        """Test connection timeout can be set via environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_CONNECT_TIMEOUT": "15",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.connect_timeout == 15

    def test_init_query_timeout_from_env(self):
        """Test query timeout can be set via environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_QUERY_TIMEOUT": "30",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.query_timeout == 30

    def test_init_retry_attempts_from_env(self):
        """Test retry attempts can be set via environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_RETRY_ATTEMPTS": "5",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.retry_attempts == 5

    def test_init_retry_delay_from_env(self):
        """Test retry delay can be set via environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_RETRY_DELAY_MS": "2000",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.retry_delay_ms == 2000

    def test_init_optional_true_from_env(self):
        """Test optional flag true from environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_OPTIONAL": "true",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.optional is True

    def test_init_optional_false_from_env(self):
        """Test optional flag false from environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_OPTIONAL": "false",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.optional is False

    def test_init_optional_false_from_arg(self):
        """Test optional flag can be set via constructor argument."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            optional=False,
        )

        assert loader.optional is False

    def test_init_defaults(self):
        """Test default values for connection resilience settings."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {"HS_CONFIG_DSN": "postgresql://x@y/z"}, clear=True):
            loader = PostgresConfigLoader()

            assert loader.connect_timeout == 5  # DEFAULT_CONNECT_TIMEOUT
            assert loader.query_timeout == 10  # DEFAULT_QUERY_TIMEOUT
            assert loader.retry_attempts == 3  # DEFAULT_RETRY_ATTEMPTS
            assert loader.retry_delay_ms == 1000  # DEFAULT_RETRY_DELAY_MS
            assert loader.optional is True  # DEFAULT_OPTIONAL

    def test_build_conninfo_adds_connect_timeout(self):
        """Test that _build_conninfo adds connect_timeout to DSN."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://user@host/db",
            connect_timeout=10,
        )

        conninfo = loader._build_conninfo()

        assert "connect_timeout=10" in conninfo

    def test_build_conninfo_preserves_existing_timeout(self):
        """Test that _build_conninfo preserves existing connect_timeout in DSN."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://user@host/db?connect_timeout=30",
            connect_timeout=10,  # Should be ignored since DSN has one
        )

        conninfo = loader._build_conninfo()

        assert conninfo == "postgresql://user@host/db?connect_timeout=30"
        assert "connect_timeout=10" not in conninfo

    def test_build_conninfo_with_existing_params(self):
        """Test that _build_conninfo uses & separator when DSN has params."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://user@host/db?sslmode=require",
            connect_timeout=5,
        )

        conninfo = loader._build_conninfo()

        assert conninfo == "postgresql://user@host/db?sslmode=require&connect_timeout=5"


class TestPostgresConfigLoaderOptionalFlag:
    """Test optional flag behaviour (graceful fallback vs hard failure)."""

    def test_load_sync_optional_true_returns_empty_on_import_error(self):
        """Test that load_sync returns empty dict on import error when optional=True."""
        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z", optional=True)

        with (
            patch.dict("sys.modules", {"psycopg": None}),
            patch("builtins.__import__", side_effect=ImportError("No psycopg")),
        ):
            result = loader.load_sync()

        assert result == {}

    def test_load_sync_optional_false_raises_on_import_error(self):
        """Test that load_sync raises PostgresConfigError on import error when optional=False."""
        from hs_pylib.config import PostgresConfigError, PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z", optional=False)

        with (
            patch.dict("sys.modules", {"psycopg": None}),
            patch("builtins.__import__", side_effect=ImportError("No psycopg")),
            pytest.raises(PostgresConfigError, match="psycopg not installed"),
        ):
            loader.load_sync()


class TestPostgresConfigLoaderAuditTrail:
    """Test audit trail functionality."""

    def test_set_value_accepts_description_and_updated_by(self):
        """Test that set_value accepts description and updated_by parameters."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")

        # Mock the database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            result = loader.set_value(
                "database.host",
                "localhost",
                description="Database hostname",
                updated_by="admin@example.com",
            )

        # Should succeed (returns True on successful DB operation)
        assert result is True

        # Verify the execute was called with description and updated_by
        call_args = mock_cursor.execute.call_args
        assert call_args is not None
        # The second argument tuple should contain description and updated_by
        params = call_args[0][1]  # (namespace, key, json_value, description, updated_by)
        assert params[3] == "Database hostname"
        assert params[4] == "admin@example.com"

    def test_get_history_returns_empty_when_disabled(self):
        """Test that get_history returns empty list when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HS_CONFIG_DSN", None)

            loader = PostgresConfigLoader()

            assert loader.get_history() == []

    def test_ensure_table_with_audit_flag(self):
        """Test that ensure_table accepts with_audit parameter."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")

        # Mock the database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            result = loader.ensure_table(with_audit=True)

        assert result is True

        # Verify that multiple CREATE statements were executed
        # (main table, indexes, history table, trigger function, trigger)
        assert mock_cursor.execute.call_count >= 5


class TestPostgresConfigUnavailableException:
    """Test PostgresConfigUnavailable exception."""

    def test_import_postgres_config_unavailable(self):
        """Test that PostgresConfigUnavailable can be imported."""
        from hs_pylib.config import PostgresConfigUnavailable

        assert PostgresConfigUnavailable is not None

    def test_postgres_config_unavailable_is_subclass_of_error(self):
        """Test that PostgresConfigUnavailable is a subclass of PostgresConfigError."""
        from hs_pylib.config import PostgresConfigError, PostgresConfigUnavailable

        assert issubclass(PostgresConfigUnavailable, PostgresConfigError)

    def test_postgres_config_unavailable_can_be_raised(self):
        """Test that PostgresConfigUnavailable can be raised and caught."""
        from hs_pylib.config import PostgresConfigUnavailable

        with pytest.raises(PostgresConfigUnavailable, match="unavailable"):
            raise PostgresConfigUnavailable("database unavailable")


class TestPostgresConfigLoaderFallbackFile:
    """Test fallback file functionality."""

    def test_init_fallback_disabled_by_default(self):
        """Test that fallback is disabled by default."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(os.environ, {"HS_CONFIG_DSN": "postgresql://x@y/z"}, clear=True):
            loader = PostgresConfigLoader()

            assert loader.fallback_enabled is False

    def test_init_fallback_enabled_from_env(self):
        """Test fallback can be enabled via environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_FALLBACK_ENABLED": "true",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.fallback_enabled is True

    def test_init_fallback_file_from_env(self):
        """Test fallback file path can be set via environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_FALLBACK_FILE": "/custom/path/fallback.yaml",
            },
        ):
            loader = PostgresConfigLoader()

            assert str(loader.fallback_file) == "/custom/path/fallback.yaml"

    def test_init_fallback_mode_from_env(self):
        """Test fallback mode can be set via environment variable."""
        from hs_pylib.config import PostgresConfigLoader

        with patch.dict(
            os.environ,
            {
                "HS_CONFIG_DSN": "postgresql://x@y/z",
                "HS_CONFIG_FALLBACK_MODE": "merge",
            },
        ):
            loader = PostgresConfigLoader()

            assert loader.fallback_mode == "merge"

    def test_init_fallback_from_args(self):
        """Test fallback settings can be set via constructor arguments."""
        from pathlib import Path

        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            fallback_enabled=True,
            fallback_file="/my/fallback.yaml",
            fallback_mode="merge",
        )

        assert loader.fallback_enabled is True
        assert loader.fallback_file == Path("/my/fallback.yaml")
        assert loader.fallback_mode == "merge"

    def test_write_fallback_file_disabled(self):
        """Test that _write_fallback_file returns False when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            fallback_enabled=False,
        )

        result = loader._write_fallback_file({"key": "value"})

        assert result is False

    def test_write_fallback_file_creates_file(self, tmp_path):
        """Test that _write_fallback_file creates the fallback file."""
        from hs_pylib.config import PostgresConfigLoader

        fallback_file = tmp_path / "fallback.yaml"

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            fallback_enabled=True,
            fallback_file=str(fallback_file),
        )

        config = {"database": {"host": "localhost", "port": 5432}}
        result = loader._write_fallback_file(config)

        assert result is True
        assert fallback_file.exists()

        content = fallback_file.read_text()
        assert "database:" in content
        assert "host: localhost" in content
        assert "port: 5432" in content
        assert "# PostgreSQL config fallback file" in content

    def test_write_fallback_file_merge_mode(self, tmp_path):
        """Test that merge mode merges with existing file."""
        import yaml

        from hs_pylib.config import PostgresConfigLoader

        fallback_file = tmp_path / "fallback.yaml"

        # Create existing file
        existing = {"existing_key": "existing_value", "database": {"user": "olduser"}}
        with open(fallback_file, "w") as f:
            yaml.safe_dump(existing, f)

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            fallback_enabled=True,
            fallback_file=str(fallback_file),
            fallback_mode="merge",
        )

        new_config = {"database": {"host": "newhost"}}
        result = loader._write_fallback_file(new_config)

        assert result is True

        # Read and verify merged content
        with open(fallback_file) as f:
            merged = yaml.safe_load(f)

        assert merged["existing_key"] == "existing_value"
        assert merged["database"]["host"] == "newhost"
        assert merged["database"]["user"] == "olduser"

    def test_load_fallback_file_disabled(self):
        """Test that _load_fallback_file returns None when disabled."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            fallback_enabled=False,
        )

        result = loader._load_fallback_file()

        assert result is None

    def test_load_fallback_file_not_exists(self, tmp_path):
        """Test that _load_fallback_file returns None when file doesn't exist."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            fallback_enabled=True,
            fallback_file=str(tmp_path / "nonexistent.yaml"),
        )

        result = loader._load_fallback_file()

        assert result is None

    def test_load_fallback_file_success(self, tmp_path):
        """Test that _load_fallback_file loads config from file."""
        import yaml

        from hs_pylib.config import PostgresConfigLoader

        fallback_file = tmp_path / "fallback.yaml"

        config = {"database": {"host": "localhost"}, "api": {"timeout": 30}}
        with open(fallback_file, "w") as f:
            yaml.safe_dump(config, f)

        loader = PostgresConfigLoader(
            dsn="postgresql://x@y/z",
            fallback_enabled=True,
            fallback_file=str(fallback_file),
        )

        result = loader._load_fallback_file()

        assert result == config

    def test_deep_merge_simple(self):
        """Test _deep_merge with simple dicts."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")

        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        result = loader._deep_merge(base, override)

        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self):
        """Test _deep_merge with nested dicts."""
        from hs_pylib.config import PostgresConfigLoader

        loader = PostgresConfigLoader(dsn="postgresql://x@y/z")

        base = {"db": {"host": "old", "port": 5432}}
        override = {"db": {"host": "new", "user": "admin"}}

        result = loader._deep_merge(base, override)

        assert result == {"db": {"host": "new", "port": 5432, "user": "admin"}}

    def test_load_sync_uses_fallback_on_connection_error(self, tmp_path):
        """Test that load_sync uses fallback file when DB is unavailable."""
        import yaml

        from hs_pylib.config import PostgresConfigLoader

        PostgresConfigLoader.clear_all_cache()

        fallback_file = tmp_path / "fallback.yaml"
        fallback_config = {"database": {"host": "fallback-host"}}
        with open(fallback_file, "w") as f:
            yaml.safe_dump(fallback_config, f)

        loader = PostgresConfigLoader(
            dsn="postgresql://invalid@nonexistent:9999/db",
            fallback_enabled=True,
            fallback_file=str(fallback_file),
            retry_attempts=1,
        )

        # Mock psycopg with OperationalError
        mock_psycopg = MagicMock()
        mock_psycopg.OperationalError = type("OperationalError", (Exception,), {})
        mock_psycopg.connect.side_effect = mock_psycopg.OperationalError("Connection refused")

        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            result = loader.load_sync()

        assert result == fallback_config
