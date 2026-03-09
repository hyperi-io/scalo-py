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

from ..exceptions import ProviderError, SecretNotFoundError
from ..types import AzureConfig, SecretValue
from .base import SecretProvider

logger = logging.getLogger(__name__)

try:
    from azure.core.exceptions import ClientAuthenticationError, ResourceNotFoundError
    from azure.identity import ClientSecretCredential, DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    ResourceNotFoundError = Exception  # type: ignore[assignment,misc]
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


class AzureProvider(SecretProvider):
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


__all__ = ["AzureProvider", "AZURE_AVAILABLE", "AZURE_ASYNC_AVAILABLE"]
