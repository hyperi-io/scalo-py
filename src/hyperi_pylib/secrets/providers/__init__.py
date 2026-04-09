"""Secret providers for hyperi-pylib secrets module."""

from .base import SecretProvider
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

__all__ = [
    "SecretProvider",
    "FileProvider",
    "OpenBaoProvider",
    "AWSProvider",
    "GCPProvider",
    "AzureProvider",
    "HTTPX_AVAILABLE",
    "BOTO3_AVAILABLE",
    "AIOBOTOCORE_AVAILABLE",
    "GCP_AVAILABLE",
    "AZURE_AVAILABLE",
    "AZURE_ASYNC_AVAILABLE",
]
