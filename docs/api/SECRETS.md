# Secrets

Unified async/sync secrets API across the supported providers — file, OpenBao,
HashiCorp Vault (same protocol as OpenBao), AWS Secrets Manager, GCP
Secret Manager, Azure Key Vault, and Ansible Vault. One `SecretsManager`
object, one configuration shape, two-tier caching, stale-grace fallback,
background refresh, and rotation callbacks.

```
pip install hyperi-pylib[secrets-vault]        # OpenBao / Vault
pip install hyperi-pylib[secrets-aws]          # AWS Secrets Manager
pip install hyperi-pylib[secrets-gcp]          # GCP Secret Manager
pip install hyperi-pylib[secrets-azure]        # Azure Key Vault
pip install hyperi-pylib[secrets-ansible-vault]  # Ansible Vault
```

File provider is always available — no extra install needed.

---

## Quick start

```python
from hyperi_pylib.secrets import SecretsManager

sm = SecretsManager.from_config({
    "openbao": {"address": "https://vault:8200", "auth": {"method": "token"}},
    "sources": {"db_password": {"provider": "openbao", "path": "secret/data/db", "key": "password"}},
})
password = await sm.get_string("db_password")
```

---

## Provider matrix

| Provider | Extra | Versioned | Native async | Server-side filter | Auth chain |
|----------|-------|-----------|--------------|--------------------|------------|
| `file` | (always available) | no | thread-pool | prefix only | n/a |
| `openbao` / `vault` | `secrets-vault` | yes (KV v2) | yes (httpx) | prefix + tags | token, approle, kubernetes |
| `aws` | `secrets-aws` | yes | yes (aiobotocore) | prefix + tags | boto3 default chain |
| `gcp` | `secrets-gcp` | yes | yes (async client) | prefix + labels | ADC |
| `azure` | `secrets-azure` | yes | yes (`azure.identity.aio`) | prefix + tags | `DefaultAzureCredential` or service principal |
| `ansible_vault` | `secrets-ansible-vault` | no | thread-pool | prefix + tags | password / password file |

OpenBao and HashiCorp Vault share the KV v2 protocol — the same provider
talks to both. Use the `openbao` provider for Vault too.

---

## Configuration

```python
sm = SecretsManager.from_config({
    "openbao": {
        "address": "https://vault:8200",
        "namespace": "team-a",
        "auth": {"method": "kubernetes", "role": "my-service"},
    },
    "aws": {"region": "ap-southeast-2"},
    "azure": {"vault_url": "https://my-vault.vault.azure.net/"},
    "cache": {
        "ttl_secs": 3600,
        "stale_grace_secs": 86400,
        "refresh_interval_secs": 1800,
        "encryption_key": "...",  # optional cache-at-rest encryption
    },
    "env_prefix": "MYSVC",
    "sources": {
        "db_password": {"provider": "openbao", "path": "secret/data/db", "key": "password"},
        "api_key":     {"provider": "aws",     "secret_id": "prod/api-key"},
        "tls_cert":    {"provider": "file",    "path": "/etc/ssl/cert.pem"},
    },
})
```

Env-var overrides for every provider — `VAULT_ADDR`, `VAULT_TOKEN`,
`AWS_REGION`, `GOOGLE_APPLICATION_CREDENTIALS`, `AZURE_VAULT_URL`,
`ANSIBLE_VAULT_PASSWORD`, etc. Cache settings respect
`HYPERI_SECRETS_CACHE_DIR`, `HYPERI_SECRETS_CACHE_TTL`,
`HYPERI_SECRETS_CACHE_KEY`.

---

## Reading secrets

Three call shapes:

```python
# Named source (recommended)
pw = await sm.get_string("db_password")

# Direct provider + path
val = await sm.get("secret/data/prod", key="token", provider="openbao")

# File path (backwards compatible)
cert = await sm.get_string("/etc/ssl/cert.pem")
```

Sync siblings exist for every method (`get_sync`, `get_string_sync`,
`list_sync`, …) — use them in startup code, signal handlers, or any
non-async context.

`SecretValue` carries the raw `data: bytes`, `fetched_at`, `version`
(for rotation detection), and `source` (provider name).

---

## ENV fallback

When a provider is unreachable, `SecretsManager` looks up an ENV
variable named after the source. Lookup order:

1. `source.env_fallback` (explicit override on the source config)
2. `{env_prefix}_{NAME.upper()}` if `SecretsManager(env_prefix=...)`
3. `NAME.upper()` (no prefix)

