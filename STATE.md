# hyperi-pylib - Project State

**Repository**: <https://github.com/hyperi-io/hyperi-pylib>
**Type**: Python package (shared library)
**Purpose**: Enterprise infrastructure for all HyperI Python projects

---

## Session Management

**New session?** Run `/start` to initialise (reads STATE.md, TODO.md, standards)
**Save progress:** Run `/save` to checkpoint

### Local Development

```bash
make quality               # Lint, type-check, security audit
make test                  # Run test suite
make build                 # Build wheel
```

Requires `hyperi-ci` CLI: `uv tool install hyperi-ci`

CI runs via `hyperi-io/hyperi-ci` reusable GitHub Actions workflow — no submodule.

---

**Build type:** Native wheel only (no Nuitka)

---

## Architecture: PostgreSQL Cache Backend

```text
┌─────────────────────────────────────────────────────────┐
│                    Application (dfe-engine)             │
│  ┌─────────────────────────────────────────────────┐   │
│  │         PostgresCache (hyperi-pylib)                │   │
│  │  ┌─────────────┐  ┌─────────────────────────┐   │   │
│  │  │ Serializer  │  │ AsyncConnectionPool     │   │   │
│  │  │ (msgpack)   │  │ (psycopg3)              │   │   │
│  │  └─────────────┘  └─────────────────────────┘   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │  Pod A  │      │  Pod B  │      │  Pod C  │
    └────┬────┘      └────┬────┘      └────┬────┘
         └────────────────┼────────────────┘
                          ▼
              ┌───────────────────────┐
              │      PostgreSQL       │
              │   cache_entries       │
              └───────────────────────┘
```

### API Usage

```python
from hyperi_pylib.cache import PostgresCache, generate_cache_key

cache = PostgresCache(dsn="postgresql://user:pass@host/db")
await cache.init()

key = generate_cache_key("analytics", "events", org_id="acme")
await cache.set(key, {"data": [...]}, ttl_seconds=300, namespace="analytics")
value = await cache.get(key)

await cache.close()
```

---

## CI Architecture

CI uses `hyperi-io/hyperi-ci` reusable GitHub Actions workflows. No local submodule.

### Configuration

**Single source:** `.hyperi-ci.yaml`

### Publish

Publishes to **public PyPI** (`publish-target: oss`).

### Runner Configuration

**Org-level:** `GH_RUNNER_DEFAULT=arc-runner-16cpu` (ARC self-hosted runners)
**No repo-level override** — inherits org setting

### Update CI Config

Only `.hyperi-ci.yaml` needs editing — workflow files are managed by `hyperi-ci`.

---

## Architecture: DfeApp CLI Framework

Mirrors rustlib's `cli::app` module. Python DFE services subclass `DfeApp` to get
standard CLI lifecycle for free (80% boilerplate, 20% app logic).

```python
from hyperi_pylib.cli import DfeApp, VersionInfo

class MyService(DfeApp):
    name = "dfe-control-plane"
    env_prefix = "DFE_CP"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "1.0.0")

    def run_service(self, config) -> None:
        ...  # sync

    async def run_service_async(self, config) -> None:
        ...  # or async

if __name__ == "__main__":
    MyService().cli()
```

**Standard subcommands:** `run`, `version`, `config-check`
**No `top` command** — Python is never on the hot path (that's Rust)
**Config:** Always uses `hyperi_pylib.config` cascade (Dynaconf), not bespoke loading

---

## Quick Reference

**Python requirement:** 3.12+

**Local commands:**

```bash
make quality    # Lint, type-check, security audit
make test       # Run test suite
make build      # Build wheel
```

**CI config:** `.hyperi-ci.yaml` — edit to adjust quality/publish settings.

---

## Active Work: Secrets Abstraction — Plan 4 (deferred)

**Current state (v2.27.0):** Plans 1-3 shipped. File and Ansible Vault providers have full
list/CRUD/metadata support. Cloud providers (OpenBao, AWS, GCP, Azure) still have
`NotImplementedError` stubs for the new methods — reads via `get()`/`get_sync()` still work
exactly as before.

**Plan 4 (next):** Replace cloud provider stubs with real SDK implementations. **Deferred to
`desktop-derek` work VM** because it needs cloud creds that aren't on this machine.

**Resume checklist — on desktop-derek:**

1. `git pull` latest main (should be v2.27.0+).
2. Place cloud creds in `.env` (gitignored): `VAULT_ADDR`, `VAULT_TOKEN`, AWS keys, GCP service account path, Azure SP.
3. Read `TODO.md` → "Secrets Abstraction Extensions — Plan 4 (Cloud Providers)" for full details.
4. Read spec: `docs/superpowers/specs/2026-04-10-secrets-abstraction-extensions-design.md`.
5. Implement in order: **OpenBao → AWS → GCP → Azure** (easiest → hardest).
6. Target: **v2.28.0** (minor bump).

**Safe dev path for OpenBao:** use devex infra VM at `https://10.66.0.101:8200` — it's the
internal OpenBao and already trusted.

**Safe dev path for AWS:** use [LocalStack](https://localstack.cloud/) or [moto](https://github.com/getmoto/moto)
instead of hitting real AWS — they both support Secrets Manager.

**Key design invariants (don't break these):**

- Cloud providers inherit from `VersionedProvider`, file providers from `SecretProvider`.
- `isinstance(p, VersionedProvider)` is the capability check in `SecretsManager.get_version` / `list_versions`.
- AWS `batch_get` should use native `batch_get_secret_value` — `SecretsManager.batch_get` already delegates via `hasattr(p, "batch_get_async")`.
- Map provider errors to: `SecretNotFoundError`, `SecretAlreadyExistsError`, `SecretPermissionError(provider, operation, path, hint)`, `SecretVersionNotFoundError`.

---

**Last Updated:** 2026-04-11
