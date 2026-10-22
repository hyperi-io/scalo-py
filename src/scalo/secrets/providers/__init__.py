"""Secret providers for scalo secrets module.

A provider module imports its SDK when it is imported, so a provider name below loads its module on first
access (PEP 562) and ``import scalo.secrets.providers`` loads no SDK. ``FileProvider`` and the base classes
need none and are imported here.
"""

import importlib
from typing import TYPE_CHECKING, Any

from .base import SecretProvider, VersionedProvider
from .file import FileProvider

# Type checkers (here and in consumers) see the real names, because the runtime ones load on first access.
if TYPE_CHECKING:
    from .ansible_vault import ANSIBLE_VAULT_AVAILABLE, AnsibleVaultProvider
    from .aws import AIOBOTOCORE_AVAILABLE, BOTO3_AVAILABLE, AWSProvider
    from .azure import AZURE_ASYNC_AVAILABLE, AZURE_AVAILABLE, AzureProvider
    from .gcp import GCP_AVAILABLE, GCPProvider
    from .kubernetes import KubernetesProvider
    from .openbao import HTTPX_AVAILABLE, OpenBaoProvider

# Each name and the provider module that defines it. A module guards its own SDK import, so importing it
# never raises for a missing SDK: the availability flag is False and the provider's constructor raises.
_LAZY = {
    "AIOBOTOCORE_AVAILABLE": "aws",
    "ANSIBLE_VAULT_AVAILABLE": "ansible_vault",
    "AZURE_ASYNC_AVAILABLE": "azure",
    "AZURE_AVAILABLE": "azure",
    "BOTO3_AVAILABLE": "aws",
    "GCP_AVAILABLE": "gcp",
    "HTTPX_AVAILABLE": "openbao",
    "AWSProvider": "aws",
    "AnsibleVaultProvider": "ansible_vault",
    "AzureProvider": "azure",
    "GCPProvider": "gcp",
    "KubernetesProvider": "kubernetes",
    "OpenBaoProvider": "openbao",
}
_MODULES = frozenset(_LAZY.values())


def __getattr__(name: str) -> Any:
    """Import the provider module that defines ``name`` and return it (PEP 562).

    A provider module's own name (``providers.aws``) imports and returns that module, so attribute access
    to a submodule keeps working without an explicit import.
    """
    if name in _MODULES:
        module_name, attribute = name, None
    elif name in _LAZY:
        module_name, attribute = _LAZY[name], name
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # The module name comes from the fixed tables above, never from the caller's input.
    # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
    module = importlib.import_module(f".{module_name}", __name__)
    return module if attribute is None else getattr(module, attribute)


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
