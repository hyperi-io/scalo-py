# Project:   hyperi-pylib
# File:      secrets/providers/azure.py
# Purpose:   Azure Key Vault secrets provider
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Azure Key Vault secrets provider."""

import json
import logging
from datetime import UTC, datetime

from ..exceptions import (
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
    SecretVersionNotFoundError,
)
from ..types import AzureConfig, SecretFilter, SecretMetadata, SecretValue
from .base import VersionedProvider

logger = logging.getLogger(__name__)

try:
    from azure.core.exceptions import (
        ClientAuthenticationError,
        HttpResponseError,
        ResourceExistsError,
        ResourceNotFoundError,
    )
    from azure.identity import ClientSecretCredential, DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    ResourceNotFoundError = Exception  # type: ignore[assignment,misc]
    ResourceExistsError = Exception  # type: ignore[assignment,misc]
    HttpResponseError = Exception  # type: ignore[assignment,misc]
    ClientAuthenticationError = Exception  # type: ignore[assignment,misc]
    DefaultAzureCredential = None  # type: ignore[assignment]
    ClientSecretCredential = None  # type: ignore[assignment]
    SecretClient = None  # type: ignore[assignment]

try:
    from azure.identity.aio import ClientSecretCredential as AsyncClientSecretCredential
    from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
    from azure.keyvault.secrets.aio import SecretClient as AsyncSecretClient

    AZURE_ASYNC_AVAILABLE = True
except ImportError:
    AZURE_ASYNC_AVAILABLE = False
    AsyncDefaultAzureCredential = None  # type: ignore[assignment]
    AsyncClientSecretCredential = None  # type: ignore[assignment]
    AsyncSecretClient = None  # type: ignore[assignment]


class AzureProvider(VersionedProvider):
    """Azure Key Vault secrets provider.

    Uses azure-keyvault-secrets with DefaultAzureCredential (managed identity,
    environment variables, Azure CLI, etc.) or explicit ClientSecretCredential.

    Features:
    - Native async via azure.keyvault.secrets.aio
    - JSON key extraction
    - Version tracking via secret properties
    - DefaultAzureCredential chain (managed identity, env, CLI)
    """

    def __init__(self, config: AzureConfig) -> None:
        """Initialise Azure Key Vault provider.

        Args:
            config: Azure configuration.

        Raises:
            ProviderNotAvailableError: azure-keyvault-secrets not installed.
        """
        if not AZURE_AVAILABLE:
            from ..exceptions import ProviderNotAvailableError

            raise ProviderNotAvailableError(
                "azure",
                "azure-keyvault-secrets",
                "pip install hyperi-pylib[secrets-azure]",
            )
        self._config = config
        self._sync_client = None

    @property
    def name(self) -> str:
        """Provider name."""
        return "azure"

    def _sync_credential(self):
        """Return sync credential — explicit service principal or DefaultAzureCredential."""
        if self._config.tenant_id and self._config.client_id and self._config.client_secret:
            return ClientSecretCredential(
                tenant_id=self._config.tenant_id,
                client_id=self._config.client_id,
                client_secret=self._config.client_secret,
            )
        return DefaultAzureCredential()

    def _get_sync_client(self):
        """Get or create sync Key Vault client."""
        if self._sync_client is None:
            self._sync_client = SecretClient(
                vault_url=self._config.vault_url,
                credential=self._sync_credential(),
            )
        return self._sync_client

    def _async_credential(self):
        """Return async credential — explicit service principal or DefaultAzureCredential."""
        if self._config.tenant_id and self._config.client_id and self._config.client_secret:
            return AsyncClientSecretCredential(
                tenant_id=self._config.tenant_id,
                client_id=self._config.client_id,
                client_secret=self._config.client_secret,
            )
        return AsyncDefaultAzureCredential()

    def _parse_value(self, secret_value: str, path: str, key: str | None) -> bytes:
        """Extract key from JSON secret value, or return full value as bytes."""
        if key is None:
            return secret_value.encode("utf-8")
        try:
            parsed = json.loads(secret_value)
        except json.JSONDecodeError as e:
            raise ProviderError(self.name, f"invalid JSON in {path}: {e}")
        if key not in parsed:
            raise SecretNotFoundError(f"{path}[{key}]", self.name)
        value = parsed[key]
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value).encode("utf-8")

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from Azure Key Vault.

        Args:
            path: Secret name in the vault.
            key: Optional key to extract from JSON secret.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: Azure request failed.
        """
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.get_sync, path, key)

        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                secret = await client.get_secret(path)
                data = self._parse_value(secret.value, path, key)
                version = secret.properties.version
                return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except (SecretNotFoundError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"request failed: {e}")

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from Azure Key Vault (sync).

        Args:
            path: Secret name in the vault.
            key: Optional key to extract from JSON secret.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: Azure request failed.
        """
        try:
            client = self._get_sync_client()
            secret = client.get_secret(path)
            data = self._parse_value(secret.value, path, key)
            version = secret.properties.version
            return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except (SecretNotFoundError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"request failed: {e}")

    async def health_check_async(self) -> bool:
        """Check if Azure Key Vault is reachable."""
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.health_check_sync)

        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                async for _ in client.list_properties_of_secrets(max_page_size=1):
                    break
            return True
        except Exception:
            return False

    def health_check_sync(self) -> bool:
        """Check if Azure Key Vault is reachable (sync)."""
        try:
            client = self._get_sync_client()
            for _ in client.list_properties_of_secrets(max_page_size=1):
                break
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close sync client and release credentials."""
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    # --- Helpers for Tier 1+2 ---

    @staticmethod
    def _decode_value_for_storage(value: bytes) -> str:
        """Azure Key Vault stores secret values as UTF-8 strings.

        For binary values, callers must pre-encode (e.g. base64) before passing
        bytes; we don't transparently wrap because there's no portable convention
        across providers. Raise ``ProviderError`` for non-utf-8 bytes so the
        failure is explicit.
        """
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as e:
            from ..exceptions import ProviderError

            raise ProviderError("azure", f"value is not valid utf-8 (Azure stores strings only): {e}")

    def _azure_hint(self) -> str:
        """Permission hint for Azure per HyperI spec."""
        return "check Key Vault access policy or RBAC role assignment"

    def _props_to_metadata(self, props, fallback_name: str | None = None) -> SecretMetadata:
        """Convert SecretProperties (from list_properties_of_secrets / get_secret().properties) to SecretMetadata."""
        return SecretMetadata(
            name=props.name or fallback_name or "",
            created_at=props.created_on,
            updated_at=props.updated_on,
            expires_at=props.expires_on,
            version=props.version,
            version_count=None,
            tags=dict(props.tags) if props.tags else None,
            source=self.name,
        )

    def _post_filter(self, names: list[str], filter: SecretFilter | None) -> list[str]:
        """Apply client-side prefix + fnmatch + tag filters (Azure has no server-side filter)."""
        import fnmatch

        if not filter:
            return sorted(names)
        if filter.prefix:
            names = [n for n in names if n.startswith(filter.prefix)]
        if filter.pattern:
            names = [n for n in names if fnmatch.fnmatch(n, filter.pattern)]
        return sorted(names)

    def _is_404(self, err: Exception) -> bool:
        """True if the exception represents an Azure 404 / ResourceNotFound."""
        if isinstance(err, ResourceNotFoundError):
            return True
        status = getattr(err, "status_code", None) or getattr(getattr(err, "response", None), "status_code", None)
        return status == 404

    def _is_403(self, err: Exception) -> bool:
        """True if the exception represents an Azure 403 / Forbidden."""
        status = getattr(err, "status_code", None) or getattr(getattr(err, "response", None), "status_code", None)
        return status == 403

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """List secret names. Azure has no server-side prefix or tag filter for list_properties_of_secrets;
        all filtering is client-side.
        """
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.list_sync, filter)

        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                names: list[str] = []
                async for props in client.list_properties_of_secrets():
                    if not props.name:
                        continue
                    if filter and filter.tags and not self._tags_match(props.tags or {}, filter.tags):
                        continue
                    names.append(props.name)
                return self._post_filter(names, filter)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "list", "*", self._azure_hint())
            raise ProviderError(self.name, f"list failed: {e}")
        except (SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"list failed: {e}")

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        try:
            client = self._get_sync_client()
            names: list[str] = []
            for props in client.list_properties_of_secrets():
                if not props.name:
                    continue
                if filter and filter.tags and not self._tags_match(props.tags or {}, filter.tags):
                    continue
                names.append(props.name)
            return self._post_filter(names, filter)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "list", "*", self._azure_hint())
            raise ProviderError(self.name, f"list failed: {e}")
        except (SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"list failed: {e}")

    @staticmethod
    def _tags_match(have: dict, want: dict) -> bool:
        """All requested tags must be present and equal."""
        return all(have.get(k) == v for k, v in want.items())

    # --- Metadata ---

    async def get_metadata_async(self, path: str) -> SecretMetadata:
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.get_metadata_sync, path)

        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                secret = await client.get_secret(path)
                return self._props_to_metadata(secret.properties, fallback_name=path)
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "get", path, self._azure_hint())
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")
        except (SecretNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")

    def get_metadata_sync(self, path: str) -> SecretMetadata:
        try:
            client = self._get_sync_client()
            secret = client.get_secret(path)
            return self._props_to_metadata(secret.properties, fallback_name=path)
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "get", path, self._azure_hint())
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")
        except (SecretNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")

    # --- Create ---

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create a new secret. Azure has no native "create-only" semantic; we pre-check via
        ``get_secret`` and raise ``SecretAlreadyExistsError`` if found. Read-then-write is
        race-tolerant, not race-safe.
        """
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.create_sync, path, value, tags)

        # Pre-check existence
        try:
            await self.get_metadata_async(path)
        except SecretNotFoundError:
            pass
        else:
            raise SecretAlreadyExistsError(path, self.name)

        return await self._set_secret_async(path, value, tags)

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        try:
            self.get_metadata_sync(path)
        except SecretNotFoundError:
            pass
        else:
            raise SecretAlreadyExistsError(path, self.name)

        return self._set_secret_sync(path, value, tags)

    async def _set_secret_async(self, path: str, value: bytes, tags: dict[str, str] | None) -> SecretMetadata:
        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                str_value = self._decode_value_for_storage(value)
                secret = await client.set_secret(path, str_value, tags=tags or None)
                return self._props_to_metadata(secret.properties, fallback_name=path)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "set", path, self._azure_hint())
            raise ProviderError(self.name, f"set {path} failed: {e}")
        except (ProviderError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"set {path} failed: {e}")

    def _set_secret_sync(self, path: str, value: bytes, tags: dict[str, str] | None) -> SecretMetadata:
        try:
            client = self._get_sync_client()
            str_value = self._decode_value_for_storage(value)
            secret = client.set_secret(path, str_value, tags=tags or None)
            return self._props_to_metadata(secret.properties, fallback_name=path)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "set", path, self._azure_hint())
            raise ProviderError(self.name, f"set {path} failed: {e}")
        except (ProviderError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"set {path} failed: {e}")

    # --- Update ---

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Update by writing a new version (Azure ``set_secret`` is upsert).

        Pre-checks existence to map "missing" cleanly to ``SecretNotFoundError``.
        """
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.update_sync, path, value)

        await self.get_metadata_async(path)  # raises SecretNotFoundError if absent
        return await self._set_secret_async(path, value, tags=None)

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        self.get_metadata_sync(path)
        return self._set_secret_sync(path, value, tags=None)

    # --- Delete ---

    async def delete_async(self, path: str) -> None:
        """Soft-delete a secret. Azure schedules deletion with the vault's recovery period."""
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.delete_sync, path)

        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                poller = await client.begin_delete_secret(path)
                await poller.wait()
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "delete", path, self._azure_hint())
            raise ProviderError(self.name, f"delete {path} failed: {e}")
        except (SecretNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"delete {path} failed: {e}")

    def delete_sync(self, path: str) -> None:
        try:
            client = self._get_sync_client()
            poller = client.begin_delete_secret(path)
            poller.wait()
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "delete", path, self._azure_hint())
            raise ProviderError(self.name, f"delete {path} failed: {e}")
        except (SecretNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"delete {path} failed: {e}")

    # --- Versioning ---

    async def get_version_async(self, path: str, version: str, key: str | None = None) -> SecretValue:
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.get_version_sync, path, version, key)

        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                secret = await client.get_secret(path, version=version)
                data = self._parse_value(secret.value, path, key)
                return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except ResourceNotFoundError:
            # Disambiguate: secret missing vs version missing
            try:
                await self.get_metadata_async(path)
            except SecretNotFoundError:
                raise SecretNotFoundError(path, self.name)
            raise SecretVersionNotFoundError(path, version, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "get", path, self._azure_hint())
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")
        except (SecretNotFoundError, SecretVersionNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")

    def get_version_sync(self, path: str, version: str, key: str | None = None) -> SecretValue:
        try:
            client = self._get_sync_client()
            secret = client.get_secret(path, version=version)
            data = self._parse_value(secret.value, path, key)
            return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except ResourceNotFoundError:
            try:
                self.get_metadata_sync(path)
            except SecretNotFoundError:
                raise SecretNotFoundError(path, self.name)
            raise SecretVersionNotFoundError(path, version, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "get", path, self._azure_hint())
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")
        except (SecretNotFoundError, SecretVersionNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")

    async def list_versions_async(self, path: str) -> list[SecretMetadata]:
        if not AZURE_ASYNC_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.list_versions_sync, path)

        try:
            credential = self._async_credential()
            async with credential, AsyncSecretClient(vault_url=self._config.vault_url, credential=credential) as client:
                items: list[SecretMetadata] = []
                async for props in client.list_properties_of_secret_versions(path):
                    items.append(self._props_to_metadata(props, fallback_name=path))
                if not items:
                    raise SecretNotFoundError(path, self.name)
                items.sort(key=lambda m: m.created_at or datetime.fromtimestamp(0, tz=UTC), reverse=True)
                return items
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "list", path, self._azure_hint())
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")
        except (SecretNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")

    def list_versions_sync(self, path: str) -> list[SecretMetadata]:
        try:
            client = self._get_sync_client()
            items: list[SecretMetadata] = []
            for props in client.list_properties_of_secret_versions(path):
                items.append(self._props_to_metadata(props, fallback_name=path))
            if not items:
                raise SecretNotFoundError(path, self.name)
            items.sort(key=lambda m: m.created_at or datetime.fromtimestamp(0, tz=UTC), reverse=True)
            return items
        except ResourceNotFoundError:
            raise SecretNotFoundError(path, self.name)
        except ClientAuthenticationError as e:
            raise ProviderError(self.name, f"authentication error: {e}")
        except HttpResponseError as e:
            if self._is_403(e):
                raise SecretPermissionError(self.name, "list", path, self._azure_hint())
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")
        except (SecretNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")


__all__ = ["AZURE_ASYNC_AVAILABLE", "AZURE_AVAILABLE", "AzureProvider"]
