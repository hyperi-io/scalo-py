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

## Current Status (2025-12-30)

**Versions:**

- hs-pylib: v2.13.6
- hs-ci: v1.37.0 (GitHub Actions architecture)

**Build type:** Native wheel only (no Nuitka)

---

## Current Session (2025-12-30)

### Accomplished

1. **Application framework removed** - Deleted 2,656 lines of unused code
   - `src/hs_pylib/application/` (API, CLI, Daemon, MCP, Oneshot types)
   - Associated tests removed
   - Zero production usage across dfe-* projects

2. **Kafka Docker testing infrastructure**
   - Created `docker-compose.kafka.yml` (Apache Kafka 3.9.0, KRaft mode, no ZooKeeper)
   - Updated `.env` with remote Kafka config (k8s.tyrell.com.au:30092, SASL_PLAINTEXT)
   - Smart fixtures in `conftest.py`:
     - `kafka_config` - tries remote, falls back to Docker
     - `kafka_config_local_only` - forces Docker only
     - Auto-starts Docker Kafka if needed
     - Tracks `_kafka_started_by_tests` to only cleanup what we started
     - Unique project name `hs-pylib-test` avoids conflicts

3. **Unit tests for Kafka fixtures** - 19 new tests
   - `tests/unit/test_conftest_kafka_fixtures.py`
   - Tests connection checking, container detection, config env logic

4. **Fixed CI runner issue**
   - Org-level `GH_RUNNER_DEFAULT` was set to `buildjet-4vcpu-ubuntu-2204` (BuildJet unavailable)
   - Set repo-level `GH_RUNNER_DEFAULT=ubuntu-latest` for hs-pylib
   - CI now runs on GitHub-hosted runners

5. **Published v2.13.6 to JFrog PyPI**
   - CI passed, Semantic Release created tag
   - Package at: `hypersec.jfrog.io/artifactory/hypersec-pypi-local/hs-pylib/2.13.6/`

### Key Files Modified

- `docker-compose.kafka.yml` - New: Local Kafka for integration testing
- `tests/conftest.py` - Added Kafka fixtures with Docker fallback
- `tests/unit/test_conftest_kafka_fixtures.py` - New: 19 unit tests for fixtures
- `tests/integration/test_kafka_docker_fallback.py` - New: Docker fallback tests
- `tests/integration/test_kafka_integration.py` - Updated docstring
- `.env` - Updated Kafka config (k8s.tyrell.com.au:30092)
- `src/hs_pylib/application/` - Deleted (unused framework)
- Various source files - Minor cleanups

### Decisions Made

- **DO NOT use Bitnami images** - User explicitly requested "never use Bitnami EVER"
- **Apache Kafka official image** - `apache/kafka:3.9.0` for local testing
- **BuildJet runners unavailable** - Using `ubuntu-latest` via repo-level variable override
- **Python >= 3.12 only** - Using `Python :: 3 :: Only` classifier, no version-specific classifiers

### Git State

- **Branch:** main
- **Upstream:** Up to date with origin/main
- **Uncommitted:** Clean
- **Latest commits:**
  - `c916a92` fix: remove unused application framework, add Kafka Docker testing
  - `5b66016` chore: version 2.13.5 [skip ci]
  - `ae3d339` fix: add faker to dev dependencies for integration tests

### Session Context Summary

Removed unused application framework (~2,700 LOC) and added Docker Kafka testing infrastructure. The integration tests now auto-detect remote Kafka from .env, falling back to local Docker if unavailable. Fixed BuildJet runner issue by setting repo-level GH_RUNNER_DEFAULT. Published v2.13.6 to JFrog.

---

## Previous Session (2025-12-05)

### Completed: hs_pylib.kafka Module

**Branch:** `feat/DFE-553/add-kafka-library`
**Commit:** `2a9b38b`
**Files:** 16 files, 7505 insertions

Implemented complete Kafka client library:

- **Core clients:** KafkaClient, KafkaConsumer, KafkaProducer
- **Async variants:** AsyncKafkaClient, AsyncKafkaConsumer, AsyncKafkaProducer
- **Admin (KafkaAdmin):** Topic config, retention, cleanup, partition management
- **Offset reset:** `reset_offsets_to_timestamp()`, `reset_offsets_to_earliest()`, `reset_offsets_to_latest()`
- **Utilities:** SchemaAnalyser (JSON inference), sampling (reservoir, time-bounded)
- **Metrics:** KafkaMetricsCollector (librdkafka stats → Prometheus)
- **Config:** File loading (.properties, .json, .yaml, .ini), env vars (KAFKA_*)

