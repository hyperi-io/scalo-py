"""scalo Secrets Module.

Unified secrets management with multi-provider support, caching, and rotation detection.

Basic usage:
    from scalo.secrets import SecretsManager

    # File-based secrets (always available)
    secrets = SecretsManager()
    value = await secrets.get("/path/to/secret")
    text = value.decode()

    # With OpenBao/Vault (requires: pip install scalo[secrets-vault])
    from scalo.secrets import SecretsManager, OpenBaoConfig

    secrets = SecretsManager.from_config({
        "openbao": {"address": "https://vault.example.com:8200", "auth": {"token": "hvs.xxx"}},
        "sources": {"api_key": {"provider": "openbao", "path": "secret/data/myapp", "key": "api_key"}},
    })
    value = await secrets.get("api_key")

    # With AWS (requires: pip install scalo[secrets-aws])
    from scalo.secrets import SecretsManager, AWSConfig

    secrets = SecretsManager.from_config({"aws": {"region": "us-west-2"}})
    value = await secrets.get("my-secret-id", provider="aws")

    # With GCP (requires: pip install scalo[secrets-gcp])
    secrets = SecretsManager.from_config({"gcp": {"project_id": "my-project"}})
    value = await secrets.get("my-secret", provider="gcp")

    # With Azure (requires: pip install scalo[secrets-azure])
    secrets = SecretsManager.from_config({"azure": {"vault_url": "https://my-vault.vault.azure.net/"}})
    value = await secrets.get("my-secret", provider="azure")

    # With the keys of one Kubernetes Secret, from inside a pod (requires: pip install scalo[secrets-kubernetes])
    secrets = SecretsManager.from_config({"kubernetes": {"secret_name": "my-app-tokens"}})
    value = await secrets.get("api-key", provider="kubernetes")

    # ENV fallback -- if provider is unavailable, fall back to environment variable
    secrets = SecretsManager.from_config({
        "sources": {"api_key": {"provider": "openbao", "path": "secret/data/myapp", "key": "api_key", "env_fallback": "MY_API_KEY"}},
    })

Providers:
    - file: Local filesystem (always available)
    - openbao: OpenBao/Vault (optional: scalo[secrets-vault])
    - aws: AWS Secrets Manager (optional: scalo[secrets-aws])
    - gcp: GCP Secret Manager (optional: scalo[secrets-gcp])
    - azure: Azure Key Vault (optional: scalo[secrets-azure])
    - kubernetes: the keys of one Kubernetes Secret (optional: scalo[secrets-kubernetes])
"""

from typing import TYPE_CHECKING, Any

from . import providers

# Core types (always available)
# Cache (always available)
from .cache import DiskCache

# Exceptions (always available)
from .exceptions import (
    AuthenticationError,
    CacheError,
    ProviderError,
    ProviderNotAvailableError,
    ProviderNotConfiguredError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPendingDeletionError,
    SecretPermissionError,
    SecretsError,
    SecretVersionNotFoundError,
    VersioningNotSupportedError,
)

# Manager (always available)
from .manager import SecretsManager

# Providers that need no SDK. The others load on first access, see below.
from .providers import FileProvider, SecretProvider, VersionedProvider
from .types import (
    AWSConfig,
    AzureConfig,
    CacheConfig,
    GCPConfig,
    KubernetesConfig,
    OpenBaoConfig,
    ProviderType,
    RotationCallback,
    RotationEvent,
    SecretFilter,
    SecretMetadata,
    SecretValue,
    SourceConfig,
)

# Type checkers (here and in consumers) see the real names, because the runtime ones load on first access.
if TYPE_CHECKING:
    from .providers import (
        AIOBOTOCORE_AVAILABLE,
        AZURE_ASYNC_AVAILABLE,
        AZURE_AVAILABLE,
        BOTO3_AVAILABLE,
        GCP_AVAILABLE,
        HTTPX_AVAILABLE,
        AWSProvider,
        AzureProvider,
        GCPProvider,
        KubernetesProvider,
        OpenBaoProvider,
    )

# Provider names re-exported here, each resolved through ``scalo.secrets.providers`` (PEP 562).
_PROVIDER_NAMES = frozenset(
    {
        "AIOBOTOCORE_AVAILABLE",
        "AZURE_ASYNC_AVAILABLE",
        "AZURE_AVAILABLE",
        "BOTO3_AVAILABLE",
        "GCP_AVAILABLE",
        "HTTPX_AVAILABLE",
        "AWSProvider",
        "AzureProvider",
        "GCPProvider",
        "KubernetesProvider",
        "OpenBaoProvider",
    }
)


def __getattr__(name: str) -> Any:
    """Return a provider name, importing its provider module and SDK on first access (PEP 562)."""
    if name in _PROVIDER_NAMES:
        return getattr(providers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AIOBOTOCORE_AVAILABLE",
    "AZURE_ASYNC_AVAILABLE",
    "AZURE_AVAILABLE",
    "BOTO3_AVAILABLE",
    "GCP_AVAILABLE",
    # Availability flags
    "HTTPX_AVAILABLE",
    "AWSConfig",
    "AWSProvider",
    "AuthenticationError",
    "AzureConfig",
    "AzureProvider",
    "CacheConfig",
    "CacheError",
    # Cache
    "DiskCache",
    "FileProvider",
    "GCPConfig",
    "GCPProvider",
    "KubernetesConfig",
    "KubernetesProvider",
    "OpenBaoConfig",
    "OpenBaoProvider",
    "ProviderError",
    "ProviderNotAvailableError",
    "ProviderNotConfiguredError",
    # Types
    "ProviderType",
    "RotationCallback",
    "RotationEvent",
    "SecretAlreadyExistsError",
    "SecretFilter",
    "SecretMetadata",
    "SecretNotFoundError",
    "SecretPendingDeletionError",
    "SecretPermissionError",
    # Providers
    "SecretProvider",
    "SecretValue",
    "SecretVersionNotFoundError",
    # Exceptions
    "SecretsError",
    # Manager
    "SecretsManager",
    "SourceConfig",
    "VersionedProvider",
    "VersioningNotSupportedError",
]
