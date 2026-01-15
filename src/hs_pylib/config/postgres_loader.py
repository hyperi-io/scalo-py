"""
PostgreSQL Configuration Loader for hs-pylib Config Cascade.

Provides an optional PostgreSQL-backed configuration store that integrates
into the standard 8-layer configuration cascade as layer 5 (between
environment-specific files and project defaults).

8-Layer Configuration Cascade (with PostgreSQL):
=================================================

    Priority  Layer              Source                  When Used
    --------  -----              ------                  ---------
    1         CLI args           --host=X                Runtime override
    2         ENV vars           MYAPP_DATABASE_HOST     Deployment/secrets
    3         .env file          .env                    Local dev secrets
    4         settings.{env}     settings.production.yaml Environment-specific
    5         PostgreSQL         config_values table     Shared org config (OPTIONAL)
    6         settings.yaml      settings.yaml           Project base
    7         defaults.yaml      defaults.yaml           Safe defaults
    8         Hard-coded         code fallback           Last resort

Enabling PostgreSQL Config:
===========================

    Set environment variables to enable:

    # Required: PostgreSQL connection string (DSN)
    HS_CONFIG_DSN="postgresql://user:pass@host:5432/dbname"

    # Optional: Table name (default: config_values)
    HS_CONFIG_TABLE="config_values"

    # Optional: Namespace for app isolation (default: default)
    HS_CONFIG_NAMESPACE="my-app"

    # Optional: Cache TTL in seconds (default: 60)
    HS_CONFIG_CACHE_TTL="60"

Database Schema:
================

    CREATE TABLE IF NOT EXISTS config_values (
        namespace TEXT NOT NULL DEFAULT 'default',
        key TEXT NOT NULL,
        value JSONB NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (namespace, key)
    );

    CREATE INDEX idx_config_namespace ON config_values (namespace);

Usage:
======

    # Automatic integration - just set HS_CONFIG_DSN
    from hs_pylib.config import settings
    value = settings.database.host  # Cascade includes PostgreSQL if enabled

    # Manual loading for custom scenarios
    from hs_pylib.config.postgres_loader import PostgresConfigLoader

    loader = PostgresConfigLoader(
        dsn="postgresql://user:pass@host/db",
        namespace="my-app",
    )
    config = await loader.load()

K8s/HELM Deployment:
====================

    # DSN from Kubernetes Secret
    env:
      - name: HS_CONFIG_DSN
        valueFrom:
          secretKeyRef:
            name: app-secrets
            key: config-dsn
      - name: HS_CONFIG_NAMESPACE
        value: "my-app"
"""

import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class PostgresConfigError(Exception):
    """Raised when PostgreSQL config operations fail."""

    pass