For `env_prefix="DFE"` and source `db_password`, the manager checks
`DFE_DB_PASSWORD`. Logged at WARN level so it shows up in dashboards.

---

## Caching

Two-tier: in-process memory cache (per-`SecretsManager`, class-level
shared) plus optional encrypted disk cache (Fernet, `[cache]` extra). On
provider failure the manager returns the cached value if still within
`stale_grace_secs` past TTL — your service keeps running through a
Vault outage.

```python
# Background refresh prevents cold-cache thundering herds
await sm.start_refresh()  # spawns asyncio task
...
await sm.stop_refresh()   # on shutdown
```

Background refresh adds jitter (`refresh_jitter_secs`, default 5 min) so
a fleet doesn't slam the secrets backend at the same instant.

---

## Rotation callbacks

```python
def on_rotate(event):
    logger.info("Secret rotated",
                name=event.name,
                old=event.old_version,
                new=event.new_version)
    reload_db_pool()

sm.on_rotation(on_rotate, names=["db_password"])  # None = all secrets
```

Triggered when the cached `SecretValue.version` differs from the freshly
fetched value. File provider derives version from `mtime:size`; cloud
providers use the native version ID.

---

## Versioning

OpenBao, AWS, GCP, Azure support per-version reads:

```python
old = await sm.get_version("secret/data/api-key", version="3", provider="openbao")
history = await sm.list_versions("secret/data/api-key", provider="openbao")
```

File and Ansible Vault providers raise `VersioningNotSupportedError`.

---

## CRUD

```python
await sm.create("secret/data/new-key", b"value", tags={"env": "prod"}, provider="openbao")
await sm.update("secret/data/new-key", b"rotated", provider="openbao")
await sm.delete("secret/data/old-key", provider="openbao")
```

Tags are server-side on cloud providers, ignored by file-based ones.
Writes raise `SecretAlreadyExistsError`, `SecretPermissionError`, or
`ProviderError` — never silently fail.

---

## Listing and filtering

```python
from hyperi_pylib.secrets import SecretFilter

paths = await sm.list(
    filter=SecretFilter(prefix="prod/", tags={"team": "data"}),
    provider="aws",
)
```

`prefix` is server-side on all cloud providers. `tags` is server-side on
AWS/GCP/Azure/OpenBao, ignored by file/ansible-vault. `pattern` is
client-side fnmatch.

`get_metadata(path, provider=...)` returns `SecretMetadata` without
fetching the value — `created_at`, `updated_at`, `expires_at`, `version`,
`version_count`, `tags`.

---

## Batch get

```python
secrets = await sm.batch_get(
    ["prod/db", "prod/cache", "prod/queue"],
    provider="aws",
)
```

AWS uses its native `BatchGetSecretValue` API. Other providers fall back
to `asyncio.gather` with per-item error isolation — failures are logged
and omitted from the result, not raised.

---

## Health

```python
status = await sm.health_check()
# {"file": True, "openbao": True, "aws": False}
```

Wire this into `health.register_ready_check(...)` to surface secrets-backend
outages in `/health/ready`.

---

## Exceptions

| Exception | When |
|-----------|------|
| `SecretsError` | base class |
| `SecretNotFoundError` | path doesn't exist |
| `ProviderError` | transport / API call failed |
| `ProviderNotConfiguredError` | requested provider not in `from_config` |
| `ProviderNotAvailableError` | provider extra not installed |
| `AuthenticationError` | provider auth failed |
| `SecretPermissionError` | read-only token tried a write |
| `SecretAlreadyExistsError` | `create()` on existing path |
| `SecretVersionNotFoundError` | `get_version()` for unknown version |
| `VersioningNotSupportedError` | versioned op on file/ansible-vault |
| `CacheError` | disk cache I/O failed |

---

## Lifecycle

```python
sm = SecretsManager.from_config(settings.get("secrets"))
await sm.start_refresh()      # at startup
...
await sm.close()              # on SIGTERM (closes providers + stops refresh)
```

`close()` releases httpx clients, aiobotocore sessions, Azure
credentials, and joins the refresh task.

---

## Related

- [../INTEGRATION.md](../INTEGRATION.md)
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
- [HTTP-CLIENT.md](HTTP-CLIENT.md)
- [CACHE.md](CACHE.md)
- [CONCURRENCY.md](CONCURRENCY.md)
- [RESILIENCE.md](RESILIENCE.md)