**Tests:** 160 unit tests + 19 integration tests (faker data)

**Backlog documented:** JSON key-value offset seek (in admin.py:552-582)

---

## Planned: PostgreSQL Cache Backend

**Status:** Design Complete - Ready for Implementation
**Target Version:** v2.14.0
**Consumer:** dfe-engine Query Gateway API

### Purpose

Extend `hs_pylib.cache` to support PostgreSQL as a cache backend for multi-pod deployments. The existing disk-backed cache (cashews + SQLite) is local to each pod and cannot be shared. PostgreSQL provides a shared cache accessible by all pod instances without adding Redis to the infrastructure.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **No Redis** | PostgreSQL only | Simpler infrastructure, already in stack |
| **PostgreSQL library** | psycopg3 | Already in dependencies, excellent async support |
| **Storage format** | BYTEA + msgpack | Fast, compact, supports any Python type |
| **Expiration** | Lazy + scheduled cleanup | Balance of simplicity and cleanliness |
| **Cashews integration** | Standalone module | Simpler, purpose-built, easier to maintain |
| **Upsert pattern** | ON CONFLICT DO UPDATE | Atomic, safe for multi-pod concurrency |
| **Connection pooling** | psycopg_pool.AsyncConnectionPool | Built-in, no external dependency |

### Architecture

```
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
              │   - key (PK)          │
              │   - value (BYTEA)     │
              │   - expires_at        │
              │   - namespace         │
              │   - org_id            │
              └───────────────────────┘
```

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    namespace TEXT NOT NULL DEFAULT 'default',
    org_id TEXT,                              -- For tenant-scoped invalidation
    value BYTEA NOT NULL,                     -- msgpack-serialized data
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    hit_count INTEGER DEFAULT 0,
    size_bytes INTEGER
);

-- Indexes for efficient operations
CREATE INDEX idx_cache_expires ON cache_entries (expires_at);
CREATE INDEX idx_cache_namespace ON cache_entries (namespace);
CREATE INDEX idx_cache_org ON cache_entries (org_id);
CREATE INDEX idx_cache_ns_org ON cache_entries (namespace, org_id);
```

### Configuration (dfe-engine integration)

The Query Gateway selects cache backend via config cascade (env > config file > defaults):

```yaml
# dfe-engine defaults.yaml
cache:
  backend: "disk"                    # disk | postgres
  postgres_dsn: ""                   # postgresql://user:pass@host/db
  table_name: "cache_entries"
  default_ttl_seconds: 3600
  pool_min_size: 2
  pool_max_size: 10
```

```bash
# Environment variables (DFE_ prefix)
DFE_CACHE_BACKEND=postgres
DFE_CACHE_POSTGRES_DSN=postgresql://user:pass@host/db
DFE_CACHE_TABLE_NAME=cache_entries
DFE_CACHE_POOL_MIN_SIZE=2
DFE_CACHE_POOL_MAX_SIZE=10
```

**Backend selection logic:**
1. If `backend=postgres` and DSN provided → Use PostgresCache
2. If `backend=postgres` but no DSN → Fall back to disk with warning
3. If `backend=disk` → Use existing cashews disk cache

### API Design

```python
from hs_pylib.cache.postgres import PostgresCache, generate_cache_key

# Initialisation (at app startup)
cache = PostgresCache(
    dsn="postgresql://user:pass@host/db",
    table_name="cache_entries",      # Optional, default
    default_ttl_seconds=3600,        # 1 hour default
    pool_min_size=2,
    pool_max_size=10,
)
await cache.init()  # Creates table if not exists

# Basic operations
await cache.set(
    key="analytics:acme-corp:events_by_day:a1b2c3d4",
    value={"data": [...]},           # Any msgpack-serializable
    ttl_seconds=300,
    namespace="analytics",           # For grouped invalidation
    org_id="acme-corp",              # For tenant-scoped invalidation
)

value = await cache.get("analytics:acme-corp:events_by_day:a1b2c3d4")
# Returns None if not found or expired (lazy expiration)

