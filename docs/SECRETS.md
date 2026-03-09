# hyperi-pylib Secrets Management Guide

## Overview

hyperi-pylib provides a unified secrets management module for securely loading certificates, credentials, and other sensitive data from multiple sources with automatic caching and resilience.

## Key Features

- **Multi-provider support** - Files, OpenBao/Vault, AWS Secrets Manager
- **Automatic caching** - Local disk cache with TTL for resilience
- **Stale fallback** - Use cached secrets when providers are unavailable
- **Background refresh** - Proactive secret renewal before expiry
- **Rotation callbacks** - Notify applications when secrets change
- **Zero-config defaults** - Works with file paths out of the box

## Quick Start

```python
from hyperi_pylib.secrets import SecretsManager, SecretRef

# Simple file-based usage (backwards compatible)
secrets = SecretsManager()
cert = await secrets.get("/etc/ssl/cert.pem")

# Named secret sources
secrets = SecretsManager.from_config({
    "sources": {
        "tls_cert": {"provider": "file", "path": "/etc/ssl/cert.pem"},
        "api_key": {"provider": "openbao", "path": "secret/data/myapp", "key": "api_key"},
    }
})
cert = await secrets.get("tls_cert")
api_key = await secrets.get("api_key")
```

## Installation

```bash
# Core only (file provider)
uv add hyperi-pylib

# With OpenBao/Vault support
uv add hyperi-pylib[secrets-vault]

# With AWS Secrets Manager support
uv add hyperi-pylib[secrets-aws]

# All secrets providers
uv add hyperi-pylib[secrets-all]
```

## Providers

### File Provider (Always Available)

Loads secrets from local filesystem. This is the default provider and requires no additional dependencies.

```python
from hyperi_pylib.secrets import SecretsManager

secrets = SecretsManager()

# Direct file path
cert = await secrets.get("/etc/ssl/cert.pem")

# Via configuration
secrets = SecretsManager.from_config({
    "sources": {
        "tls_cert": {
            "provider": "file",
            "path": "/etc/ssl/cert.pem"
        }
    }
})
```

**Use cases:**

- Kubernetes secrets mounted as files
- Docker secrets in `/run/secrets`
- Local development with file-based credentials
- External Secrets Operator (ESO) synced files

### OpenBao/Vault Provider

Loads secrets from HashiCorp Vault or OpenBao (Vault fork).

```python
from hyperi_pylib.secrets import SecretsManager

secrets = SecretsManager.from_config({
    "openbao": {
        "address": "https://vault.example.com:8200",
        "auth": {
            "method": "approle",
            "role_id": "${VAULT_ROLE_ID}",
            "secret_id": "${VAULT_SECRET_ID}"
        },
        "namespace": "hypersec",  # Optional, for Vault Enterprise
        "ca_cert": "/etc/ssl/vault-ca.pem"  # Optional
    },
    "sources": {
        "tls_cert": {
            "provider": "openbao",
            "path": "secret/data/myapp/tls",
            "key": "certificate"
        },
        "tls_key": {
            "provider": "openbao",
            "path": "secret/data/myapp/tls",
            "key": "private_key"
        }
    }
})
```

**Authentication Methods:**

| Method | Configuration | Use Case |
|--------|--------------|----------|
| `token` | `{"method": "token", "token": "..."}` | Development, CI/CD |
| `approle` | `{"method": "approle", "role_id": "...", "secret_id": "..."}` | Production services |
| `kubernetes` | `{"method": "kubernetes", "role": "myapp"}` | Kubernetes pods |

**AppRole Example:**

```python
secrets = SecretsManager.from_config({
    "openbao": {
        "address": "https://vault.example.com:8200",
        "auth": {
            "method": "approle",
            "role_id": os.environ["VAULT_ROLE_ID"],
            "secret_id": os.environ["VAULT_SECRET_ID"],
            "mount": "approle"  # Default mount path
        }
    }
})
```

**Kubernetes Auth Example:**

```python
secrets = SecretsManager.from_config({
    "openbao": {
        "address": "https://vault.example.com:8200",
        "auth": {
            "method": "kubernetes",
            "role": "myapp-role",
            "token_path": "/var/run/secrets/kubernetes.io/serviceaccount/token",
            "mount": "kubernetes"
        }
    }
})
```

### AWS Secrets Manager Provider

Loads secrets from AWS Secrets Manager with automatic credential chain.

```python
from hyperi_pylib.secrets import SecretsManager

secrets = SecretsManager.from_config({
    "aws": {
        "region": "us-east-1",
        # Uses default credential chain:
        # 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        # 2. Shared credentials file (~/.aws/credentials)
        # 3. IAM instance profile (EC2, ECS, Lambda)
    },
    "sources": {
        "db_password": {
            "provider": "aws",
            "secret_id": "prod/myapp/database",
            "key": "password"  # Optional: extract from JSON secret
        },
        "api_credentials": {
            "provider": "aws",
            "secret_id": "arn:aws:secretsmanager:us-east-1:123456789:secret:myapp/api"
        }
    }
})

# Get specific key from JSON secret
password = await secrets.get("db_password")

# Get full secret (for plaintext secrets)
credentials = await secrets.get("api_credentials")
```

