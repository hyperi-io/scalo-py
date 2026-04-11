"""SecretsManager - main orchestrator for secrets management."""

from __future__ import annotations

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
    VersioningNotSupportedError,
)
from .providers.base import SecretProvider, VersionedProvider
from .providers.file import FileProvider
from .types import (
    AnsibleVaultConfig,
    AWSConfig,
    AzureConfig,
    CacheConfig,
    GCPConfig,
    OpenBaoConfig,
    ProviderType,
    RotationCallback,
    RotationEvent,
    SecretFilter,
    SecretMetadata,
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
        env_prefix: str | None = None,
    ) -> None:
        """Initialize SecretsManager.

        Args:
            providers: Map of provider name to provider instance.
            sources: Map of secret name to source configuration.
            cache_config: Cache configuration.
            cache: Alias for cache_config (for convenience).
            env_prefix: Optional prefix for automatic ENV fallback lookup.
                When a provider fetch fails and no explicit env_fallback is set on
                the source, the manager looks up {PREFIX}_{NAME.upper()} in the
                environment. E.g. prefix="DFE", name="fred_key" → DFE_FRED_KEY.
                Without a prefix it looks up NAME.upper() directly.
        """
        # Default to file provider
        self._providers: dict[str, SecretProvider] = providers.copy() if providers else {}
        if "file" not in self._providers:
            self._providers["file"] = FileProvider()

        self._sources = sources or {}
        self._cache = DiskCache(cache or cache_config or CacheConfig())
        self._env_prefix = env_prefix.rstrip("_") if env_prefix else None
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

        # GCP provider
        if "gcp" in config:
            try:
                from .providers.gcp import GCPProvider

                gcp_config = cls._parse_gcp_config(config["gcp"])
                providers["gcp"] = GCPProvider(gcp_config)
            except ImportError:
                logger.warning("GCP provider not available. Install with: pip install hyperi-pylib[secrets-gcp]")

        # Azure provider
        if "azure" in config:
            try:
                from .providers.azure import AzureProvider

                azure_config = cls._parse_azure_config(config["azure"])
                providers["azure"] = AzureProvider(azure_config)
            except ImportError:
                logger.warning("Azure provider not available. Install with: pip install hyperi-pylib[secrets-azure]")

        # Ansible Vault provider
        if "ansible_vault" in config:
            try:
                from .providers.ansible_vault import AnsibleVaultProvider

                av_config = cls._parse_ansible_vault_config(config["ansible_vault"])
                providers["ansible_vault"] = AnsibleVaultProvider(av_config)
            except ImportError:
                logger.warning(
                    "Ansible Vault provider not available. Install with: pip install hyperi-pylib[secrets-ansible-vault]"
                )

        # Parse sources
        sources: dict[str, SourceConfig] = {}
        for name, source_cfg in config.get("sources", {}).items():
            provider_type = source_cfg.get("provider", "file")
            sources[name] = SourceConfig(
                provider=ProviderType(provider_type),
                path=source_cfg.get("path"),
                secret_id=source_cfg.get("secret_id"),
                key=source_cfg.get("key"),
                env_fallback=source_cfg.get("env_fallback"),
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

        env_prefix = config.get("env_prefix") or os.environ.get("HYPERI_SECRETS_ENV_PREFIX")
        return cls(providers=providers, sources=sources, cache_config=cache_config, env_prefix=env_prefix)

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

    @staticmethod
    def _parse_gcp_config(cfg: dict) -> GCPConfig:
        """Parse GCP config with env var fallbacks."""
        return GCPConfig(
            project_id=cfg.get("project_id") or os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            credentials_file=cfg.get("credentials_file") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
            timeout_secs=cfg.get("timeout_secs", 30),
        )

    @staticmethod
    def _parse_azure_config(cfg: dict) -> AzureConfig:
        """Parse Azure config with env var fallbacks."""
        return AzureConfig(
            vault_url=cfg.get("vault_url") or os.environ.get("AZURE_VAULT_URL", ""),
            tenant_id=cfg.get("tenant_id") or os.environ.get("AZURE_TENANT_ID"),
            client_id=cfg.get("client_id") or os.environ.get("AZURE_CLIENT_ID"),
            client_secret=cfg.get("client_secret") or os.environ.get("AZURE_CLIENT_SECRET"),
            timeout_secs=cfg.get("timeout_secs", 30),
        )

    @staticmethod
    def _parse_ansible_vault_config(cfg: dict) -> AnsibleVaultConfig:
        """Parse Ansible Vault config with env var fallbacks."""
        return AnsibleVaultConfig(
            password=cfg.get("password")
            or os.environ.get("ANSIBLE_VAULT_PASSWORD")
            or os.environ.get("ANSIBLE_VAULT_PASS"),
            password_file=cfg.get("password_file"),
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

    # -------------------------------------------------------------------------
    # List
    # -------------------------------------------------------------------------

    async def list(
        self,
        filter: SecretFilter | None = None,
        provider: str | None = None,
    ) -> list[str]:
        """List secret names/paths matching filter.

        Args:
            filter: Optional filter (prefix, tags, pattern).
            provider: Provider name. Defaults to "file".

        Returns:
            List of secret names/paths.

        Raises:
            ProviderNotConfiguredError: Provider not configured.
            ProviderError: Provider communication failed.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return await p.list_async(filter)

    def list_sync(
        self,
        filter: SecretFilter | None = None,
        provider: str | None = None,
    ) -> list[str]:
        """List secret names/paths matching filter (sync)."""
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return p.list_sync(filter)

    # -------------------------------------------------------------------------
    # Metadata
    # -------------------------------------------------------------------------

    async def get_metadata(
        self,
        path: str,
        provider: str | None = None,
    ) -> SecretMetadata:
        """Get secret metadata without fetching the value.

        Args:
            path: Secret path/name.
            provider: Provider name. Defaults to "file".

        Returns:
            SecretMetadata with available fields populated.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderNotConfiguredError: Provider not configured.
            ProviderError: Provider communication failed.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return await p.get_metadata_async(path)

    def get_metadata_sync(
        self,
        path: str,
        provider: str | None = None,
    ) -> SecretMetadata:
        """Get secret metadata without fetching the value (sync)."""
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return p.get_metadata_sync(path)

    # -------------------------------------------------------------------------
    # Create / Update / Delete
    # -------------------------------------------------------------------------

    async def create(
        self,
        path: str,
        value: bytes,
        tags: dict[str, str] | None = None,
        provider: str | None = None,
    ) -> SecretMetadata:
        """Create a new secret.

        Args:
            path: Secret path/name.
            value: Secret value as bytes.
            tags: Optional tags/labels. Ignored by file-based providers.
            provider: Provider name. Defaults to "file".

        Returns:
            SecretMetadata of the created secret.

        Raises:
            SecretAlreadyExistsError: Secret already exists.
            SecretPermissionError: Caller lacks write permission.
            ProviderNotConfiguredError: Provider not configured.
            ProviderError: Write failed.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return await p.create_async(path, value, tags)

    def create_sync(
        self,
        path: str,
        value: bytes,
        tags: dict[str, str] | None = None,
        provider: str | None = None,
    ) -> SecretMetadata:
        """Create a new secret (sync)."""
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return p.create_sync(path, value, tags)

    async def update(
        self,
        path: str,
        value: bytes,
        provider: str | None = None,
    ) -> SecretMetadata:
        """Update an existing secret's value.

        Args:
            path: Secret path/name.
            value: New secret value as bytes.
            provider: Provider name. Defaults to "file".

        Returns:
            SecretMetadata of the updated secret.

        Raises:
            SecretNotFoundError: Secret does not exist.
            SecretPermissionError: Caller lacks write permission.
            ProviderNotConfiguredError: Provider not configured.
            ProviderError: Write failed.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return await p.update_async(path, value)

    def update_sync(
        self,
        path: str,
        value: bytes,
        provider: str | None = None,
    ) -> SecretMetadata:
        """Update an existing secret's value (sync)."""
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        return p.update_sync(path, value)

    async def delete(
        self,
        path: str,
        provider: str | None = None,
    ) -> None:
        """Delete a secret.

        Args:
            path: Secret path/name.
            provider: Provider name. Defaults to "file".

        Raises:
            SecretNotFoundError: Secret does not exist.
            SecretPermissionError: Caller lacks write permission.
            ProviderNotConfiguredError: Provider not configured.
            ProviderError: Delete failed.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        await p.delete_async(path)

    def delete_sync(
        self,
        path: str,
        provider: str | None = None,
    ) -> None:
        """Delete a secret (sync)."""
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        p.delete_sync(path)

    # -------------------------------------------------------------------------
    # Batch get
    # -------------------------------------------------------------------------

    async def batch_get(
        self,
        paths: list[str],
        provider: str | None = None,
    ) -> dict[str, SecretValue]:
        """Fetch multiple secrets concurrently.

        Uses native batch API for AWS. Falls back to asyncio.gather for all
        other providers.

        Args:
            paths: List of secret paths/names to fetch.
            provider: Provider name. Defaults to "file".

        Returns:
            Dict mapping each path to its SecretValue. Paths that fail are
            omitted and a warning is logged rather than raising.

        Raises:
            ProviderNotConfiguredError: Provider not configured.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)

        # AWS has a native batch API — delegate to provider if available.
        if provider_name == "aws" and hasattr(p, "batch_get_async"):
            return await p.batch_get_async(paths)  # type: ignore[attr-defined]

        # Generic: concurrent gather with per-item error isolation.
        async def _fetch(path: str) -> tuple[str, SecretValue | None]:
            try:
                return path, await p.get_async(path)
            except (SecretNotFoundError, ProviderError) as e:
                logger.warning("batch_get: failed to fetch secret", extra={"path": path, "error": str(e)})
                return path, None

        results_list = await asyncio.gather(*[_fetch(path) for path in paths])
        return {k: v for k, v in results_list if v is not None}

    def batch_get_sync(
        self,
        paths: list[str],
        provider: str | None = None,
    ) -> dict[str, SecretValue]:
        """Fetch multiple secrets (sync). Errors are logged and omitted.

        Args:
            paths: List of secret paths/names to fetch.
            provider: Provider name. Defaults to "file".

        Returns:
            Dict mapping each path to its SecretValue.

        Raises:
            ProviderNotConfiguredError: Provider not configured.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)

        results: dict[str, SecretValue] = {}
        for path in paths:
            try:
                results[path] = p.get_sync(path)
            except (SecretNotFoundError, ProviderError) as e:
                logger.warning("batch_get_sync: failed to fetch secret", extra={"path": path, "error": str(e)})
        return results

    # -------------------------------------------------------------------------
    # Versioning (VersionedProvider only)
    # -------------------------------------------------------------------------

    async def get_version(
        self,
        path: str,
        version: str,
        key: str | None = None,
        provider: str | None = None,
    ) -> SecretValue:
        """Fetch a specific version of a secret.

        Only available on versioned providers (OpenBao, AWS, GCP, Azure).

        Args:
            path: Secret path.
            version: Version identifier (provider-specific format).
            key: Optional key to extract from structured secret.
            provider: Provider name. Defaults to "file".

        Returns:
            SecretValue for the requested version.

        Raises:
            VersioningNotSupportedError: Provider does not support versioning.
            SecretVersionNotFoundError: Version does not exist.
            SecretNotFoundError: Secret does not exist.
            ProviderNotConfiguredError: Provider not configured.
            ProviderError: Provider communication failed.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        if not isinstance(p, VersionedProvider):
            raise VersioningNotSupportedError(provider_name)
        return await p.get_version_async(path, version, key)

    def get_version_sync(
        self,
        path: str,
        version: str,
        key: str | None = None,
        provider: str | None = None,
    ) -> SecretValue:
        """Fetch a specific version of a secret (sync)."""
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        if not isinstance(p, VersionedProvider):
            raise VersioningNotSupportedError(provider_name)
        return p.get_version_sync(path, version, key)

    async def list_versions(
        self,
        path: str,
        provider: str | None = None,
    ) -> list[SecretMetadata]:
        """List all versions of a secret, newest first.

        Only available on versioned providers (OpenBao, AWS, GCP, Azure).

        Args:
            path: Secret path.
            provider: Provider name. Defaults to "file".

        Returns:
            List of SecretMetadata, one per version.

        Raises:
            VersioningNotSupportedError: Provider does not support versioning.
            SecretNotFoundError: Secret does not exist.
            ProviderNotConfiguredError: Provider not configured.
            ProviderError: Provider communication failed.
        """
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        if not isinstance(p, VersionedProvider):
            raise VersioningNotSupportedError(provider_name)
        return await p.list_versions_async(path)

    def list_versions_sync(
        self,
        path: str,
        provider: str | None = None,
    ) -> list[SecretMetadata]:
        """List all versions of a secret, newest first (sync)."""
        provider_name = provider or "file"
        p = self._get_provider(provider_name)
        if not isinstance(p, VersionedProvider):
            raise VersioningNotSupportedError(provider_name)
        return p.list_versions_sync(path)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_provider(self, provider_name: str) -> SecretProvider:
        """Return named provider or raise ProviderNotConfiguredError."""
        p = self._providers.get(provider_name)
        if p is None:
            raise ProviderNotConfiguredError(provider_name)
        return p

    def _env_fallback_var(self, name: str, source: SourceConfig) -> str | None:
        """Compute the ENV var name to use as fallback for a source.

        Priority:
        1. source.env_fallback (explicit override)
        2. {env_prefix}_{NAME.upper()} if manager has env_prefix
        3. NAME.upper() (auto, no prefix)
        """
        if source.env_fallback:
            return source.env_fallback
        upper = name.upper()
        if self._env_prefix:
            return f"{self._env_prefix}_{upper}"
        return upper

    def _resolve_env_fallback(self, name: str, source: SourceConfig) -> SecretValue | None:
        """Look up ENV fallback value; return SecretValue or None if not set."""
        env_var = self._env_fallback_var(name, source)
        if env_var is None:
            return None
        env_value = os.environ.get(env_var)
        if env_value is None:
            return None
        logger.warning(
            "Provider unavailable, using ENV fallback",
            extra={"source": name, "env_var": env_var},
        )
        return SecretValue(data=env_value.encode("utf-8"), fetched_at=datetime.now(UTC), source="env")

    async def _get_by_source(self, name: str) -> SecretValue:
        """Get secret using configured source, with ENV fallback on failure."""
        source = self._sources[name]
        provider_name = source.provider.value
        path = source.path or source.secret_id

        if not path:
            raise SecretsError(f"source '{name}' has no path or secret_id")

        try:
            return await self._get_from_provider(provider_name, path, source.key)
        except (ProviderError, ProviderNotConfiguredError, SecretNotFoundError):
            fallback = self._resolve_env_fallback(name, source)
            if fallback is not None:
                return fallback
            raise

    def _get_by_source_sync(self, name: str) -> SecretValue:
        """Get secret using configured source, with ENV fallback on failure (sync)."""
        source = self._sources[name]
        provider_name = source.provider.value
        path = source.path or source.secret_id

        if not path:
            raise SecretsError(f"source '{name}' has no path or secret_id")

        try:
            return self._get_from_provider_sync(provider_name, path, source.key)
        except (ProviderError, ProviderNotConfiguredError, SecretNotFoundError):
            fallback = self._resolve_env_fallback(name, source)
            if fallback is not None:
                return fallback
            raise

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


__all__ = ["SecretsManager", "SecretFilter", "SecretMetadata"]
