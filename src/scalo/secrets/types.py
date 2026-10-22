"""Type definitions for scalo secrets module."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Callable
from urllib.parse import urlsplit


class ProviderType(Enum):
    """Secret provider types."""

    FILE = "file"
    OPENBAO = "openbao"
    VAULT = "vault"  # Alias for OpenBao (HashiCorp Vault is API-compatible)
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ANSIBLE_VAULT = "ansible_vault"
    KUBERNETES = "kubernetes"


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
    """Enable caching. False turns off the memory and disk tiers and the stale-grace fallback."""

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

    encryption_key: bytes | str | None = None
    """Key that seals disk-cache entries with AES-256-GCM, UTF-8 encoded when a str.

    Without one the disk tier is off (memory-only) unless ``allow_plaintext_disk_cache`` is set.
    """

    allow_plaintext_disk_cache: bool = False
    """Permit UNENCRYPTED disk-cache entries when no ``encryption_key`` is set: written, and read back.

    Default False: without a key the disk tier is skipped rather than persisting plaintext secrets, and a
    plaintext file in the cache directory is not read. Ignored once ``encryption_key`` is set. Refused at
    construction when the app environment (APP_ENV, ENVIRONMENT, ENV) is ``production`` or ``prod``.
    """


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

    token: str | None = field(default=None, repr=False)
    """Vault token (for token auth). repr=False to prevent repr leak."""

    role_id: str | None = field(default=None, repr=False)
    """AppRole role ID. repr=False to prevent repr leak."""

    secret_id: str | None = field(default=None, repr=False)
    """AppRole secret ID. repr=False to prevent repr leak."""

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

    region: str | None = None
    """AWS region. None leaves the region to the SDK chain, and there is no default region."""

    access_key_id: str | None = field(default=None, repr=False)
    """AWS access key ID. repr=False to prevent repr leak.
    None = use default credential chain."""

    secret_access_key: str | None = field(default=None, repr=False)
    """AWS secret access key. repr=False to prevent repr leak."""

    endpoint_url: str | None = None
    """Custom endpoint URL (for LocalStack)."""

    timeout_secs: int = 30
    """Request timeout in seconds."""

    kms_key_id: str | None = None
    """KMS key ID, ARN or alias that encrypts secrets this provider creates. None = the AWS managed key."""

    recovery_window_days: int | None = None
    """Days a deleted secret stays recoverable: None = the AWS default (30), 0 = delete at once, or 7-30."""

    def __post_init__(self) -> None:
        """Refuse a recovery window AWS would reject.

        Raises:
            ValueError: ``recovery_window_days`` is not None, 0 or 7-30.
        """
        window = self.recovery_window_days
        if window is None:
            return
        # bool is an int subclass, and False would otherwise read as a forced delete.
        if isinstance(window, bool) or not isinstance(window, int) or not (window == 0 or 7 <= window <= 30):
            raise ValueError(f"recovery_window_days must be 0 (delete without recovery) or 7-30, got {window!r}")


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

    client_secret: str | None = field(default=None, repr=False)
    """Service principal client secret. repr=False to prevent repr leak.
    None = DefaultAzureCredential chain."""

    timeout_secs: int = 30
    """Request timeout in seconds."""


_SERVICE_ACCOUNT_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
# A Secret name is a DNS-1123 subdomain and a namespace a DNS-1123 label, so neither can reshape the API path.
_DNS1123_SUBDOMAIN = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*")
_DNS1123_SUBDOMAIN_MAX = 253
_DNS1123_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?")
_DNS1123_LABEL_MAX = 63


def _check_secret_name(name: str) -> None:
    """Refuse a Kubernetes Secret name the API server would reject.

    Raises:
        ValueError: ``name`` is not a DNS-1123 subdomain of at most 253 characters.
    """
    if len(name) > _DNS1123_SUBDOMAIN_MAX or not _DNS1123_SUBDOMAIN.fullmatch(name):
        raise ValueError(
            f"Kubernetes Secret name {name!r} must be a DNS-1123 subdomain: lowercase letters, digits, "
            f"'-' and '.', starting and ending alphanumeric, at most {_DNS1123_SUBDOMAIN_MAX} characters"
        )


def _check_namespace(namespace: str) -> None:
    """Refuse a Kubernetes namespace the API server would reject.

    Raises:
        ValueError: ``namespace`` is not a DNS-1123 label of at most 63 characters.
    """
    if len(namespace) > _DNS1123_LABEL_MAX or not _DNS1123_LABEL.fullmatch(namespace):
        raise ValueError(
            f"Kubernetes namespace {namespace!r} must be a DNS-1123 label: lowercase letters, digits "
            f"and '-', starting and ending alphanumeric, at most {_DNS1123_LABEL_MAX} characters"
        )


@dataclass
class KubernetesConfig:
    """Kubernetes Secret provider configuration: the data keys of one named Secret are the secrets.

    The provider authenticates with the pod's service account, so the defaults are the paths the
    kubelet mounts the account's token, CA and namespace at.
    """

    secret_name: str
    """The Secret whose keys the provider reads and writes. It must exist: the provider never creates or deletes it."""

    namespace: str | None = None
    """The Secret's namespace. None = the pod's own, read from ``namespace_path``."""

    api_server: str | None = None
    """API server URL. None = ``https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT``, as every pod is given."""

    allow_insecure_http: bool = False
    """Accept an ``http://`` ``api_server``, which sends the service account token in cleartext."""

    token_path: str = f"{_SERVICE_ACCOUNT_DIR}/token"
    """Service account token, read on every request because the kubelet rotates a projected token."""

    ca_cert: str | None = f"{_SERVICE_ACCOUNT_DIR}/ca.crt"
    """CA bundle the API server's certificate is checked against. None = the system trust store."""

    namespace_path: str = f"{_SERVICE_ACCOUNT_DIR}/namespace"
    """File holding the pod's namespace, read when ``namespace`` is None."""

    timeout_secs: int = 30
    """Request timeout in seconds."""

    conflict_retries: int = 5
    """Writes retried after a 409, when another writer changed the Secret between the read and the replace."""

    def __post_init__(self) -> None:
        """Refuse a Secret name, namespace, API server or retry count the provider cannot use.

        Raises:
            ValueError: The Secret name or namespace is malformed, ``api_server`` is not an ``https://`` URL
                (or ``http://`` with ``allow_insecure_http``), or ``conflict_retries`` is negative.
        """
        _check_secret_name(self.secret_name)
        if self.namespace is not None:
            _check_namespace(self.namespace)
        if self.api_server is not None:
            scheme = urlsplit(self.api_server).scheme.lower()
            if scheme == "http" and not self.allow_insecure_http:
                raise ValueError(
                    f"api_server {self.api_server!r} would send the service account token in cleartext: use "
                    "https://, or set allow_insecure_http for a local test API server"
                )
            if scheme not in ("https", "http"):
                raise ValueError(f"api_server must be an https:// URL, got {self.api_server!r}")
        if self.conflict_retries < 0:
            raise ValueError(f"conflict_retries must be 0 or more, got {self.conflict_retries}")


@dataclass
class AnsibleVaultConfig:
    """Ansible Vault provider configuration.

    Designed primarily for SME networks that need encrypted-at-rest secrets
    without the operational overhead of a dedicated secrets server. Also suitable
    for dev/test environments, CI pipelines, or any setup where Ansible Vault is
    already the team's standard for secret management.
    """

    password: str | None = field(default=None, repr=False)
    """Resolved vault password (from env var or file). repr=False to prevent repr leak."""

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
    "KubernetesConfig",
    "OpenBaoConfig",
    "ProviderType",
    "RotationCallback",
    "RotationEvent",
    "SecretFilter",
    "SecretMetadata",
    "SecretValue",
    "SourceConfig",
]
