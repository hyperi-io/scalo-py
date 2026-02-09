"""SecretsManager - main orchestrator for secrets management."""

import asyncio
import logging
import os
import random
import threading
from datetime import UTC, datetime
from typing import Any

from .cache import DiskCache
from .exceptions import (
    ProviderError,
    ProviderNotConfiguredError,
    SecretNotFoundError,
    SecretsError,
)
from .providers.base import SecretProvider
from .providers.file import FileProvider
from .types import (
    AWSConfig,
    CacheConfig,
    OpenBaoConfig,
    ProviderType,
    RotationCallback,
    RotationEvent,
    SecretValue,
    SourceConfig,
)

logger = logging.getLogger(__name__)


class SecretsManager:
    """Main secrets manager orchestrating providers, caching, and refresh.

    Features:
    - Multi-provider support (file, OpenBao/Vault, AWS)
    - Two-tier caching (memory + disk)
    - Stale cache fallback when providers unavailable
    - Background refresh with jitter
    - Rotation detection and callbacks
    - Backward compatible with file paths

    Usage:
        # Simple file-based usage
        secrets = SecretsManager()
        cert = await secrets.get("/etc/ssl/cert.pem")

        # With configuration
        secrets = SecretsManager.from_config({
            "openbao": {"address": "https://vault:8200", ...},
            "sources": {"api_key": {"provider": "openbao", "path": "secret/data/myapp", "key": "api_key"}}
        })
        api_key = await secrets.get("api_key")
    """

    # Class-level memory cache (like PostgresConfigLoader)
    _memory_cache: dict[str, SecretValue] = {}
    _memory_cache_lock = threading.Lock()

    def __init__(
        self,
        providers: dict[str, SecretProvider] | None = None,
        sources: dict[str, SourceConfig] | None = None,
        cache_config: CacheConfig | None = None,
        cache: CacheConfig | None = None,  # Alias for cache_config
    ) -> None:
        """Initialize SecretsManager.

        Args:
            providers: Map of provider name to provider instance.
            sources: Map of secret name to source configuration.
            cache_config: Cache configuration.
            cache: Alias for cache_config (for convenience).
        """
        # Default to file provider
        self._providers: dict[str, SecretProvider] = providers.copy() if providers else {}
        if "file" not in self._providers:
            self._providers["file"] = FileProvider()

        self._sources = sources or {}
        self._cache = DiskCache(cache or cache_config or CacheConfig())
        self._rotation_callbacks: list[tuple[RotationCallback, list[str] | None]] = []
        self._refresh_task: asyncio.Task | None = None
        self._refresh_stop_event: asyncio.Event | None = None

    @property
    def _file_provider(self) -> SecretProvider:
        """File provider for backward compatibility."""
        return self._providers["file"]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SecretsManager":
        """Create manager from configuration dictionary.

        Config structure matches docs/SECRETS.md.

        Args:
            config: Configuration dictionary with optional keys:
                - openbao: OpenBao/Vault provider config
                - aws: AWS Secrets Manager config
                - cache: Cache configuration
                - sources: Named secret sources

        Returns:
            Configured SecretsManager instance.
        """
        providers: dict[str, SecretProvider] = {"file": FileProvider()}

        # OpenBao/Vault provider
        if "openbao" in config:
            try:
                from .providers.openbao import OpenBaoProvider

                ob_config = cls._parse_openbao_config(config["openbao"])
                providers["openbao"] = OpenBaoProvider(ob_config)
            except ImportError:
                logger.warning("OpenBao provider not available. Install with: pip install hyperi-pylib[secrets-vault]")

        # AWS provider
        if "aws" in config:
            try:
                from .providers.aws import AWSProvider

                aws_config = cls._parse_aws_config(config["aws"])
                providers["aws"] = AWSProvider(aws_config)
            except ImportError:
                logger.warning("AWS provider not available. Install with: pip install hyperi-pylib[secrets-aws]")

        # Parse sources
        sources: dict[str, SourceConfig] = {}
        for name, source_cfg in config.get("sources", {}).items():
            provider_type = source_cfg.get("provider", "file")
            sources[name] = SourceConfig(
                provider=ProviderType(provider_type),
                path=source_cfg.get("path"),
                secret_id=source_cfg.get("secret_id"),
                key=source_cfg.get("key"),
            )

        # Parse cache config
        cache_cfg = config.get("cache", {})
        encryption_key = cls._get_encryption_key(cache_cfg)
        cache_config = CacheConfig(
            enabled=cache_cfg.get("enabled", True),
            directory=cache_cfg.get("directory") or os.environ.get("HYPERI_SECRETS_CACHE_DIR"),
            ttl_secs=cache_cfg.get("ttl_secs", int(os.environ.get("HYPERI_SECRETS_CACHE_TTL", "3600"))),
            stale_grace_secs=cache_cfg.get("stale_grace_secs", 86400),
            refresh_interval_secs=cache_cfg.get("refresh_interval_secs", 1800),
            refresh_jitter_secs=cache_cfg.get("refresh_jitter_secs", 300),
            encryption_key=encryption_key,
        )

        return cls(providers=providers, sources=sources, cache_config=cache_config)

    @staticmethod
    def _get_encryption_key(cache_cfg: dict) -> bytes | None:
        """Get encryption key from config or environment."""
        key = cache_cfg.get("encryption_key") or os.environ.get("HYPERI_SECRETS_CACHE_KEY")
        if key:
            return key.encode("utf-8") if isinstance(key, str) else key
        return None

    @staticmethod
    def _parse_openbao_config(cfg: dict) -> OpenBaoConfig:
        """Parse OpenBao config with env var fallbacks."""
        auth = cfg.get("auth", {})
        return OpenBaoConfig(
            address=cfg.get("address") or os.environ.get("VAULT_ADDR", ""),
            auth_method=auth.get("method", "token"),
            token=auth.get("token") or os.environ.get("VAULT_TOKEN"),
            role_id=auth.get("role_id") or os.environ.get("VAULT_ROLE_ID"),
            secret_id=auth.get("secret_id") or os.environ.get("VAULT_SECRET_ID"),
            role=auth.get("role"),
            token_path=auth.get("token_path", "/var/run/secrets/kubernetes.io/serviceaccount/token"),
            mount=auth.get("mount"),
            namespace=cfg.get("namespace") or os.environ.get("VAULT_NAMESPACE"),
            ca_cert=cfg.get("ca_cert"),
            skip_verify=cfg.get("skip_verify", False),
            timeout_secs=cfg.get("timeout_secs", 30),
        )

    @staticmethod
    def _parse_aws_config(cfg: dict) -> AWSConfig:
        """Parse AWS config with env var fallbacks."""
        return AWSConfig(
            region=cfg.get("region") or os.environ.get("AWS_REGION", "us-east-1"),
            access_key_id=cfg.get("access_key_id"),
            secret_access_key=cfg.get("secret_access_key"),
            endpoint_url=cfg.get("endpoint_url"),
            timeout_secs=cfg.get("timeout_secs", 30),
        )

    async def get(
        self,
        name_or_path: str,
        key: str | None = None,
        provider: str | None = None,
    ) -> SecretValue:
        """Get secret by name or file path.

        If name matches a configured source, uses that source.
        Otherwise treats as file path (backwards compatible).

        Args:
            name_or_path: Secret name or file path.
            key: Optional key to extract from JSON secret.
            provider: Optional provider override.

        Returns:
            SecretValue with data and metadata.

        Raises:
            SecretNotFoundError: Secret not found.
            ProviderError: Provider communication failed.
            ProviderNotConfiguredError: Provider not configured.
        """
        # Provider override takes precedence
        if provider:
            return await self._get_from_provider(provider, name_or_path, key)

        # Check if it's a named source
        if name_or_path in self._sources:
            return await self._get_by_source(name_or_path)

        # Treat as file path (backwards compatible)
        return await self._get_from_provider("file", name_or_path, key)

    def get_sync(
        self,
        name_or_path: str,
        key: str | None = None,
        provider: str | None = None,
    ) -> SecretValue:
        """Get secret synchronously.

        Args:
            name_or_path: Secret name or file path.
            key: Optional key to extract from JSON secret.
            provider: Optional provider override.

        Returns:
            SecretValue with data and metadata.
        """
        # Provider override takes precedence
        if provider:
            return self._get_from_provider_sync(provider, name_or_path, key)

        # Check if it's a named source
        if name_or_path in self._sources:
            return self._get_by_source_sync(name_or_path)

        # Treat as file path
        return self._get_from_provider_sync("file", name_or_path, key)

    async def get_string(self, name_or_path: str, encoding: str = "utf-8") -> str:
        """Get secret as string.

        Args:
            name_or_path: Secret name or file path.
            encoding: String encoding (default: utf-8).

        Returns:
            Secret data as string.
        """
        value = await self.get(name_or_path)
        return value.decode(encoding)

    def get_string_sync(self, name_or_path: str, encoding: str = "utf-8") -> str:
        """Get secret as string synchronously.

        Args:
            name_or_path: Secret name or file path.
            encoding: String encoding (default: utf-8).

        Returns:
            Secret data as string.
        """
        value = self.get_sync(name_or_path)
        return value.decode(encoding)

    async def _get_by_source(self, name: str) -> SecretValue:
        """Get secret using configured source."""
        source = self._sources[name]
        provider_name = source.provider.value
        path = source.path or source.secret_id

        if not path:
            raise SecretsError(f"source '{name}' has no path or secret_id")

        return await self._get_from_provider(provider_name, path, source.key)

    def _get_by_source_sync(self, name: str) -> SecretValue:
        """Get secret using configured source (sync)."""
        source = self._sources[name]
        provider_name = source.provider.value
        path = source.path or source.secret_id

        if not path:
            raise SecretsError(f"source '{name}' has no path or secret_id")

        return self._get_from_provider_sync(provider_name, path, source.key)

    async def _get_from_provider(
        self,
        provider_name: str,
        path: str,
        key: str | None,
    ) -> SecretValue:
        """Fetch from provider with caching and fallback."""
        cache_key = f"{provider_name}:{path}:{key or ''}"

        # Check memory cache
        with self._memory_cache_lock:
            if cache_key in self._memory_cache:
                cached = self._memory_cache[cache_key]
                if not cached.is_expired(self._cache.config.ttl_secs):
                    logger.debug("Memory cache hit", extra={"key": cache_key})
                    return cached

        # Check disk cache
        cached = self._cache.get(cache_key)
        if cached and not cached.is_expired(self._cache.config.ttl_secs):
            with self._memory_cache_lock:
                self._memory_cache[cache_key] = cached
            logger.debug("Disk cache hit", extra={"key": cache_key})
            return cached

        # Fetch from provider
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ProviderNotConfiguredError(provider_name)

        try:
            value = await provider.get_async(path, key)

            # Update caches
            with self._memory_cache_lock:
                old_value = self._memory_cache.get(cache_key)
                self._memory_cache[cache_key] = value

            self._cache.set(cache_key, value)

            # Check for rotation
            if old_value and old_value.version != value.version:
                self._emit_rotation(cache_key, old_value.version, value.version)

            logger.debug("Provider fetch", extra={"key": cache_key, "provider": provider_name})
            return value

        except (SecretNotFoundError, ProviderError) as e:
            # Try stale cache fallback
            if cached and cached.is_within_grace(
                self._cache.config.ttl_secs,
                self._cache.config.stale_grace_secs,
            ):
                logger.warning(
                    "Provider failed, using stale cache",
                    extra={"provider": provider_name, "error": str(e), "key": cache_key},
                )
                return cached
            raise

    def _get_from_provider_sync(
        self,
        provider_name: str,
        path: str,
        key: str | None,
    ) -> SecretValue:
        """Fetch from provider with caching and fallback (sync)."""
        cache_key = f"{provider_name}:{path}:{key or ''}"

        # Check memory cache
        with self._memory_cache_lock:
            if cache_key in self._memory_cache:
                cached = self._memory_cache[cache_key]
                if not cached.is_expired(self._cache.config.ttl_secs):
                    return cached

        # Check disk cache
        cached = self._cache.get(cache_key)
        if cached and not cached.is_expired(self._cache.config.ttl_secs):
            with self._memory_cache_lock:
                self._memory_cache[cache_key] = cached
            return cached

        # Fetch from provider
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ProviderNotConfiguredError(provider_name)

        try:
            value = provider.get_sync(path, key)

            # Update caches
            with self._memory_cache_lock:
                old_value = self._memory_cache.get(cache_key)
                self._memory_cache[cache_key] = value

            self._cache.set(cache_key, value)

            # Check for rotation
            if old_value and old_value.version != value.version:
                self._emit_rotation(cache_key, old_value.version, value.version)

            return value

        except (SecretNotFoundError, ProviderError) as e:
            # Try stale cache fallback
            if cached and cached.is_within_grace(
                self._cache.config.ttl_secs,
                self._cache.config.stale_grace_secs,
            ):
                logger.warning(
                    "Provider failed, using stale cache",
                    extra={"provider": provider_name, "error": str(e)},
                )
                return cached
            raise

    def on_rotation(
        self,
        callback: RotationCallback,
        names: list[str] | None = None,
    ) -> None:
        """Register rotation callback.

        Args:
            callback: Function to call when secret rotates.
            names: Optional list of secret names to watch. None = all secrets.
        """
        self._rotation_callbacks.append((callback, names))

    def _emit_rotation(self, name: str, old_version: str | None, new_version: str) -> None:
        """Emit rotation event to callbacks."""
        event = RotationEvent(
            name=name,
            old_version=old_version,
            new_version=new_version,
            rotated_at=datetime.now(UTC),
        )

        for callback, names in self._rotation_callbacks:
            if names is None or name in names:
                try:
                    callback(event)
                except Exception as e:
                    logger.error("Rotation callback failed", extra={"error": str(e)})

    async def start_refresh(self) -> None:
        """Start background refresh task."""
        if self._refresh_task is not None:
            return

        self._refresh_stop_event = asyncio.Event()
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("Background refresh started")

    async def stop_refresh(self) -> None:
        """Stop background refresh task."""
        if self._refresh_task is None:
            return

        self._refresh_stop_event.set()
        await self._refresh_task
        self._refresh_task = None
        logger.info("Background refresh stopped")

    async def _refresh_loop(self) -> None:
        """Background refresh loop."""
        cfg = self._cache.config

        while not self._refresh_stop_event.is_set():
            # Add jitter
            jitter = random.uniform(0, cfg.refresh_jitter_secs)
            interval = cfg.refresh_interval_secs + jitter

            try:
                await asyncio.wait_for(
                    self._refresh_stop_event.wait(),
                    timeout=interval,
                )
                break  # Stop event was set
            except TimeoutError:
                pass  # Normal timeout, do refresh

            # Refresh all cached secrets
            await self._refresh_all()

    async def _refresh_all(self) -> None:
        """Refresh all cached secrets."""
        with self._memory_cache_lock:
            keys = list(self._memory_cache.keys())

        for cache_key in keys:
            try:
                parts = cache_key.split(":", 2)
                if len(parts) >= 2:
                    provider_name, path = parts[0], parts[1]
                    key = parts[2] if len(parts) > 2 and parts[2] else None
                    await self._get_from_provider(provider_name, path, key)
            except Exception as e:
                logger.warning("Refresh failed", extra={"key": cache_key, "error": str(e)})

    async def health_check(self) -> dict[str, bool]:
        """Check health of all configured providers.

        Returns:
            Map of provider name to health status.
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check_async()
            except Exception:
                results[name] = False
        return results

    def health_check_sync(self) -> dict[str, bool]:
        """Check health of all configured providers (sync).

        Returns:
            Map of provider name to health status.
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = provider.health_check_sync()
            except Exception:
                results[name] = False
        return results

    def clear_cache(self) -> None:
        """Clear all cached secrets (memory and disk)."""
        with self._memory_cache_lock:
            self._memory_cache.clear()
        self._cache.clear()
        logger.info("Cache cleared")

    @classmethod
    def clear_memory_cache(cls) -> None:
        """Clear class-level memory cache."""
        with cls._memory_cache_lock:
            cls._memory_cache.clear()

    async def close(self) -> None:
        """Close manager and release resources."""
        await self.stop_refresh()
        for provider in self._providers.values():
            await provider.close()


__all__ = ["SecretsManager"]
