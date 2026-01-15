# hs-pylib - Project State

**Repository**: <https://github.com/hypersec-io/hs-pylib>
**Type**: Python package (shared library)
**Purpose**: Enterprise infrastructure for all HyperSec Python projects

---

## Session Management

**New session?** Run `/start` to initialise (reads STATE.md, TODO.md, standards)
**Save progress:** Run `/save` to checkpoint

### IMPORTANT: Local Build

**ALWAYS use the CI local build script for QA checks:**

```bash
ci/scripts/local/build-local.sh
```

Do NOT manually run ruff/pyright/pytest individually - use the CI script which runs the full validation pipeline.

---

## Current Status (2026-01-15)

**Versions:**

- hs-pylib: v2.14.0
- hs-ci: v1.37.0 (GitHub Actions architecture)

**Build type:** Native wheel only (no Nuitka)

---

## Current Session (2026-01-15)

### Accomplished

1. **PostgreSQL Cache Backend (v2.14.0)** - RELEASED
   - `PostgresCache` class with async connection pooling (psycopg3)
   - Automatic table creation with indexes
   - msgpack serialization for efficient storage
   - TTL-based expiration with lazy cleanup
   - Bulk invalidation by prefix, namespace, or org_id
   - Cache statistics and hit/miss metrics
   - `generate_cache_key()` helper for deterministic keys

2. **PostgreSQL Config Loader** - RELEASED
   - `PostgresConfigLoader` for shared configuration store
   - Integrates as layer 5 in 8-layer config cascade
   - Namespace isolation for multi-tenant deployments
   - Configurable cache TTL for performance
   - Sync and async loading modes
   - Automatic table/index creation

3. **Testing Infrastructure**
   - `docker-compose.postgres.yml` for local PostgreSQL testing
   - PostgreSQL fixtures in `conftest.py` (auto-start Docker)
   - Unit tests: 31 for config loader, comprehensive for cache
   - Integration tests: 25 for config loader, 40+ for cache

4. **dfe-engine Updated**
   - Updated to `hs-pylib>=2.14.0`
   - Security fixes: urllib3 2.6.0→2.6.3, werkzeug 3.1.4→3.1.5

### Key Files Created/Modified

- `src/hs_pylib/cache/postgres.py` - NEW: PostgresCache implementation
- `src/hs_pylib/cache/__init__.py` - Updated exports for PostgresCache
- `src/hs_pylib/config/postgres_loader.py` - NEW: PostgresConfigLoader
- `src/hs_pylib/config/__init__.py` - Updated exports
- `src/hs_pylib/config/config.py` - Added layer 5 integration
- `docker-compose.postgres.yml` - NEW: Local PostgreSQL for testing
- `tests/conftest.py` - Added PostgreSQL fixtures
- `tests/unit/test_cache_postgres.py` - NEW: Unit tests
- `tests/unit/test_config_postgres_loader.py` - NEW: Unit tests
- `tests/integration/test_cache_postgres.py` - NEW: Integration tests
- `tests/integration/test_config_postgres_loader.py` - NEW: Integration tests

### Git State

- **Branch:** main
- **Upstream:** Up to date with origin/main
- **Latest commits:**
  - `1afee67` chore: version 2.14.0 [skip ci]
  - `6d09b2d` feat: add PostgreSQL cache and config backends for multi-pod deployments

---

## Previous Session (2025-12-30)

### Completed: Kafka Docker Testing & Application Framework Cleanup

- Created `docker-compose.kafka.yml` (Apache Kafka 3.9.0, KRaft mode)
- Smart fixtures in `conftest.py` with remote/Docker fallback
- Removed unused application framework (~2,700 LOC)
- Fixed BuildJet runner issue (repo-level override to ubuntu-latest)
- Published v2.13.6

---

## Architecture: PostgreSQL Cache Backend

```text
┌─────────────────────────────────────────────────────────┐
│                    Application (dfe-engine)             │
│  ┌─────────────────────────────────────────────────┐   │
│  │         PostgresCache (hs-pylib)                │   │
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
from hs_pylib.cache import PostgresCache, generate_cache_key

cache = PostgresCache(dsn="postgresql://user:pass@host/db")
await cache.init()

key = generate_cache_key("analytics", "events", org_id="acme")
await cache.set(key, {"data": [...]}, ttl_seconds=300, namespace="analytics")
value = await cache.get(key)

await cache.close()
```

---

## CI Architecture (hs-ci v1.37.x)

**IMPORTANT:** hs-ci was completely rewritten. No more `./ci/run` scripts.

### Configuration

**Single source:** `.hypersec-ci.yaml` (not `ci.yaml`, not `pyproject.toml`)

### Local Development

Use CI local build script:

```bash
ci/scripts/local/build-local.sh
```

### Runner Configuration

**Org-level:** `GH_RUNNER_DEFAULT=buildjet-4vcpu-ubuntu-2204` (BuildJet - currently unavailable)
**Repo-level (hs-pylib):** `GH_RUNNER_DEFAULT=ubuntu-latest` (overrides org setting)

---

## Quick Reference

**Python requirement:** 3.12+

**Local commands:**

```bash
ci/scripts/local/build-local.sh   # Full QA + build
```

**Update ci submodule:**

```bash
git -C ci reset --hard origin/main
./ci/attach.sh --force
git add ci .github/ .hypersec-ci.yaml .releaserc.json
git commit -m "chore: update ci submodule to vX.Y.Z"
```

---

**Last Updated:** 2026-01-15
