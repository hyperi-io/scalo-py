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

    secrets = SecretsManager(
        openbao=OpenBaoConfig(
            address="https://vault.example.com:8200",
            token="hvs.xxx",
        )
    )
    value = await secrets.get("secret/data/myapp/config", key="api_key")

    # With AWS (requires: pip install hyperi-pylib[secrets-aws])
    from hyperi_pylib.secrets import SecretsManager, AWSConfig

    secrets = SecretsManager(
        aws=AWSConfig(region="us-west-2")
    )
    value = await secrets.get("my-secret-id", provider="aws")

Providers:
    - file: Local filesystem (always available)
    - openbao: OpenBao/Vault (optional: hyperi-pylib[secrets-vault])
    - aws: AWS Secrets Manager (optional: hyperi-pylib[secrets-aws])

Install all providers:
    pip install hyperi-pylib[secrets-all]
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
    SecretNotFoundError,
    SecretsError,
)

# Manager (always available)
from .manager import SecretsManager

# Providers
from .providers import (
    AIOBOTOCORE_AVAILABLE,
    BOTO3_AVAILABLE,
    HTTPX_AVAILABLE,
    AWSProvider,
    FileProvider,
    OpenBaoProvider,
    SecretProvider,
)
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

__all__ = [
    # Manager
    "SecretsManager",
    # Types
    "ProviderType",
    "SecretValue",
    "RotationEvent",
    "CacheConfig",
    "SourceConfig",
    "OpenBaoConfig",
    "AWSConfig",
    "RotationCallback",
    # Exceptions
    "SecretsError",
    "SecretNotFoundError",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderNotAvailableError",
    "CacheError",
    "AuthenticationError",
    # Cache
    "DiskCache",
    # Providers
    "SecretProvider",
    "FileProvider",
    "OpenBaoProvider",
    "AWSProvider",
    # Availability flags
    "HTTPX_AVAILABLE",
    "BOTO3_AVAILABLE",
    "AIOBOTOCORE_AVAILABLE",
]