**With explicit credentials:**

```python
secrets = SecretsManager.from_config({
    "aws": {
        "region": "us-east-1",
        "access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
        "secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "endpoint_url": "http://localhost:4566"  # LocalStack
    }
})
```

## Caching

Caching provides resilience when external providers are unavailable. Secrets are cached to disk and used as fallback.

### Cache Configuration

```python
secrets = SecretsManager.from_config({
    "cache": {
        "enabled": True,  # Default: True
        "directory": "/var/cache/myapp/secrets",  # Default: auto-detect
        "ttl_secs": 3600,  # Fresh cache validity (default: 1 hour)
        "stale_grace_secs": 86400,  # Stale cache fallback (default: 24 hours)
        "refresh_interval_secs": 1800,  # Background refresh (default: 30 min)
        "refresh_jitter_secs": 300,  # Randomize refresh (default: 5 min)
        "encryption_key": None  # Optional: encrypt cache at rest
    }
})
```

### Cache Behavior

```text
get_secret(name)
    │
    ├─ Check memory cache
    │   └─ Hit + fresh → Return immediately
    │
    ├─ Check disk cache
    │   └─ Hit + fresh → Update memory, return
    │
    ├─ Fetch from provider
    │   ├─ Success → Update caches, return
    │   └─ Failure ─┐
    │               │
    ├─ Check stale cache (within grace period)
    │   └─ Hit → Return with warning logged
    │
    └─ No cache available → Raise SecretsError
```

### Encrypted Cache (Optional)

For environments requiring encryption at rest:

```python
secrets = SecretsManager.from_config({
    "cache": {
        "enabled": True,
        "encryption_key": os.environ.get("SECRETS_CACHE_KEY")
        # If not set, cache is stored in plaintext
        # Plaintext is acceptable for ephemeral containers with encrypted volumes
    }
})
```

**Note:** For Kubernetes deployments with encrypted PersistentVolumes or ephemeral storage, plaintext cache is typically acceptable.

## Background Refresh

Secrets are proactively refreshed before TTL expiry to ensure fresh credentials.

```python
secrets = SecretsManager.from_config({
    "cache": {
        "refresh_interval_secs": 1800,  # Check every 30 minutes
        "refresh_jitter_secs": 300  # Add 0-5 min random delay
    }
})

# Start background refresh task
await secrets.start_refresh()

# On shutdown
await secrets.stop_refresh()
```

## Rotation Callbacks

Register callbacks to be notified when secrets are refreshed with new versions:

```python
from hyperi_pylib.secrets import SecretsManager, RotationEvent

def on_secret_rotation(event: RotationEvent):
    logger.info(
        "Secret rotated",
        name=event.name,
        old_version=event.old_version,
        new_version=event.new_version
    )
    # Reconnect database, refresh tokens, etc.
    if event.name == "db_password":
        reconnect_database()

secrets = SecretsManager.from_config({...})
secrets.on_rotation(on_secret_rotation)

# Or for specific secrets
secrets.on_rotation(on_secret_rotation, names=["db_password", "api_key"])
```

## Configuration Reference

### Full Configuration Example

```yaml
# config.yaml
secrets:
  # Cache settings
  cache:
    enabled: true
    directory: /var/cache/myapp/secrets
    ttl_secs: 3600
    stale_grace_secs: 86400
    refresh_interval_secs: 1800
    refresh_jitter_secs: 300
    encryption_key: ${SECRETS_CACHE_KEY}  # Optional

  # OpenBao/Vault provider
  openbao:
    address: https://vault.example.com:8200
    auth:
      method: approle
      role_id: ${VAULT_ROLE_ID}
      secret_id: ${VAULT_SECRET_ID}
    namespace: hypersec
    ca_cert: /etc/ssl/vault-ca.pem
    skip_verify: false

  # AWS Secrets Manager provider
  aws:
    region: us-east-1
    # Uses default credential chain

  # Named secret sources
  sources:
    # File-based (K8s secret mount)
    tls_cert:
      provider: file
      path: /secrets/tls/cert.pem

    tls_key:
      provider: file
      path: /secrets/tls/key.pem

    # OpenBao/Vault
    ca_bundle:
      provider: openbao
      path: secret/data/pki/ca
      key: certificate

    kafka_password:
      provider: openbao
      path: secret/data/kafka/credentials
      key: password

    # AWS Secrets Manager
    api_credentials:
      provider: aws
      secret_id: prod/myapp/api
      key: api_key
```

### Loading Configuration

