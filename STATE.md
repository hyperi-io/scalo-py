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

**Last Updated:** 2026-03-04
