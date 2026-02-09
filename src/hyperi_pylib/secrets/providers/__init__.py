"""Secret providers for hyperi-pylib secrets module."""

from .base import SecretProvider
from .file import FileProvider

# Optional providers with graceful import fallbacks
try:
    from .openbao import HTTPX_AVAILABLE, OpenBaoProvider
except ImportError:
    OpenBaoProvider = None  # type: ignore[assignment,misc]
    HTTPX_AVAILABLE = False

try:
    from .aws import AIOBOTOCORE_AVAILABLE, BOTO3_AVAILABLE, AWSProvider
except ImportError:
    AWSProvider = None  # type: ignore[assignment,misc]
    BOTO3_AVAILABLE = False
    AIOBOTOCORE_AVAILABLE = False

__all__ = [
    "SecretProvider",
    "FileProvider",
    "OpenBaoProvider",
    "AWSProvider",
    "HTTPX_AVAILABLE",
    "BOTO3_AVAILABLE",
    "AIOBOTOCORE_AVAILABLE",
]
