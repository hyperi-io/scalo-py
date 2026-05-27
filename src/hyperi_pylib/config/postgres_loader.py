"""
PostgreSQL Configuration Loader for hyperi-pylib Config Cascade.

Provides an optional PostgreSQL-backed configuration store that integrates
into the standard 8-layer configuration cascade. PostgreSQL config has HIGH
priority and OVERRIDES file-based config (but not ENV vars or CLI args).

8-Layer Configuration Cascade (with PostgreSQL):
=================================================

    Priority  Layer              Source                  When Used
    --------  -----              ------                  ---------
    1         CLI args           --host=X                Runtime override
    2         ENV vars           MYAPP_DATABASE_HOST     Deployment/secrets
    3         .env file          .env                    Local dev secrets
    4         PostgreSQL         config_values table     Shared org config (OVERRIDES files)
    5         settings.{env}     settings.production.yaml Environment-specific
    6         settings.yaml      settings.yaml           Project base
    7         defaults.yaml      defaults.yaml           Safe defaults
    8         Hard-coded         code fallback           Last resort

    PostgreSQL config OVERRIDES file-based config. This allows centralised
    configuration management where the database is the source of truth.

Fallback File Support:
======================

    When PostgreSQL config is loaded successfully, it can optionally be
    written to a local fallback file. If PostgreSQL becomes unavailable,
    the fallback file is used instead, ensuring continued operation.

    # Enable fallback file (default: false)
    HYPERI_CONFIG_FALLBACK_ENABLED="true"

    # Fallback file path (default: /tmp/{namespace}_config_fallback.yaml)
    HYPERI_CONFIG_FALLBACK_FILE="/config/fallback.yaml"

    # Merge mode: "replace" or "merge" (default: replace)
    # - replace: Fallback file contains only PostgreSQL config
    # - merge: Fallback file merges with existing local config
    HYPERI_CONFIG_FALLBACK_MODE="replace"

Enabling PostgreSQL Config:
===========================

    Set environment variables to enable:

    # Required: PostgreSQL connection string (DSN)
    HYPERI_CONFIG_DSN="postgresql://user:pass@host:5432/dbname"

    # Optional: Table name (default: config_values)
    HYPERI_CONFIG_TABLE="config_values"

    # Optional: Namespace for app isolation (default: default)
    HYPERI_CONFIG_NAMESPACE="my-app"

    # Optional: Cache TTL in seconds (default: 60)
    HYPERI_CONFIG_CACHE_TTL="60"

    # Optional: Connection timeout in seconds (default: 5)
    HYPERI_CONFIG_CONNECT_TIMEOUT="5"

    # Optional: Query timeout in seconds (default: 10)
    HYPERI_CONFIG_QUERY_TIMEOUT="10"

    # Optional: Retry attempts on connection failure (default: 3)
    HYPERI_CONFIG_RETRY_ATTEMPTS="3"

    # Optional: Delay between retries in milliseconds (default: 1000)
    HYPERI_CONFIG_RETRY_DELAY_MS="1000"

    # Optional: Continue startup if PostgreSQL unavailable (default: true)
    # If false, raises PostgresConfigError on connection failure
    HYPERI_CONFIG_OPTIONAL="true"

Database Schema:
================

    Main config table:

    CREATE TABLE IF NOT EXISTS config_values (
        namespace TEXT NOT NULL DEFAULT 'default',
        key TEXT NOT NULL,
        value JSONB NOT NULL,
        description TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by TEXT,
        PRIMARY KEY (namespace, key)
    );

    CREATE INDEX idx_config_namespace ON config_values (namespace);
    CREATE INDEX idx_config_key_prefix ON config_values USING btree (key text_pattern_ops);

    Optional audit trail table (created with ensure_table(with_audit=True)):

    CREATE TABLE IF NOT EXISTS config_values_history (
        id BIGSERIAL PRIMARY KEY,
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        old_value JSONB,
        new_value JSONB,
        changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        changed_by TEXT
    );

Usage:
======

    # Automatic integration - just set HYPERI_CONFIG_DSN
    from hyperi_pylib.config import settings
    value = settings.database.host  # Cascade includes PostgreSQL if enabled

    # Manual loading for custom scenarios
    from hyperi_pylib.config.postgres_loader import PostgresConfigLoader

    loader = PostgresConfigLoader(
        dsn="postgresql://user:pass@host/db",
        namespace="my-app",
    )
    config = await loader.load()

K8s/HELM Deployment:
====================

    # DSN from Kubernetes Secret
    env:
      - name: HYPERI_CONFIG_DSN
        valueFrom:
          secretKeyRef:
            name: app-secrets
            key: config-dsn
      - name: HYPERI_CONFIG_NAMESPACE
        value: "my-app"
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PostgresConfigError(Exception):
    """Raised when PostgreSQL config operations fail."""


class PostgresConfigUnavailable(PostgresConfigError):
    """Raised when PostgreSQL is unavailable but optional=True."""


class PostgresConfigLoader:
    """
    PostgreSQL configuration loader with caching and connection resilience.

    Loads configuration from a PostgreSQL table and caches results
    in memory to avoid repeated database queries.

    Features:
    - Connection timeout and query timeout
    - Retry with exponential backoff on connection failure
    - Optional mode (graceful fallback vs hard failure)
    - Thread-safe caching shared across instances
    - Audit trail support for config changes
    """

    # Class-level cache shared across instances
    _cache: dict[str, dict[str, Any]] = {}
    _cache_times: dict[str, float] = {}

    # Default settings
    DEFAULT_TABLE = "config_values"
    DEFAULT_NAMESPACE = "default"
    DEFAULT_CACHE_TTL = 60  # seconds
    DEFAULT_CONNECT_TIMEOUT = 5  # seconds
    DEFAULT_QUERY_TIMEOUT = 10  # seconds
    DEFAULT_RETRY_ATTEMPTS = 3
    DEFAULT_RETRY_DELAY_MS = 1000
    DEFAULT_OPTIONAL = True  # graceful fallback on failure
    DEFAULT_FALLBACK_ENABLED = False
    DEFAULT_FALLBACK_MODE = "replace"  # "replace" or "merge"

    def __init__(
        self,
        dsn: str | None = None,
        table_name: str | None = None,
        namespace: str | None = None,
        cache_ttl: int | None = None,
        connect_timeout: int | None = None,
        query_timeout: int | None = None,
        retry_attempts: int | None = None,
        retry_delay_ms: int | None = None,
        optional: bool | None = None,
        fallback_enabled: bool | None = None,
        fallback_file: str | None = None,
        fallback_mode: str | None = None,
    ):
        """
        Initialise PostgreSQL config loader.

        Args:
            dsn: PostgreSQL connection string. If None, reads from HYPERI_CONFIG_DSN.
            table_name: Table name for config values. Default: config_values.
            namespace: Namespace for app isolation. Default: default.
            cache_ttl: Cache TTL in seconds. Default: 60.
            connect_timeout: Connection timeout in seconds. Default: 5.
            query_timeout: Query timeout in seconds. Default: 10.
            retry_attempts: Number of retry attempts on connection failure. Default: 3.
            retry_delay_ms: Delay between retries in milliseconds. Default: 1000.
            optional: If True, gracefully fallback on failure. If False, raise error. Default: True.
            fallback_enabled: If True, write config to fallback file after successful load. Default: False.
            fallback_file: Path to fallback file. Default: /tmp/{namespace}_config_fallback.yaml.
            fallback_mode: "replace" to overwrite fallback file, "merge" to merge with existing. Default: replace.
        """
        self.dsn = dsn or os.getenv("HYPERI_CONFIG_DSN")
        self.table_name = table_name or os.getenv("HYPERI_CONFIG_TABLE", self.DEFAULT_TABLE)
        self.namespace = namespace or os.getenv("HYPERI_CONFIG_NAMESPACE", self.DEFAULT_NAMESPACE)
        self.cache_ttl = (
            cache_ttl
            if cache_ttl is not None
            else int(os.getenv("HYPERI_CONFIG_CACHE_TTL", str(self.DEFAULT_CACHE_TTL)))
        )
        self.connect_timeout = (
            connect_timeout
            if connect_timeout is not None
            else int(os.getenv("HYPERI_CONFIG_CONNECT_TIMEOUT", str(self.DEFAULT_CONNECT_TIMEOUT)))
        )
        self.query_timeout = (
            query_timeout
            if query_timeout is not None
            else int(os.getenv("HYPERI_CONFIG_QUERY_TIMEOUT", str(self.DEFAULT_QUERY_TIMEOUT)))
        )
        self.retry_attempts = (
            retry_attempts
            if retry_attempts is not None
            else int(os.getenv("HYPERI_CONFIG_RETRY_ATTEMPTS", str(self.DEFAULT_RETRY_ATTEMPTS)))
        )
        self.retry_delay_ms = (
            retry_delay_ms
            if retry_delay_ms is not None
            else int(os.getenv("HYPERI_CONFIG_RETRY_DELAY_MS", str(self.DEFAULT_RETRY_DELAY_MS)))
        )

        # Parse optional flag from env var
        if optional is not None:
            self.optional = optional
        else:
            opt_env = os.getenv("HYPERI_CONFIG_OPTIONAL", "true").lower()
            self.optional = opt_env in ("true", "1", "yes")

        # Fallback file settings
        if fallback_enabled is not None:
            self.fallback_enabled = fallback_enabled
        else:
            fb_env = os.getenv("HYPERI_CONFIG_FALLBACK_ENABLED", "false").lower()
            self.fallback_enabled = fb_env in ("true", "1", "yes")

        if fallback_file is not None:
            self.fallback_file = Path(fallback_file)
        else:
            fallback_file_env = os.getenv("HYPERI_CONFIG_FALLBACK_FILE")
            if fallback_file_env:
                self.fallback_file = Path(fallback_file_env)
            else:
                self.fallback_file = self._default_fallback_path(self.namespace)

        self.fallback_mode = fallback_mode or os.getenv("HYPERI_CONFIG_FALLBACK_MODE", self.DEFAULT_FALLBACK_MODE)

        # Cache key for this loader instance
        self._cache_key = f"{self.dsn}:{self.namespace}" if self.dsn else None

    @property
    def enabled(self) -> bool:
        """Check if PostgreSQL config is enabled (DSN is set)."""
        return bool(self.dsn)

    @staticmethod
    def _default_fallback_path(namespace: str) -> Path:
        """Per-user cache dir, NEVER system temp.

        Defaulting to ``tempfile.gettempdir()`` was unsafe: ``/tmp`` is
        typically world-readable, so any config (including snapshots of
        secret values) written to the fallback file could be read by
        any other user on the host. Anchor to ``$XDG_CACHE_HOME`` (or
        the platform equivalent) and create the parent dir with 0o700
        on first write.
        """
        import sys

        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            base = Path(xdg_cache) / "hyperi-ai" / "postgres-config-fallback"
        elif sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "hyperi-ai" / "postgres-config-fallback"
        else:
            base = Path.home() / ".cache" / "hyperi-ai" / "postgres-config-fallback"
        return base / f"{namespace}.yaml"

    # Match scheme://user:password@host (password = everything up to '@' that
    # isn't ':' or '/' or '@'). Used to scrub DSN-shaped substrings out of
    # arbitrary text (e.g. psycopg error messages that embed the DSN).
    _DSN_CRED_RE = re.compile(r"(\w+://[^:/@\s]+:)([^@\s]+)(@)")

    def _mask_dsn(self, dsn: str | None) -> str:
        """Mask credentials in a DSN OR any string containing a DSN substring.

        Safe to call on raw psycopg exception messages that embed the
        connection URL alongside other text. Always returns a string.
        """
        if not dsn:
            return ""
        try:
            return self._DSN_CRED_RE.sub(r"\1***\3", dsn)
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
                 -> {"database": {"host": "localhost"}}
        """
        keys = key.split(".")
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    def _validate_table_name(self) -> None:
        """Validate table name to prevent SQL injection."""
        if not self.table_name.replace("_", "").isalnum():
            raise PostgresConfigError(f"Invalid table name: {self.table_name}")

    def _build_conninfo(self) -> str:
        """Build connection string with timeout parameters."""
        # psycopg3 accepts connect_timeout in the DSN or as a keyword arg
        # We'll add it to the DSN if not already present
        if "connect_timeout=" in self.dsn:
            return self.dsn
        separator = "&" if "?" in self.dsn else "?"
        return f"{self.dsn}{separator}connect_timeout={self.connect_timeout}"

    def _handle_connection_error(self, error: Exception, attempt: int) -> None:
        """Log connection error with attempt info."""
        logger.warning(
            "PostgreSQL config connection failed",
            extra={
                "attempt": attempt,
                "max_attempts": self.retry_attempts,
                "error": str(error),
                "dsn_host": self._mask_dsn(self.dsn) if self.dsn else None,
                "namespace": self.namespace,
            },
        )

    def _write_fallback_file(self, config: dict[str, Any]) -> bool:
        """
        Write config to fallback file for use when PostgreSQL is unavailable.

        Args:
            config: Configuration dictionary to write.

        Returns:
            True if successful, False on error.
        """
        if not self.fallback_enabled:
            return False

        try:
            # Ensure parent directory exists. Tighten perms to 0o700 -- the
            # fallback file holds snapshotted config (and potentially
            # secret values) and must not be readable by other users.
            self.fallback_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.fallback_file.parent.chmod(0o700)
            except (OSError, NotImplementedError):
                pass  # Windows / read-only fs

            if self.fallback_mode == "merge" and self.fallback_file.exists():
                # Load existing config and merge
                with open(self.fallback_file, encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}

                # Deep merge: new config overwrites existing
                merged = self._deep_merge(existing, config)
                config_to_write = merged
            else:
                config_to_write = config

            # Write with header comment, then tighten to 0o600 (owner-only).
            with open(self.fallback_file, "w", encoding="utf-8", newline="\n") as f:
                f.write("# PostgreSQL config fallback file\n")
                f.write(f"# Generated at: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
                f.write(f"# Namespace: {self.namespace}\n")
                f.write(f"# Mode: {self.fallback_mode}\n")
                f.write("# This file is auto-generated. Do not edit manually.\n\n")
                yaml.safe_dump(config_to_write, f, default_flow_style=False, sort_keys=True)
            try:
                self.fallback_file.chmod(0o600)
            except (OSError, NotImplementedError):
                pass

            logger.debug(
                "Wrote PostgreSQL config fallback file",
                extra={
                    "fallback_file": str(self.fallback_file),
                    "namespace": self.namespace,
                    "mode": self.fallback_mode,
                    "key_count": len(config),
                },
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to write fallback file",
                extra={
                    "error": str(e),
                    "fallback_file": str(self.fallback_file),
                },
            )
            return False

    def _load_fallback_file(self) -> dict[str, Any] | None:
        """
        Load config from fallback file if it exists.

        Returns:
            Configuration dictionary or None if file doesn't exist or is invalid.
        """
        if not self.fallback_enabled:
            return None

        if not self.fallback_file.exists():
            return None

        try:
            with open(self.fallback_file, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if config is None:
                return None

            logger.info(
                "Loaded config from fallback file (PostgreSQL unavailable)",
                extra={
                    "fallback_file": str(self.fallback_file),
                    "namespace": self.namespace,
                },
            )
            return config

        except Exception as e:
            logger.warning(
                "Failed to load fallback file",
                extra={
                    "error": str(e),
                    "fallback_file": str(self.fallback_file),
                },
            )
            return None

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """
        Deep merge two dictionaries. Override values take precedence.

        Args:
            base: Base dictionary.
            override: Dictionary with values to override.

        Returns:
            Merged dictionary.
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def load_sync(self) -> dict[str, Any]:
        """
        Load configuration from PostgreSQL synchronously.

        Returns cached config if valid, otherwise fetches from database
        with retry logic on connection failures.

        Returns:
            Dictionary of configuration values. Empty dict if disabled.

        Raises:
            PostgresConfigError: If optional=False and PostgreSQL is unavailable.
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
        except ImportError:
            msg = "psycopg not installed, PostgreSQL config disabled. Install with: pip install hyperi-pylib[cache]"
            logger.warning(msg)
            if not self.optional:
                raise PostgresConfigError(msg)
            return {}

        try:
            self._validate_table_name()
        except PostgresConfigError:
            if not self.optional:
                raise
            logger.warning(
                "Invalid table name for PostgreSQL config",
                extra={"table_name": self.table_name},
            )
            return {}

        conninfo = self._build_conninfo()

        last_error = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                config: dict[str, Any] = {}

                with psycopg.connect(conninfo) as conn, conn.cursor() as cur:
                    # Set statement timeout for query
                    cur.execute(f"SET statement_timeout = '{self.query_timeout * 1000}'")  # nosec B608

                    cur.execute(
                        f"SELECT key, value FROM {self.table_name} WHERE namespace = %s ORDER BY key",  # nosec B608
                        (self.namespace,),
                    )

                    for row in cur.fetchall():
                        key, value = row
                        # Value is JSONB, psycopg returns it as Python object
                        self._set_nested(config, key, value)

                # Update cache
                self._set_cache(config)

                # Write fallback file on successful load
                if self.fallback_enabled and config:
                    self._write_fallback_file(config)

                logger.debug(
                    "Loaded PostgreSQL config",
                    extra={
                        "namespace": self.namespace,
                        "key_count": len(config),
                        "attempt": attempt,
                    },
                )

                return config

            except psycopg.OperationalError as e:
                last_error = e
                self._handle_connection_error(e, attempt)

                if attempt < self.retry_attempts:
                    time.sleep(self.retry_delay_ms / 1000)
                continue

            except Exception as e:
                # Non-connection error, don't retry
                logger.warning(
                    "PostgreSQL config query failed",
                    extra={
                        "error": str(e),
                        "dsn_host": self._mask_dsn(self.dsn) if self.dsn else None,
                        "namespace": self.namespace,
                    },
                )
                if not self.optional:
                    raise PostgresConfigError(
                        f"PostgreSQL config failed (host={self._mask_dsn(self.dsn)}): {self._mask_dsn(str(e))}"
                    ) from None
                # Try fallback file
                fallback = self._load_fallback_file()
                if fallback:
                    self._set_cache(fallback)
                    return fallback
                return {}

        # All retries exhausted - try fallback file
        fallback_config = self._load_fallback_file()
        if fallback_config:
            self._set_cache(fallback_config)
            return fallback_config

        if self.optional:
            logger.warning(
                "PostgreSQL config unavailable after retries, no fallback file",
                extra={
                    "attempts": self.retry_attempts,
                    "dsn_host": self._mask_dsn(self.dsn) if self.dsn else None,
                    "namespace": self.namespace,
                },
            )
            return {}
        else:
            raise PostgresConfigError(
                f"PostgreSQL config unavailable after {self.retry_attempts} attempts "
                f"(host={self._mask_dsn(self.dsn)}): {self._mask_dsn(str(last_error))}"
            )

    async def load_async(self) -> dict[str, Any]:
        """
        Load configuration from PostgreSQL asynchronously.

        Returns cached config if valid, otherwise fetches from database
        with retry logic on connection failures.

        Returns:
            Dictionary of configuration values. Empty dict if disabled.

        Raises:
            PostgresConfigError: If optional=False and PostgreSQL is unavailable.
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
        except ImportError:
            msg = "psycopg not installed, PostgreSQL config disabled. Install with: pip install hyperi-pylib[cache]"
            logger.warning(msg)
            if not self.optional:
                raise PostgresConfigError(msg)
            return {}

        try:
            self._validate_table_name()
        except PostgresConfigError:
            if not self.optional:
                raise
            logger.warning(
                "Invalid table name for PostgreSQL config",
                extra={"table_name": self.table_name},
            )
            return {}

        conninfo = self._build_conninfo()

        last_error = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                config: dict[str, Any] = {}

                async with (
                    await psycopg.AsyncConnection.connect(conninfo) as conn,
                    conn.cursor() as cur,
                ):
                    # Set statement timeout for query
                    await cur.execute(f"SET statement_timeout = '{self.query_timeout * 1000}'")  # nosec B608

                    await cur.execute(
                        f"SELECT key, value FROM {self.table_name} WHERE namespace = %s ORDER BY key",  # nosec B608
                        (self.namespace,),
                    )

                    async for row in cur:
                        key, value = row
                        self._set_nested(config, key, value)

                # Update cache
                self._set_cache(config)

                # Write fallback file on successful load
                if self.fallback_enabled and config:
                    self._write_fallback_file(config)

                logger.debug(
                    "Loaded PostgreSQL config (async)",
                    extra={
                        "namespace": self.namespace,
                        "key_count": len(config),
                        "attempt": attempt,
                    },
                )

                return config

            except psycopg.OperationalError as e:
                last_error = e
                self._handle_connection_error(e, attempt)

                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay_ms / 1000)
                continue

            except Exception as e:
                # Non-connection error, don't retry
                logger.warning(
                    "PostgreSQL config query failed",
                    extra={
                        "error": str(e),
                        "dsn_host": self._mask_dsn(self.dsn) if self.dsn else None,
                        "namespace": self.namespace,
                    },
                )
                if not self.optional:
                    raise PostgresConfigError(
                        f"PostgreSQL config failed (host={self._mask_dsn(self.dsn)}): {self._mask_dsn(str(e))}"
                    ) from None
                # Try fallback file
                fallback = self._load_fallback_file()
                if fallback:
                    self._set_cache(fallback)
                    return fallback
                return {}

        # All retries exhausted - try fallback file
        fallback_config = self._load_fallback_file()
        if fallback_config:
            self._set_cache(fallback_config)
            return fallback_config

        if self.optional:
            logger.warning(
                "PostgreSQL config unavailable after retries, no fallback file",
                extra={
                    "attempts": self.retry_attempts,
                    "dsn_host": self._mask_dsn(self.dsn) if self.dsn else None,
                    "namespace": self.namespace,
                },
            )
            return {}
        else:
            raise PostgresConfigError(
                f"PostgreSQL config unavailable after {self.retry_attempts} attempts "
                f"(host={self._mask_dsn(self.dsn)}): {self._mask_dsn(str(last_error))}"
            )

    def ensure_table(self, with_audit: bool = False) -> bool:
        """
        Ensure the config table exists in the database.

        Creates the table and indexes if they don't exist.
        Safe to call multiple times (uses IF NOT EXISTS).

        Args:
            with_audit: If True, also creates audit trail table and trigger.

        Returns:
            True if table exists or was created, False on error.
        """
        if not self.enabled:
            return False

        try:
            import psycopg

            self._validate_table_name()
            conninfo = self._build_conninfo()

            with psycopg.connect(conninfo) as conn:
                with conn.cursor() as cur:
                    # Create main config table with enhanced schema
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} (
                            namespace TEXT NOT NULL DEFAULT 'default',
                            key TEXT NOT NULL,
                            value JSONB NOT NULL,
                            description TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_by TEXT,
                            PRIMARY KEY (namespace, key)
                        )
                    """)  # nosec B608

                    # Index for namespace queries
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_namespace
                        ON {self.table_name} (namespace)
                    """)  # nosec B608

                    # Index for prefix queries (e.g., all kafka.* keys)
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_key_prefix
                        ON {self.table_name} USING btree (key text_pattern_ops)
                    """)  # nosec B608

                    if with_audit:
                        # Create audit trail table
                        history_table = f"{self.table_name}_history"
                        cur.execute(f"""
                            CREATE TABLE IF NOT EXISTS {history_table} (
                                id BIGSERIAL PRIMARY KEY,
                                namespace TEXT NOT NULL,
                                key TEXT NOT NULL,
                                old_value JSONB,
                                new_value JSONB,
                                changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                changed_by TEXT
                            )
                        """)  # nosec B608

                        # Create audit trigger function
                        cur.execute(f"""
                            CREATE OR REPLACE FUNCTION {self.table_name}_audit_trigger()
                            RETURNS TRIGGER AS $$
                            BEGIN
                                IF TG_OP = 'UPDATE' THEN
                                    INSERT INTO {history_table} (namespace, key, old_value, new_value, changed_by)
                                    VALUES (OLD.namespace, OLD.key, OLD.value, NEW.value, NEW.updated_by);
                                ELSIF TG_OP = 'DELETE' THEN
                                    INSERT INTO {history_table} (namespace, key, old_value, new_value, changed_by)
                                    VALUES (OLD.namespace, OLD.key, OLD.value, NULL, current_user);
                                END IF;
                                RETURN NEW;
                            END;
                            $$ LANGUAGE plpgsql
                        """)  # nosec B608

                        # Create trigger (drop first to allow recreation)
                        trigger_name = f"{self.table_name}_audit"
                        cur.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {self.table_name}")  # nosec B608
                        cur.execute(f"""
                            CREATE TRIGGER {trigger_name}
                            AFTER UPDATE OR DELETE ON {self.table_name}
                            FOR EACH ROW EXECUTE FUNCTION {self.table_name}_audit_trigger()
                        """)  # nosec B608

                conn.commit()

            logger.info(
                f"Config table '{self.table_name}' ready",
                extra={"with_audit": with_audit},
            )
            return True

        except ImportError:
            logger.warning("psycopg not installed")
            return False

        except Exception as e:
            logger.error(f"Failed to create config table: {e}")
            return False

    def set_value(
        self,
        key: str,
        value: Any,
        description: str | None = None,
        updated_by: str | None = None,
    ) -> bool:
        """
        Set a configuration value in the database.

        Uses upsert (INSERT ... ON CONFLICT UPDATE) for atomic operation.

        Args:
            key: Configuration key (dot-notation supported, e.g., "database.host")
            value: Value to store (must be JSON-serialisable)
            description: Optional description of the config key
            updated_by: Optional identifier of who made the change (for audit)

        Returns:
            True if successful, False on error.
        """
        if not self.enabled:
            return False

        try:
            import psycopg

            self._validate_table_name()
            conninfo = self._build_conninfo()

            with psycopg.connect(conninfo) as conn:
                with conn.cursor() as cur:
                    # Convert value to JSON
                    json_value = json.dumps(value)

                    cur.execute(
                        f"""
                        INSERT INTO {self.table_name} (namespace, key, value, description, updated_by, updated_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (namespace, key) DO UPDATE SET
                            value = EXCLUDED.value,
                            description = COALESCE(EXCLUDED.description, {self.table_name}.description),
                            updated_by = EXCLUDED.updated_by,
                            updated_at = NOW()
                        """,  # nosec B608
                        (self.namespace, key, json_value, description, updated_by),
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

            self._validate_table_name()
            conninfo = self._build_conninfo()

            with psycopg.connect(conninfo) as conn:
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

            self._validate_table_name()
            conninfo = self._build_conninfo()

            with psycopg.connect(conninfo) as conn:
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

    def get_history(self, key: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get config change history from the audit trail table.

        Args:
            key: Optional key to filter history. If None, returns all history for namespace.
            limit: Maximum number of records to return. Default: 100.

        Returns:
            List of history records, newest first. Empty list if audit table doesn't exist.
        """
        if not self.enabled:
            return []

        try:
            import psycopg

            self._validate_table_name()
            conninfo = self._build_conninfo()
            history_table = f"{self.table_name}_history"

            with psycopg.connect(conninfo) as conn, conn.cursor() as cur:
                if key:
                    cur.execute(
                        f"""
                            SELECT id, namespace, key, old_value, new_value, changed_at, changed_by
                            FROM {history_table}
                            WHERE namespace = %s AND key = %s
                            ORDER BY changed_at DESC
                            LIMIT %s
                            """,  # nosec B608
                        (self.namespace, key, limit),
                    )
                else:
                    cur.execute(
                        f"""
                            SELECT id, namespace, key, old_value, new_value, changed_at, changed_by
                            FROM {history_table}
                            WHERE namespace = %s
                            ORDER BY changed_at DESC
                            LIMIT %s
                            """,  # nosec B608
                        (self.namespace, limit),
                    )

                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "namespace": row[1],
                        "key": row[2],
                        "old_value": row[3],
                        "new_value": row[4],
                        "changed_at": row[5].isoformat() if row[5] else None,
                        "changed_by": row[6],
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.debug(f"Failed to get config history: {e}")
            return []


# Convenience function for Dynaconf-style loading
def load_postgres_config() -> dict[str, Any]:
    """
    Load PostgreSQL config using environment variables.

    Convenience function that creates a loader from environment variables
    and returns the configuration dictionary.

    Environment Variables:
        HYPERI_CONFIG_DSN: PostgreSQL connection string (required to enable)
        HYPERI_CONFIG_TABLE: Table name (default: config_values)
        HYPERI_CONFIG_NAMESPACE: Namespace (default: default)
        HYPERI_CONFIG_CACHE_TTL: Cache TTL in seconds (default: 60)
        HYPERI_CONFIG_CONNECT_TIMEOUT: Connection timeout in seconds (default: 5)
        HYPERI_CONFIG_QUERY_TIMEOUT: Query timeout in seconds (default: 10)
        HYPERI_CONFIG_RETRY_ATTEMPTS: Retry attempts (default: 3)
        HYPERI_CONFIG_RETRY_DELAY_MS: Retry delay in milliseconds (default: 1000)
        HYPERI_CONFIG_OPTIONAL: Continue on failure (default: true)

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
    "PostgresConfigError",
    "PostgresConfigLoader",
    "PostgresConfigUnavailable",
    "get_default_loader",
    "load_postgres_config",
]
