"""Secret providers for scalo secrets module."""

from typing import TYPE_CHECKING

from .base import SecretProvider, VersionedProvider
from .file import FileProvider

# Optional providers with graceful import fallbacks. Each module guards its own
# SDK import, so type checkers (here and in consumers) see only the real class.
try:
    from .openbao import HTTPX_AVAILABLE, OpenBaoProvider
except ImportError, AttributeError:
    if not TYPE_CHECKING:
        OpenBaoProvider = None
    HTTPX_AVAILABLE = False

try:
    from .aws import AIOBOTOCORE_AVAILABLE, BOTO3_AVAILABLE, AWSProvider
except ImportError:
    if not TYPE_CHECKING:
        AWSProvider = None
    BOTO3_AVAILABLE = False
    AIOBOTOCORE_AVAILABLE = False

try:
    from .gcp import GCP_AVAILABLE, GCPProvider
except ImportError:
    if not TYPE_CHECKING:
        GCPProvider = None
    GCP_AVAILABLE = False

try:
    from .azure import AZURE_ASYNC_AVAILABLE, AZURE_AVAILABLE, AzureProvider
except ImportError:
    if not TYPE_CHECKING:
        AzureProvider = None
    AZURE_AVAILABLE = False
    AZURE_ASYNC_AVAILABLE = False

try:
    from .ansible_vault import ANSIBLE_VAULT_AVAILABLE, AnsibleVaultProvider
except ImportError:
    if not TYPE_CHECKING:
        AnsibleVaultProvider = None
    ANSIBLE_VAULT_AVAILABLE = False

# Needs httpx and stamina, and its constructor raises ProviderNotAvailableError without them.
try:
    from .kubernetes import KubernetesProvider
except ImportError:
    if not TYPE_CHECKING:
        KubernetesProvider = None

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
    "KubernetesProvider",
    "OpenBaoProvider",
    "SecretProvider",
    "VersionedProvider",
]