class PostgresConfigLoader:
    """
    PostgreSQL configuration loader with caching.

    Loads configuration from a PostgreSQL table and caches results
    in memory to avoid repeated database queries.

    Thread-safe for read operations. Cache is shared across instances
    with the same DSN/namespace combination.
    """

    # Class-level cache shared across instances
    _cache: dict[str, dict[str, Any]] = {}
    _cache_times: dict[str, float] = {}

    # Default settings
    DEFAULT_TABLE = "config_values"
    DEFAULT_NAMESPACE = "default"
    DEFAULT_CACHE_TTL = 60  # seconds

    def __init__(
        self,
        dsn: str | None = None,
        table_name: str | None = None,
        namespace: str | None = None,
        cache_ttl: int | None = None,
    ):
        """
        Initialise PostgreSQL config loader.

        Args:
            dsn: PostgreSQL connection string. If None, reads from HS_CONFIG_DSN.
            table_name: Table name for config values. Default: config_values.
            namespace: Namespace for app isolation. Default: default.
            cache_ttl: Cache TTL in seconds. Default: 60.
        """
        self.dsn = dsn or os.getenv("HS_CONFIG_DSN")
        self.table_name = table_name or os.getenv("HS_CONFIG_TABLE", self.DEFAULT_TABLE)
        self.namespace = namespace or os.getenv("HS_CONFIG_NAMESPACE", self.DEFAULT_NAMESPACE)
        self.cache_ttl = cache_ttl or int(os.getenv("HS_CONFIG_CACHE_TTL", str(self.DEFAULT_CACHE_TTL)))

        # Cache key for this loader instance
        self._cache_key = f"{self.dsn}:{self.namespace}" if self.dsn else None

    @property
    def enabled(self) -> bool:
        """Check if PostgreSQL config is enabled (DSN is set)."""
        return bool(self.dsn)

    def _mask_dsn(self, dsn: str) -> str:
        """Mask credentials in DSN for logging."""
        try:
            parsed = urlparse(dsn)
            if parsed.password:
                masked = dsn.replace(f":{parsed.password}@", ":***@")
                return masked
            return dsn
        except Exception:
            return "postgresql://***"

    def _is_cache_valid(self) -> bool:
        """Check if cached config is still valid."""
        if not self._cache_key:
            return False
        if self._cache_key not in self._cache:
            return False
        cache_time = self._cache_times.get(self._cache_key, 0)
        return (time.time() - cache_time) < self.cache_ttl

    def _get_cached(self) -> dict[str, Any] | None:
        """Get config from cache if valid."""
        if self._is_cache_valid():
            return self._cache.get(self._cache_key, {}).copy()
        return None

    def _set_cache(self, config: dict[str, Any]) -> None:
        """Update cache with new config."""
        if self._cache_key:
            self._cache[self._cache_key] = config.copy()
            self._cache_times[self._cache_key] = time.time()

    def clear_cache(self) -> None:
        """Clear cached config for this loader's namespace."""
        if self._cache_key:
            self._cache.pop(self._cache_key, None)
            self._cache_times.pop(self._cache_key, None)

    @classmethod
    def clear_all_cache(cls) -> None:
        """Clear all cached configs across all loaders."""
        cls._cache.clear()
        cls._cache_times.clear()

    def _set_nested(self, d: dict, key: str, value: Any) -> None:
        """
        Set nested dict value from dot-notation key.

        Example: _set_nested({}, "database.host", "localhost")
                 → {"database": {"host": "localhost"}}
        """
        keys = key.split(".")
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    def load_sync(self) -> dict[str, Any]:
        """
        Load configuration from PostgreSQL synchronously.

        Returns cached config if valid, otherwise fetches from database.
        Falls through gracefully on errors with a warning log.

        Returns:
            Dictionary of configuration values. Empty dict if disabled or on error.
        """
        if not self.enabled:
            return {}

        # Check cache first
        cached = self._get_cached()
        if cached is not None:
            logger.debug("Using cached PostgreSQL config", extra={"namespace": self.namespace})
            return cached

        try:
            import psycopg

            config: dict[str, Any] = {}

            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                # Use parameterised query for namespace, but table name must be
                # validated since it can't be parameterised
                if not self.table_name.replace("_", "").isalnum():
                    raise PostgresConfigError(f"Invalid table name: {self.table_name}")

                cur.execute(
                    f"SELECT key, value FROM {self.table_name} WHERE namespace = %s",  # nosec B608
                    (self.namespace,),
                )

                for row in cur.fetchall():
                    key, value = row
                    # Value is JSONB, psycopg returns it as Python object
                    self._set_nested(config, key, value)

            # Update cache
            self._set_cache(config)

            logger.debug(
                "Loaded PostgreSQL config",
                extra={
                    "namespace": self.namespace,
                    "key_count": len(config),
                },
            )

            return config

        except ImportError:
            logger.warning(
                "psycopg not installed, PostgreSQL config disabled. Install with: pip install hs-pylib[cache]"
            )
            return {}

        except Exception as e:
            logger.warning(
                "PostgreSQL config unavailable, using file cascade",
                extra={
                    "error": str(e),
                    "dsn_host": self._mask_dsn(self.dsn) if self.dsn else None,
                    "namespace": self.namespace,
                },
            )
            return {}

    async def load_async(self) -> dict[str, Any]:
        """
        Load configuration from PostgreSQL asynchronously.

        Returns cached config if valid, otherwise fetches from database.
        Falls through gracefully on errors with a warning log.

        Returns:
            Dictionary of configuration values. Empty dict if disabled or on error.
        """
        if not self.enabled:
            return {}

        # Check cache first
        cached = self._get_cached()
        if cached is not None:
            logger.debug("Using cached PostgreSQL config", extra={"namespace": self.namespace})
            return cached

        try:
            import psycopg

            config: dict[str, Any] = {}

            async with await psycopg.AsyncConnection.connect(self.dsn) as conn, conn.cursor() as cur:
                # Validate table name
                if not self.table_name.replace("_", "").isalnum():
                    raise PostgresConfigError(f"Invalid table name: {self.table_name}")

                await cur.execute(
                    f"SELECT key, value FROM {self.table_name} WHERE namespace = %s",  # nosec B608
                    (self.namespace,),
                )

                async for row in cur:
                    key, value = row
                    self._set_nested(config, key, value)

            # Update cache
            self._set_cache(config)

            logger.debug(
                "Loaded PostgreSQL config (async)",
                extra={
                    "namespace": self.namespace,
                    "key_count": len(config),
                },
            )

            return config

        except ImportError:
            logger.warning(
                "psycopg not installed, PostgreSQL config disabled. Install with: pip install hs-pylib[cache]"
            )
            return {}

        except Exception as e:
            logger.warning(
                "PostgreSQL config unavailable, using file cascade",
                extra={
                    "error": str(e),
                    "dsn_host": self._mask_dsn(self.dsn) if self.dsn else None,
                    "namespace": self.namespace,
                },
            )
            return {}

    def ensure_table(self) -> bool:
        """
        Ensure the config table exists in the database.

        Creates the table and index if they don't exist.
        Safe to call multiple times (uses IF NOT EXISTS).

        Returns:
            True if table exists or was created, False on error.
        """
        if not self.enabled:
            return False

        try:
            import psycopg

            # Validate table name
            if not self.table_name.replace("_", "").isalnum():
                raise PostgresConfigError(f"Invalid table name: {self.table_name}")

            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} (
                            namespace TEXT NOT NULL DEFAULT 'default',
                            key TEXT NOT NULL,
                            value JSONB NOT NULL,
                            updated_at TIMESTAMPTZ DEFAULT NOW(),
                            PRIMARY KEY (namespace, key)
                        )
                    """)  # nosec B608

                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_namespace
                        ON {self.table_name} (namespace)
                    """)  # nosec B608

                conn.commit()

            logger.info(f"Config table '{self.table_name}' ready")
            return True

        except ImportError:
            logger.warning("psycopg not installed")
            return False

        except Exception as e:
            logger.error(f"Failed to create config table: {e}")
            return False

    def set_value(self, key: str, value: Any) -> bool:
        """
        Set a configuration value in the database.

        Uses upsert (INSERT ... ON CONFLICT UPDATE) for atomic operation.

        Args:
            key: Configuration key (dot-notation supported, e.g., "database.host")
            value: Value to store (must be JSON-serialisable)

        Returns:
            True if successful, False on error.
        """
        if not self.enabled:
            return False

        try:
            import psycopg

            # Validate table name
            if not self.table_name.replace("_", "").isalnum():
                raise PostgresConfigError(f"Invalid table name: {self.table_name}")

            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    # Convert value to JSON if it's not already a string
                    json_value = json.dumps(value) if not isinstance(value, str) else json.dumps(value)

                    cur.execute(
                        f"""
                        INSERT INTO {self.table_name} (namespace, key, value, updated_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT (namespace, key) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = NOW()
                        """,  # nosec B608
                        (self.namespace, key, json_value),
                    )
                conn.commit()

            # Invalidate cache
            self.clear_cache()

            logger.debug(f"Set config value: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to set config value '{key}': {e}")
            return False

    def delete_value(self, key: str) -> bool:
        """
        Delete a configuration value from the database.

        Args:
            key: Configuration key to delete.

        Returns:
            True if successful (even if key didn't exist), False on error.
        """
        if not self.enabled:
            return False

        try:
            import psycopg

            # Validate table name
            if not self.table_name.replace("_", "").isalnum():
                raise PostgresConfigError(f"Invalid table name: {self.table_name}")

            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {self.table_name} WHERE namespace = %s AND key = %s",  # nosec B608
                        (self.namespace, key),
                    )
                conn.commit()

            # Invalidate cache
            self.clear_cache()

            logger.debug(f"Deleted config value: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete config value '{key}': {e}")
            return False

    def delete_namespace(self) -> int:
        """
        Delete all configuration values in the current namespace.

        Returns:
            Number of deleted rows, or -1 on error.
        """
        if not self.enabled:
            return 0

        try:
            import psycopg

            # Validate table name
            if not self.table_name.replace("_", "").isalnum():
                raise PostgresConfigError(f"Invalid table name: {self.table_name}")

            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {self.table_name} WHERE namespace = %s",  # nosec B608
                        (self.namespace,),
                    )
                    deleted = cur.rowcount
                conn.commit()

            # Invalidate cache
            self.clear_cache()

            logger.info(f"Deleted {deleted} config values in namespace '{self.namespace}'")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete namespace '{self.namespace}': {e}")
            return -1


# Convenience function for Dynaconf-style loading
def load_postgres_config() -> dict[str, Any]:
    """
    Load PostgreSQL config using environment variables.

    Convenience function that creates a loader from environment variables
    and returns the configuration dictionary.

    Environment Variables:
        HS_CONFIG_DSN: PostgreSQL connection string (required to enable)
        HS_CONFIG_TABLE: Table name (default: config_values)
        HS_CONFIG_NAMESPACE: Namespace (default: default)
        HS_CONFIG_CACHE_TTL: Cache TTL in seconds (default: 60)

    Returns:
        Dictionary of configuration values. Empty dict if disabled or on error.
    """
    loader = PostgresConfigLoader()
    return loader.load_sync()


# Module-level loader instance for shared caching
_default_loader: PostgresConfigLoader | None = None


def get_default_loader() -> PostgresConfigLoader:
    """Get or create the default PostgreSQL config loader."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PostgresConfigLoader()
    return _default_loader


__all__ = [
    "PostgresConfigLoader",
    "PostgresConfigError",
    "load_postgres_config",
    "get_default_loader",
]
