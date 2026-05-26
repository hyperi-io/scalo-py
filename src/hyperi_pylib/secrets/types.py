"""Type definitions for hyperi-pylib secrets module."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Callable


class ProviderType(Enum):
    """Secret provider types."""

    FILE = "file"
    OPENBAO = "openbao"
    VAULT = "vault"  # Alias for OpenBao (HashiCorp Vault is API-compatible)
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ANSIBLE_VAULT = "ansible_vault"


@dataclass
class SecretValue:
    """Represents a fetched secret with metadata."""

    data: bytes
    """Raw secret data."""

    fetched_at: datetime
    """When fetched from provider."""

    version: str | None = None
    """Provider version ID (for rotation detection)."""

    source: str = "unknown"
    """Provider name."""

    def decode(self, encoding: str = "utf-8") -> str:
        """Decode bytes to string."""
        return self.data.decode(encoding)

    def is_expired(self, ttl_secs: int) -> bool:
        """Check if secret has exceeded TTL."""
        age = (datetime.now(UTC) - self.fetched_at).total_seconds()
        return age > ttl_secs

    def is_within_grace(self, ttl_secs: int, grace_secs: int) -> bool:
        """Check if secret is within stale grace period."""
        age = (datetime.now(UTC) - self.fetched_at).total_seconds()
        return age <= (ttl_secs + grace_secs)


@dataclass
class RotationEvent:
    """Event emitted when a secret is rotated."""

    name: str
    """Secret name."""

    old_version: str | None
    """Previous version."""

    new_version: str
    """New version."""

    rotated_at: datetime
    """When rotation detected."""


@dataclass
class CacheConfig:
    """Configuration for secrets caching."""

    enabled: bool = True
    """Enable caching."""

    directory: str | None = None
    """Cache directory. None = auto-detect."""

    ttl_secs: int = 3600
    """Fresh cache validity (default: 1 hour)."""

    stale_grace_secs: int = 86400
    """Stale cache fallback period (default: 24 hours)."""

    refresh_interval_secs: int = 1800
    """Background refresh interval (default: 30 min)."""

    refresh_jitter_secs: int = 300
    """Randomize refresh timing (default: 5 min)."""

    encryption_key: bytes | None = None
    """Optional encryption key for cache at rest."""


@dataclass
class SourceConfig:
    """Configuration for a single secret source."""

    provider: ProviderType
    """Provider type."""

    path: str | None = None
    """File path or Vault path."""

    secret_id: str | None = None
    """AWS secret ID or GCP/Azure secret name."""

    key: str | None = None
    """Key within JSON secret."""

    env_fallback: str | None = None
    """ENV variable name to use if provider is unavailable (e.g. MY_API_KEY)."""


@dataclass
class OpenBaoConfig:
    """OpenBao/Vault provider configuration."""

    address: str
    """Vault/OpenBao server address."""

    auth_method: str = "token"
    """Authentication method: token, approle, kubernetes."""

    token: str | None = None
    """Vault token (for token auth)."""

    role_id: str | None = None
    """AppRole role ID."""

    secret_id: str | None = None
    """AppRole secret ID."""

    role: str | None = None
    """Role name (for kubernetes auth)."""

    token_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # noqa: S105
    """Path to service account token (for kubernetes auth)."""

    mount: str | None = None
    """Auth mount path."""

    namespace: str | None = None
    """Vault Enterprise namespace."""

    ca_cert: str | None = None
    """Path to CA certificate."""

    skip_verify: bool = False
    """Skip TLS verification (not recommended)."""

    timeout_secs: int = 30
    """Request timeout in seconds."""


@dataclass
class AWSConfig:
    """AWS Secrets Manager configuration."""

    region: str = "us-east-1"
    """AWS region."""

    access_key_id: str | None = None
    """AWS access key ID. None = use default credential chain."""

    secret_access_key: str | None = None
    """AWS secret access key."""

    endpoint_url: str | None = None
    """Custom endpoint URL (for LocalStack)."""

    timeout_secs: int = 30
    """Request timeout in seconds."""


@dataclass
class GCPConfig:
    """GCP Secret Manager configuration."""

    project_id: str
    """GCP project ID."""

    credentials_file: str | None = None
    """Path to service account JSON key file. None = Application Default Credentials."""

    timeout_secs: int = 30
    """Request timeout in seconds."""


@dataclass
class AzureConfig:
    """Azure Key Vault configuration."""

    vault_url: str
    """Key Vault URL, e.g. https://my-vault.vault.azure.net/"""

    tenant_id: str | None = None
    """Azure AD tenant ID. None = DefaultAzureCredential chain."""

    client_id: str | None = None
    """Service principal client ID. None = DefaultAzureCredential chain."""

    client_secret: str | None = None
    """Service principal client secret. None = DefaultAzureCredential chain."""

    timeout_secs: int = 30
    """Request timeout in seconds."""


@dataclass
class AnsibleVaultConfig:
    """Ansible Vault provider configuration.

    Designed primarily for SME networks that need encrypted-at-rest secrets
    without the operational overhead of a dedicated secrets server. Also suitable
    for dev/test environments, CI pipelines, or any setup where Ansible Vault is
    already the team's standard for secret management.
    """

    password: str | None = None
    """Resolved vault password (from env var or file)."""

    password_file: str | None = None
    """Path to file containing the vault password (fallback)."""


@dataclass
class SecretMetadata:
    """Normalised secret metadata across all providers.

    Fields are None when the provider doesn't support them.
    File-based providers won't have tags or expires_at; cloud providers
    populate most fields from their native metadata APIs.
    """

    name: str
    """Secret name or path."""

    created_at: datetime | None = None
    """When the secret was created."""

    updated_at: datetime | None = None
    """When the secret was last modified."""

    expires_at: datetime | None = None
    """When the secret expires (Azure, AWS rotation)."""

    version: str | None = None
    """Current version identifier."""

    version_count: int | None = None
    """Number of versions (versioned providers only)."""

    tags: dict[str, str] | None = None
    """Provider tags/labels (cloud providers, OpenBao custom metadata)."""

    source: str = "unknown"
    """Provider name."""


@dataclass
class SecretFilter:
    """Filter for listing secrets.

    prefix is the primary efficient filter (server-side on most providers).
    pattern is a client-side post-filter using fnmatch glob syntax.
    tags filter is server-side on cloud providers, ignored by file-based providers.
    """

    prefix: str | None = None
    """Path prefix -- server-side filter where supported."""

    tags: dict[str, str] | None = None
    """Tag/label filter. Server-side on AWS/GCP/Azure/OpenBao. Ignored on file-based."""

    pattern: str | None = None
    """Glob pattern -- client-side post-filter on list results. Use prefix for efficiency."""


# Type alias for rotation callbacks
RotationCallback = Callable[[RotationEvent], None]


__all__ = [
    "AWSConfig",
    "AnsibleVaultConfig",
    "AzureConfig",
    "CacheConfig",
    "GCPConfig",
    "OpenBaoConfig",
    "ProviderType",
    "RotationCallback",
    "RotationEvent",
    "SecretFilter",
    "SecretMetadata",
    "SecretValue",
    "SourceConfig",
]