exists = await cache.exists("key")
deleted = await cache.delete("key")

# Bulk invalidation
count = await cache.invalidate_by_prefix("analytics:")
count = await cache.invalidate_by_namespace("analytics")
count = await cache.invalidate_by_namespace("analytics", org_id="acme-corp")
count = await cache.invalidate_by_org("acme-corp")

# Maintenance (run via scheduler, e.g., every 5 min)
deleted = await cache.cleanup_expired()

# Statistics
stats = await cache.stats()
# {"entry_count": 1234, "total_size_bytes": 5678, "namespaces": {...}}

# Key generation helper
key = generate_cache_key(
    namespace="analytics",
    identifier="events_by_day",
    org_id="acme-corp",
    params={"start": "2025-01-01", "end": "2025-01-15"},
)
# Returns: "analytics:acme-corp:events_by_day:a1b2c3d4e5f6g7h8"

# Cleanup (at app shutdown)
await cache.close()
```

### Query Gateway Integration

The dfe-engine Query Gateway will use this cache as specified in [QUERY-API.md](../dfe-engine/docs/QUERY-API.md):

```yaml
# Query definition with cache config
queries:
  events_by_day:
    store: clickhouse
    cache:
      enabled: true
      ttl_seconds: 300
      vary_by:
        - org_id
        - start_time
        - end_time
```

Cache key generated from query definition:
```python
key = generate_cache_key(
    namespace=query_def.store,           # "clickhouse"
    identifier=query_id,                 # "events_by_day"
    org_id=params["org_id"],
    params={k: params[k] for k in query_def.cache.vary_by},
)
```

### Concurrency Safety

PostgreSQL's `ON CONFLICT DO UPDATE` provides atomic upsert:

```python
async def set(self, key: str, value: Any, ttl_seconds: int, ...):
    """Atomic upsert - safe for concurrent multi-pod access."""
    async with self._pool.connection() as conn:
        await conn.execute("""
            INSERT INTO cache_entries
                (cache_key, namespace, org_id, value, expires_at, size_bytes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE SET
                value = EXCLUDED.value,
                expires_at = EXCLUDED.expires_at,
                hit_count = 0,
                size_bytes = EXCLUDED.size_bytes
        """, (key, namespace, org_id, data, expires_at, size_bytes))
```

### Expiration Strategy

**Hybrid approach:**
1. **Lazy expiration on read:** Check `expires_at` when getting, return None if expired
2. **Scheduled cleanup:** Run `cleanup_expired()` periodically (e.g., every 5 min)

```python
async def get(self, key: str) -> Any | None:
    row = await conn.fetchrow(
        "SELECT value, expires_at FROM cache_entries WHERE cache_key = %s",
        (key,),
    )
    if row is None:
        return None
    if row['expires_at'] < datetime.now(UTC):
        # Expired - fire-and-forget delete
        asyncio.create_task(self.delete(key))
        return None
    # Update hit count (don't await, non-critical)
    asyncio.create_task(self._increment_hit_count(key))
    return msgpack.unpackb(row['value'])