```python
from hyperi_pylib.secrets import SecretsManager
from hyperi_pylib.config import settings

# From hyperi-pylib config cascade
secrets = SecretsManager.from_config(settings.get("secrets", {}))

# Or from YAML file directly
import yaml
with open("config.yaml") as f:
    config = yaml.safe_load(f)
secrets = SecretsManager.from_config(config["secrets"])
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HYPERI_SECRETS_CACHE_DIR` | Cache directory | Auto-detect |
| `HYPERI_SECRETS_CACHE_TTL` | Cache TTL in seconds | 3600 |
| `HYPERI_SECRETS_CACHE_KEY` | Cache encryption key | None (plaintext) |
| `VAULT_ADDR` | OpenBao/Vault address | None |
| `VAULT_TOKEN` | Vault token (if using token auth) | None |
| `VAULT_ROLE_ID` | AppRole role ID | None |
| `VAULT_SECRET_ID` | AppRole secret ID | None |
| `VAULT_NAMESPACE` | Vault namespace | None |
| `AWS_REGION` | AWS region | us-east-1 |

## Integration with TLS

The secrets module integrates seamlessly with TLS configuration:

```python
from hyperi_pylib.secrets import SecretsManager
from hyperi_pylib.tls import TlsConfig  # Future module

secrets = SecretsManager.from_config({
    "sources": {
        "server_cert": {"provider": "openbao", "path": "pki/issue/server", "key": "certificate"},
        "server_key": {"provider": "openbao", "path": "pki/issue/server", "key": "private_key"},
        "ca_bundle": {"provider": "file", "path": "/etc/ssl/ca-bundle.pem"}
    }
})

# Load certificates
cert_pem = await secrets.get("server_cert")
key_pem = await secrets.get("server_key")
ca_pem = await secrets.get("ca_bundle")

# Use with TLS configuration
tls_config = TlsConfig(
    cert_data=cert_pem.decode(),
    key_data=key_pem.decode(),
    ca_data=ca_pem.decode()
)
```

## API Reference

### SecretsManager

```python
class SecretsManager:
    @classmethod
    def from_config(cls, config: dict) -> "SecretsManager":
        """Create manager from configuration dictionary."""

    async def get(self, name_or_path: str) -> bytes:
        """Get secret by name or file path."""

    async def get_string(self, name_or_path: str, encoding: str = "utf-8") -> str:
        """Get secret as string."""

    async def start_refresh(self) -> None:
        """Start background refresh task."""

    async def stop_refresh(self) -> None:
        """Stop background refresh task."""

    def on_rotation(
        self,
        callback: Callable[[RotationEvent], None],
        names: Optional[List[str]] = None
    ) -> None:
        """Register rotation callback."""

    async def health_check(self) -> dict[str, bool]:
        """Check health of all configured providers."""

    def clear_cache(self) -> None:
        """Clear all cached secrets."""
```

### SecretValue

```python
@dataclass
class SecretValue:
    data: bytes                    # Raw secret data
    fetched_at: datetime           # When fetched
    version: Optional[str]         # Provider version ID
    source: str                    # Provider name

    def decode(self, encoding: str = "utf-8") -> str:
        """Decode bytes to string."""

    def is_expired(self, ttl_secs: int) -> bool:
        """Check if secret has exceeded TTL."""

    def is_within_grace(self, ttl_secs: int, grace_secs: int) -> bool:
        """Check if secret is within stale grace period."""
```

### RotationEvent

```python
@dataclass
class RotationEvent:
    name: str                      # Secret name
    old_version: Optional[str]     # Previous version
    new_version: str               # New version
    rotated_at: datetime           # When rotation detected
```

### Exceptions

```python
class SecretsError(Exception):
    """Base exception for secrets module."""

class SecretNotFoundError(SecretsError):
    """Secret does not exist."""

class ProviderError(SecretsError):
    """Provider communication failed."""

class ProviderNotConfiguredError(SecretsError):
    """Requested provider not configured."""

class CacheError(SecretsError):
    """Cache operation failed."""
```

## Best Practices

1. **Use named sources** - Define secrets in configuration rather than hardcoding paths
2. **Enable caching** - Provides resilience when providers are temporarily unavailable
3. **Use AppRole or K8s auth** - Avoid long-lived tokens in production
4. **Separate secrets from config** - Keep secrets in dedicated sources (Vault, AWS SM)
5. **Monitor rotation events** - React to credential changes appropriately
6. **Test provider failover** - Verify stale cache fallback works as expected

## Troubleshooting

### Debug Mode

```bash
export HYPERI_SECRETS_DEBUG=1
python app.py

# Output:
# SecretsManager: Initializing with 3 sources
# FileProvider: Loaded /secrets/tls/cert.pem (2048 bytes)
# OpenBaoProvider: Authenticating with approle
# OpenBaoProvider: Fetched secret/data/myapp/api v3
# Cache: Stored api_credentials (ttl=3600s)
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `ProviderNotConfiguredError` | Ensure provider config is present and install extras (`uv add hyperi-pylib[secrets-vault]`) |
| `SecretNotFoundError` | Verify secret path/name exists in provider |
| Vault auth failing | Check role_id/secret_id, verify AppRole policy |
| AWS auth failing | Verify IAM permissions, check region setting |
| Stale cache not working | Ensure cache directory is writable, check grace period |

