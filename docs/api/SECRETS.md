# Secrets

Unified async/sync secrets API across the supported providers — file, OpenBao,
HashiCorp Vault (same protocol as OpenBao), AWS Secrets Manager, GCP
Secret Manager, Azure Key Vault, and Ansible Vault. One `SecretsManager`
object, one configuration shape, two-tier caching, stale-grace fallback,
background refresh, and rotation callbacks.

```bash
pip install scalo[secrets-vault]        # OpenBao / Vault
pip install scalo[secrets-aws]          # AWS Secrets Manager
pip install scalo[secrets-gcp]          # GCP Secret Manager
pip install scalo[secrets-azure]        # Azure Key Vault
pip install scalo[secrets-ansible-vault]  # Ansible Vault
```

File provider is always available — no extra install needed.

---

## Quick start

```python
from scalo.secrets import SecretsManager

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
        "enabled": True,  # False turns off the memory and disk tiers
        "ttl_secs": 3600,
        "stale_grace_secs": 86400,
        "refresh_interval_secs": 1800,
        "encryption_key": "...",  # seals disk entries; without it the disk tier is off
        "allow_plaintext_disk_cache": False,  # True permits unencrypted disk entries; refused in production
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
`AWS_REGION`, `AWS_DEFAULT_REGION`, `GOOGLE_APPLICATION_CREDENTIALS`, `AZURE_VAULT_URL`,
`ANSIBLE_VAULT_PASSWORD`, etc. Cache settings respect
`SECRETS_CACHE_DIR`, `SECRETS_CACHE_TTL`,
`SECRETS_CACHE_KEY`.

### A provider whose SDK is not installed

A provider named in the config whose extra is not installed is logged at WARN and left out, and `from_config` still returns. Using it then raises `ProviderNotConfiguredError`, and a named source falls back to ENV (see [ENV fallback](#env-fallback)). Building the provider directly raises `ProviderNotAvailableError`. A provider whose SDK is present but whose config is bad, such as Ansible Vault with no password, still raises from `from_config`.

### AWS region, KMS key and deletion window

The region comes from `aws.region`, then `AWS_REGION`, then `AWS_DEFAULT_REGION`. With none set the SDK reads the active profile's region. With no profile region every call fails, because botocore cannot build a client without one (`NoRegionError`). There is no default region.

```python
sm = SecretsManager.from_config({
    "aws": {
        "region": "ap-southeast-2",
        "kms_key_id": "alias/my-service",  # unset = the AWS managed key
        "recovery_window_days": 0,         # unset = AWS default (30), 0 = no recovery, or 7-30
    },
})
```

`kms_key_id` takes a key ID, ARN or alias and encrypts each secret the provider creates. A secret that already exists keeps its key.

`recovery_window_days` applies to `delete()`. Unset, AWS keeps a deleted secret recoverable for 30 days. `0` deletes it with no recovery, and 7-30 sets the window. Any other value is refused when the config is built. Inside the window a read, update or create of the name raises `SecretPendingDeletionError`.

A forced delete (`0`) also completes asynchronously on AWS. The DeleteSecret reference says Secrets Manager performs it "with an asynchronous background process", so a `create()` of the same name straight after can be refused for a short while, and AWS says to back off and retry. scalo does not retry. A caller that deletes and re-creates a name retries on `SecretPendingDeletionError`. Reference: <https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_DeleteSecret.html>

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

For `env_prefix="APP"` and source `db_password`, the manager checks
`APP_DB_PASSWORD`. Logged at WARN level so it shows up in dashboards.

---

## Caching

Two tiers: an in-process memory cache, one per `SecretsManager` instance, and a disk cache. Both expire on `ttl_secs`. On provider failure the manager returns the most recent cached value from either tier while it is within `stale_grace_secs` past TTL, so your service keeps running through a secrets-backend outage.

The disk tier writes only when `encryption_key` is set, which seals each entry with AES-256-GCM (via the `cryptography` package; there is no `[cache]` extra), or when `allow_plaintext_disk_cache` is True. Without either it is off, the cache is memory-only, and a plaintext file found in the cache directory is not read. The plaintext opt-in is ignored once `encryption_key` is set, and refused at startup when the app environment (`APP_ENV`, `ENVIRONMENT`, `ENV`) is `production` or `prod`.

`"enabled": False` turns off both tiers. Every read goes to the provider, nothing is held in memory or written to disk, there is no stale-grace fallback, and a provider failure raises. Use it where a secret rotates and a stale value is worse than an error.

```python
# Background refresh prevents cold-cache thundering herds
await sm.start_refresh()  # spawns asyncio task
...
await sm.stop_refresh()   # on shutdown
```

Background refresh adds jitter (`refresh_jitter_secs`, default 5 min) so
a fleet doesn't slam the secrets backend at the same instant.

Each refresh re-reads every secret held in the memory cache from its provider, fresh entries included, replaces the cached value and reports any rotation it finds. A secret whose provider fails keeps its cached value, and the failure is logged. With `"enabled": False` the memory cache is empty, so there is nothing to refresh.

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

Triggered when the cached and the freshly fetched `SecretValue.version` are both set and differ. A value with no version never reports a rotation. File provider derives version from `mtime:size`; cloud
providers use the native version ID.

With `"enabled": False` there is no cached version to compare against, so no rotation event fires.

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

The file provider writes each secret file as `0600` and makes any missing directory `0700`, whatever the umask. An update sets an existing file to `0600` before it writes, so updating a file the process does not own raises `SecretPermissionError` and leaves the file as it was.

On AWS, `delete()` follows `recovery_window_days` (see [AWS region, KMS key and deletion window](#aws-region-kms-key-and-deletion-window)).

---

## Listing and filtering

```python
from scalo.secrets import SecretFilter

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
outages in `/readyz`.

---

## Exceptions

| Exception | When |
|-----------|------|
| `SecretsError` | base class |
| `SecretNotFoundError` | path doesn't exist |
| `ProviderError` | transport / API call failed, including an OpenBao login that could not reach the server or got a 429, 3xx or 5xx |
| `ProviderNotConfiguredError` | requested provider not in `from_config`, including one left out for a missing SDK |
| `ProviderNotAvailableError` | provider extra not installed, raised by the provider's constructor and caught by `from_config`, which logs a warning and leaves the provider out |
| `AuthenticationError` | the provider refused the credentials, for OpenBao a 400-499 login answer other than 429 (a `ProviderError` subclass, so catch it first) |
| `SecretPermissionError` | read-only token tried a write |
| `SecretPendingDeletionError` | AWS: the secret is inside its deletion recovery window, so its name can be neither read nor reused (a `ProviderError` subclass) |
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
- [CONCURRENCY.md](CONCURRENCY.md)
- [RESILIENCE.md](RESILIENCE.md)