```

### Performance Considerations

| Scenario | PostgreSQL Cache | Notes |
|----------|------------------|-------|
| Read latency | ~1-5ms | Acceptable for query caching |
| Write latency | ~2-10ms | Acceptable |
| Throughput | ~10K-50K ops/sec | Sufficient for dfe-engine |
| Consistency | Strong (ACID) | Better than Redis eventual |

**When PostgreSQL cache is appropriate:**
- Already have PostgreSQL in stack ✓
- Query caching (not session/token cache)
- Multi-pod shared state required
- <50K ops/sec
- Latency tolerance >1ms

### Dependencies

**New:**
- `msgpack>=1.0.0` - Efficient serialization

**Existing (already in pyproject.toml):**
- `psycopg[binary]>=3.2.0` - PostgreSQL async client

### Files to Create

```
src/hs_pylib/cache/
├── __init__.py          # Update exports
├── cache.py             # Existing (cashews disk cache)
└── postgres.py          # NEW: PostgresCache implementation
```

### Test Plan

**Unit tests** (`tests/unit/test_cache_postgres.py`):
- Import tests
- Key generation
- TTL parsing
- Mock-based operation tests

**Integration tests** (`tests/integration/test_cache_postgres.py`):
- Requires PostgreSQL (Docker fixture like Kafka)
- Full CRUD operations
- Expiration handling
- Concurrent access
- Bulk invalidation

### Implementation Steps

1. Add `msgpack` to optional dependencies: `cache = ["cashews[diskcache]>=7.0.0", "msgpack>=1.0.0"]`
2. Create `src/hs_pylib/cache/postgres.py` with `PostgresCache` class
3. Update `src/hs_pylib/cache/__init__.py` exports
4. Add `docker-compose.postgres.yml` for testing (or reuse existing)
5. Write unit tests
6. Write integration tests
7. Run `ruff check`, `ruff format`, `pytest`
8. Commit with `feat: add PostgreSQL cache backend for multi-pod deployments`
9. Push → CI → Semantic Release → v2.14.0

---

## Active Work Scope

**Source:** `/projects/dfe-control-plane/HS-LIB-UPDATE.md`

This file is the **living scope document** for hs-pylib improvements. It is maintained in the dfe-control-plane project during integration testing and will be updated as work progresses.

**Current priorities (from HS-LIB-UPDATE.md):**

1. `hs_pylib.http` - HttpClient with Stamina retries (solves B113, adds observability)
2. `hs_pylib.metrics.fastapi` - Middleware + router for standard /metrics
3. `hs_pylib.metrics.db` - DB query metrics helpers
4. `hs_pylib.cache` - Deferred until needed

**Always re-read HS-LIB-UPDATE.md at session start** - it may have changed.

---

## CI Architecture (hs-ci v1.37.x)

**IMPORTANT:** hs-ci was completely rewritten. No more `./ci/run` scripts.

### Key Changes from Old CI

| Old (v1.11.x) | New (v1.19.x) |
|---------------|---------------|
| `./ci/run check` | GitHub Actions workflows |
| `./ci/run build` | GitHub Actions workflows |
| `./ci/bootstrap install` | GitHub Actions setup actions |
| `ci.yaml` | `.hypersec-ci.yaml` |
| Python scripts in `modules/` | Composable GitHub Actions in `actions/` |

### Configuration

**Single source:** `.hypersec-ci.yaml` (not `ci.yaml`, not `pyproject.toml`)

**Precedence:** env vars (`HYPERCI_*`) > `.hypersec-ci.yaml` > `ci/defaults.yaml`

**Current hs-pylib config:**

```yaml
language: python
quality:
  enabled: true
test:
  enabled: true
  coverage: true
build:
  enabled: true
  strategies:
    - native    # Standard wheel only, no Nuitka
publish:
  enabled: true
python:
  source_dir: src
```

### Local Development

No `./ci/run` anymore. Use standard tools directly:

```bash
# Quality checks
ruff check src/ tests/
ruff format src/ tests/

# Tests
pytest tests/

# Build
uv build
```

### CI Pipeline Flow

```text
push → CI workflow (quality → test → build)
tag  → Semantic Release → Publish workflow
```

### Runner Configuration

**Org-level:** `GH_RUNNER_DEFAULT=buildjet-4vcpu-ubuntu-2204` (BuildJet - currently unavailable)
**Repo-level (hs-pylib):** `GH_RUNNER_DEFAULT=ubuntu-latest` (overrides org setting)

### Attach/Update CI

```bash
# Update ci submodule
git -C ci fetch origin main
git -C ci reset --hard origin/main
git add ci && git commit -m "chore: update ci submodule"

# Regenerate workflows
./ci/attach.sh --force
```

---

## Architecture Notes

### hs-ci Release System

**hs-ci itself:** semantic-release CLI + .releaserc.json (Node.js)
**Projects using hs-ci:** GitHub Actions workflows (ci.yml, publish.yml, semantic-release.yml)

### Test Projects

- `/projects/ci/tests/external/projects/python/` - Python test projects
- ci-test-simple-cli, ci-test-simple-package

---

## Quick Reference

**Python requirement:** 3.12+

**Local commands:**

```bash
ruff check src/ tests/       # Lint
ruff format src/ tests/      # Format
pytest tests/                # Test
uv build                     # Build wheel
```

**Update ci submodule:**

```bash
git -C ci reset --hard origin/main
./ci/attach.sh --force
git add ci .github/ .hypersec-ci.yaml .releaserc.json
git commit -m "chore: update ci submodule to vX.Y.Z"
```

---

**Last Updated:** 2025-12-30
