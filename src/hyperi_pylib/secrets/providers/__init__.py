"""Secret providers for hyperi-pylib secrets module."""

from .base import SecretProvider, VersionedProvider
from .file import FileProvider

# Optional providers with graceful import fallbacks
try:
    from .openbao import HTTPX_AVAILABLE, OpenBaoProvider
except (ImportError, AttributeError):
    OpenBaoProvider = None  # type: ignore[assignment,misc]
    HTTPX_AVAILABLE = False

try:
    from .aws import AIOBOTOCORE_AVAILABLE, BOTO3_AVAILABLE, AWSProvider
except ImportError:
    AWSProvider = None  # type: ignore[assignment,misc]
    BOTO3_AVAILABLE = False
    AIOBOTOCORE_AVAILABLE = False

try:
    from .gcp import GCP_AVAILABLE, GCPProvider
except ImportError:
    GCPProvider = None  # type: ignore[assignment,misc]
    GCP_AVAILABLE = False

try:
    from .azure import AZURE_ASYNC_AVAILABLE, AZURE_AVAILABLE, AzureProvider
except ImportError:
    AzureProvider = None  # type: ignore[assignment,misc]
    AZURE_AVAILABLE = False
    AZURE_ASYNC_AVAILABLE = False

try:
    from .ansible_vault import ANSIBLE_VAULT_AVAILABLE, AnsibleVaultProvider
except ImportError:
    AnsibleVaultProvider = None  # type: ignore[assignment,misc]
    ANSIBLE_VAULT_AVAILABLE = False

__all__ = [
    "AIOBOTOCORE_AVAILABLE",
    "ANSIBLE_VAULT_AVAILABLE",
    "AZURE_ASYNC_AVAILABLE",
    "AZURE_AVAILABLE",
    "BOTO3_AVAILABLE",
    "GCP_AVAILABLE",
    "HTTPX_AVAILABLE",
    "AWSProvider",
    "AnsibleVaultProvider",
    "AzureProvider",
    "FileProvider",
    "GCPProvider",
    "OpenBaoProvider",
    "SecretProvider",
    "VersionedProvider",
]
