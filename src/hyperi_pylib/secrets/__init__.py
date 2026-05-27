"""hyperi-pylib Secrets Module.

Unified secrets management with multi-provider support, caching, and rotation detection.

Basic usage:
    from hyperi_pylib.secrets import SecretsManager

    # File-based secrets (always available)
    secrets = SecretsManager()
    value = await secrets.get("/path/to/secret")
    text = value.decode()

    # With OpenBao/Vault (requires: pip install hyperi-pylib[secrets-vault])
    from hyperi_pylib.secrets import SecretsManager, OpenBaoConfig

    secrets = SecretsManager.from_config({
        "openbao": {"address": "https://vault.example.com:8200", "auth": {"token": "hvs.xxx"}},
        "sources": {"api_key": {"provider": "openbao", "path": "secret/data/myapp", "key": "api_key"}},
    })
    value = await secrets.get("api_key")

    # With AWS (requires: pip install hyperi-pylib[secrets-aws])
    from hyperi_pylib.secrets import SecretsManager, AWSConfig

    secrets = SecretsManager.from_config({"aws": {"region": "us-west-2"}})
    value = await secrets.get("my-secret-id", provider="aws")

    # With GCP (requires: pip install hyperi-pylib[secrets-gcp])
    secrets = SecretsManager.from_config({"gcp": {"project_id": "my-project"}})
    value = await secrets.get("my-secret", provider="gcp")

    # With Azure (requires: pip install hyperi-pylib[secrets-azure])
    secrets = SecretsManager.from_config({"azure": {"vault_url": "https://my-vault.vault.azure.net/"}})
    value = await secrets.get("my-secret", provider="azure")

    # ENV fallback -- if provider is unavailable, fall back to environment variable
    secrets = SecretsManager.from_config({
        "sources": {"api_key": {"provider": "openbao", "path": "secret/data/myapp", "key": "api_key", "env_fallback": "MY_API_KEY"}},
    })

Providers:
    - file: Local filesystem (always available)
    - openbao: OpenBao/Vault (optional: hyperi-pylib[secrets-vault])
    - aws: AWS Secrets Manager (optional: hyperi-pylib[secrets-aws])
    - gcp: GCP Secret Manager (optional: hyperi-pylib[secrets-gcp])
    - azure: Azure Key Vault (optional: hyperi-pylib[secrets-azure])
"""

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
    SecretPermissionError,
    SecretsError,
    SecretVersionNotFoundError,
    VersioningNotSupportedError,
)

# Manager (always available)
from .manager import SecretsManager

# Providers
from .providers import (
    AIOBOTOCORE_AVAILABLE,
    AZURE_ASYNC_AVAILABLE,
    AZURE_AVAILABLE,
    BOTO3_AVAILABLE,
    GCP_AVAILABLE,
    HTTPX_AVAILABLE,
    AWSProvider,
    AzureProvider,
    FileProvider,
    GCPProvider,
    OpenBaoProvider,
    SecretProvider,
    VersionedProvider,
)
from .types import (
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
