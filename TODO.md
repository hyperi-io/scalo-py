# hs-pylib TODO

## Active

### Debug GitHub Actions bootstrap failures - **2h** 🟡

**Status:** HS_CI_PAT works for checkout, bootstrap failing

**Problem:**

- uv sync/lock/build fail in GitHub Actions environment
- Works locally with same configuration
- May be env var propagation or uv version differences

**Next:**

- Verify UV_INDEX_JFROG credentials actually set in GHA environment
- Check if --index-strategy flags working in GHA
- Consider sourcing .env before bootstrap or different export method

### Skip standard build matrix entry for apps - **0.5h**

**Status:** Apps shouldn't have standard-any build job at all

**Task:**

- Update matrix generation in workflow to skip standard build when build_type: app
- Only include Nuitka builds (x64, arm64) for apps
- Standard build only for packages

### Replace HS_CI_PAT with GitHub App token - **4h**

**Status:** PAT is user-tied, need corporate solution

**Task:**

- Create GitHub App for CI with contents:read permission
- Use actions/create-github-app-token@v1 in workflows
- Update all workflows to use app token
- Remove HS_CI_PAT secret

---

### PostgreSQL Cache Backend - **12h** 🔵

**Status:** Design complete in STATE.md, ready for implementation
**Target Version:** v2.14.0
**Consumer:** dfe-engine Query Gateway API

**Purpose:** Extend `hs_pylib.cache` with PostgreSQL backend for multi-pod shared caching (no Redis).

**Requirements:**
- Cache backend selectable via config/env: `DFE_CACHE_BACKEND=disk|postgres`
- PostgreSQL DSN from config cascade: `DFE_CACHE_POSTGRES_DSN`
- Fallback to disk cache if postgres unavailable

#### Phase 1: Setup and Dependencies

- [ ] **1.1** Update pyproject.toml - add `msgpack>=1.0.0` and `psycopg[binary,pool]>=3.2.0` to cache extras
- [ ] **1.2** Create `docker-compose.postgres.yml` following Kafka pattern (postgres:17-alpine)

#### Phase 2: Core Implementation

- [ ] **2.1** Create `src/hs_pylib/cache/postgres.py` with `PostgresCache` class
  - Constructor with dsn, table_name, ttl, pool sizes
  - `PostgresCacheError` exception
- [ ] **2.2** Implement lifecycle methods: `init()`, `close()`, async context manager
- [ ] **2.3** Implement CRUD: `get()`, `set()`, `delete()`, `exists()`
  - Lazy expiration on get
  - ON CONFLICT DO UPDATE for atomic upsert
  - msgpack serialization
- [ ] **2.4** Implement bulk invalidation: `invalidate_by_prefix()`, `invalidate_by_namespace()`, `invalidate_by_org()`
- [ ] **2.5** Implement maintenance: `cleanup_expired()`, `stats()`
- [ ] **2.6** Implement helper: `generate_cache_key(namespace, identifier, org_id, params)`

#### Phase 3: Module Integration

- [ ] **3.1** Update `src/hs_pylib/cache/__init__.py` - add conditional exports for PostgresCache

#### Phase 4: Testing Infrastructure

- [ ] **4.1** Add PostgreSQL fixtures to `tests/conftest.py` following Kafka pattern
  - `postgres_dsn` fixture with Docker fallback
  - `postgres_available` fixture
  - Docker startup/cleanup

#### Phase 5: Unit Tests

- [ ] **5.1** Create `tests/unit/test_cache_postgres.py`
- [ ] **5.2** Import tests
- [ ] **5.3** `generate_cache_key` tests (deterministic, params hashing)
- [ ] **5.4** Constructor tests
- [ ] **5.5** Mock-based operation tests

#### Phase 6: Integration Tests

- [ ] **6.1** Create `tests/integration/test_cache_postgres.py`
- [ ] **6.2** Lifecycle tests (init, context manager, close)
- [ ] **6.3** CRUD tests (string, dict, list, overwrite)
- [ ] **6.4** Expiration tests (lazy delete, cleanup)
- [ ] **6.5** Bulk invalidation tests
- [ ] **6.6** Stats tests
- [ ] **6.7** Concurrency tests (parallel writes)

#### Phase 7: Quality Assurance

- [ ] **7.1** Run `ruff check` and `ruff format`
- [ ] **7.2** Run `pyright`
- [ ] **7.3** Run unit tests: `pytest tests/unit/test_cache_postgres.py -v`
- [ ] **7.4** Run integration tests with Docker PostgreSQL
- [ ] **7.5** Run full test suite

#### Phase 8: Release and Integration

- [ ] **8.1** Commit: `feat: add PostgreSQL cache backend for multi-pod deployments`
- [ ] **8.2** Push and verify CI passes, Semantic Release creates v2.14.0
- [ ] **8.3** Update dfe-engine to use `hs-pylib>=2.14.0`

**Key Files:**

| File | Action |
|------|--------|
| `pyproject.toml` | Add cache extras deps |
| `docker-compose.postgres.yml` | Create new |
| `src/hs_pylib/cache/postgres.py` | Create new |
| `src/hs_pylib/cache/__init__.py` | Update exports |
| `tests/conftest.py` | Add PG fixtures |
| `tests/unit/test_cache_postgres.py` | Create new |
| `tests/integration/test_cache_postgres.py` | Create new |

**Design Reference:** See STATE.md section "Planned: PostgreSQL Cache Backend"

---

## Backlog

### Add hs_pylib.http.HttpClient (Stamina + httpx) - **3h**

**Status:** Not started - identified during dfe-control-plane B113 fixes

**Solution:** Wrap [Stamina](https://github.com/hynek/stamina) (by Hynek, attrs/structlog author) + httpx

**Task:**

- Create `hs_pylib.http.HttpClient` wrapping httpx + stamina
- Auto timeout (default 30s) - solves B113 bandit issues
- Auto retries with exponential backoff via stamina
- Stamina auto-detects structlog + prometheus-client

**Dependencies:**

```toml
"httpx>=0.27"
"stamina>=25.1"
```

**Rationale:**

- Stamina auto-integrates with hs_pylib.logger (structlog) and hs_pylib.metrics (prometheus)
- Testing friendly: `stamina.set_testing(attempts=1)` in pytest
- Same author as attrs/structlog - quality pedigree

**Design:** See dfe-control-plane/HS-LIB-UPDATE.md §4

### Add FastAPI metrics middleware to hs_pylib.metrics - **2h**

**Status:** Not started - identified during dfe-control-plane metrics work

**Task:**

- Create `hs_pylib.metrics.fastapi.PrometheusMiddleware`
- Auto-track: request count, duration, status by endpoint
- Create `hs_pylib.metrics.fastapi.create_metrics_router()` for `/metrics` endpoint
- Zero-config: `app.add_middleware(PrometheusMiddleware)`

**Rationale:**

- All FastAPI apps need HTTP metrics
- Currently each app implements manually
- Consistency across HyperSec apps

### Add DB query metrics helpers to hs_pylib.metrics - **1h**

**Status:** Not started - identified during dfe-control-plane metrics work

**Task:**

- Create context manager: `with metrics.db_query("postgres", "select"): ...`
- Create decorator: `@metrics.track_db_query(db_type="clickhouse")`
- Works with any DB client (not auto-instrumented)

**Rationale:**

- Multiple DB types (ClickHouse, Postgres, FalconDB)
- Can't auto-instrument all clients
- Explicit instrumentation is reliable

### [BACKLOG] hs_pylib.application: Application Framework - **deferred**

**Status:** Removed from hs-pylib v2.13.6, preserved in git history

**What was removed:**

- `src/hs_pylib/application/` - API, CLI, Daemon, MCP, Oneshot application types
- Profile-based configuration (dev, docker, prod)
- Health check mixins
- Signal handling

**Why removed:**

- Zero production usage across dfe-* projects (dfe-control-plane, dfe-engine, dfe-discovery, dfe-developer, dfe-cli-core, dfe-beats)
- 2,656 lines of experimental code
- Production apps use FastAPI/Typer directly with hs_pylib.metrics/logger/config

**Reactivation criteria:**

- When 2+ production apps need standardized application patterns
- When profile-based config provides value over direct configuration
- Branch: `feat/application-framework` (if created) or restore from git history

**Restore from:**

```bash
git show ae3d339:src/hs_pylib/application/ > application_backup.tar
```

---

### [BACKLOG] hs_pylib.kafka: JSON key-value offset seek - **2d**

**Status:** Backlog - documented in admin.py:552-582

**Task:** Implement `seek_to_json_match()` - seek to first message where nested JSON field matches value

**Considerations:**

- No index: Worst case is full topic scan
- Parallel partition search for performance
- Cancellation support via threading.Event
- Timeout handling to prevent hangs

---

## Backlog (CI/Build)

### Fix BuildJet runner availability - **1h**

**Status:** Org-level GH_RUNNER_DEFAULT set to BuildJet but runners not responding

**Current workaround:** hs-pylib uses repo-level override to `ubuntu-latest`

**Task:**

- Investigate BuildJet account/runner status
- Either fix BuildJet or update org-level variable to `ubuntu-latest`
- Consider using devex-runners when local runners are ready

### Allow null/none in ci.yaml to skip tests/linters - **1h**

**Status:** Add flexibility to completely disable checks

**Task:**

- Support `tests: null` or `tests.required: false` to skip all tests
- Support `linters: null` or `linters.required: false` to skip all linters
- Check/fix overlapping code in CI scripts for this logic
- Document in ci.yaml schema

### Fix vermin scan error - **0.5h**

**Status:** Non-blocking warning during linting

**Error:** `2025-11-19T00:38:09.191+1100 | ERROR | __main__:run_vermin_scan:75 - Failed to run vermin: %s`

**Task:**

- Check why vermin scan fails
- Fix or remove vermin if not needed
- Currently just shows warning, doesn't block

### Fix 61-update-badges.py local failure - **1h**

**Status:** Fails during local `./ci/run release`

**Task:**

- Investigate why badge update fails locally
- May need GitHub API credentials or just skip for local releases
- Low priority (doesn't affect GitHub Actions)

### Complete two-venv reference cleanup - **1h**

**Status:** Partially done, docs still need cleanup

**Task:**

- Fix remaining 12+ files in docs/ with ci-local/.venv references
- Update documentation to reflect unified .venv
- Files: docs/standards/, CONTRIBUTING.md, templates/

### Standardize ci_lib path injection - **2h**

**Status:** User wants simpler pattern (not full walk)

**Task:**

- 37 scripts currently use walk-up pattern for ci_lib
- Create simpler, consistent pattern
- Apply to all scripts uniformly

### Create test-package-build project - **2h**

**Status:** Need package mode testing (not just app mode)

**Task:**

- Create under hypersec-io org (private repo)
- Configure build_type: package (not app)
- Test Nuitka package mode (.so compilation)
- Verify compiled wheels work

### Document CI directory structure and naming conventions - **0.5h**

**Status:** Clarify architecture and naming patterns

**Task:**

- Document why we have ci/modules/python/tools vs hs-pylib package
- Explain .d directory pattern (bootstrap.d, run.d)
- Clarify naming: hs-pylib (package), hs-ci (CI system)
- Add architecture notes to STATE.md or separate doc

### Clean up deprecated CI directories - **0.5h**

**Status:** Audit and remove unused directories

**Task:**

- Check if ci/modules/python/gitci/ is still used (remove if not)
- Check if ci/modules/python/ai/claude/ is still used (templates now?)
- Audit ci/modules/ for any other deprecated directories
- Remove unused code and consolidate

### Handle No Initial Commit Scenario - **2h**

**Status:** Edge case handling

**Task:**

- Handle repositories with no commits yet
- Graceful fallbacks in git log commands
- Clear error messages when git history needed but missing

---

## Completed (2026-01-15)

### PostgreSQL Config Loader (Layer 5 of 8-layer cascade) ✅

- Created `src/hs_pylib/config/postgres_loader.py` with PostgresConfigLoader class
- Integrated as optional layer 5 in config cascade (enabled via `HS_CONFIG_DSN`)
- Features: sync/async loading, in-memory caching with TTL, namespace isolation, CRUD operations
- Tests: 31 unit tests + 25 integration tests
- Configuration: `HS_CONFIG_DSN`, `HS_CONFIG_TABLE`, `HS_CONFIG_NAMESPACE`, `HS_CONFIG_CACHE_TTL`

---

## Completed (2025-12-30)

### Kafka Docker testing infrastructure ✅

- Created `docker-compose.kafka.yml` (Apache Kafka 3.9.0, KRaft mode)
- Smart fixtures in conftest.py with remote/Docker fallback
- Unit tests for fixture logic (19 tests)
- Integration tests for Docker fallback

### Removed unused application framework ✅

- Deleted 2,656 lines of unused code
- Zero production usage across all dfe-* projects

### Fixed CI runner issue ✅

- Set repo-level `GH_RUNNER_DEFAULT=ubuntu-latest` for hs-pylib
- Published v2.13.6 to JFrog

---

## Completed (2025-12-05)

### hs_pylib.kafka module - **8h** ✅

**Completed:** Full Kafka client library with corporate defaults
**Branch:** `feat/DFE-553/add-kafka-library`
**Tests:** 160 unit + 19 integration tests

Features: KafkaClient, KafkaConsumer, KafkaProducer, async variants, KafkaAdmin (offset reset, topic config), SchemaAnalyser, sampling utilities, metrics collector, file-based config loading.

---

## Completed (2025-11-19)

### pyproject.toml Merge Bug - **3h** ✅

**Fixed:** 35-set-license.py destroying TOML structure with text manipulation
**Solution:** Use tomllib + tomli_w for proper parsing
**Result:** Template dependencies merge correctly

### Dual PyPI Setup for uv - **4h** ✅

**Implemented:** [[tool.uv.index]] + unsafe-best-match strategy
**Result:** Can use private (JFrog) + public (PyPI) packages together

### App vs Package Build Logic - **2h** ✅

**Fixed:** Apps no longer build wheels, only Nuitka binaries
**Updated:** 50-build.py, 55-build-nuitka.py, semantic-release build_command

### Local Nuitka Build Testing - **1h** ✅

**Verified:** test-cli-build builds 14MB Nuitka binary locally
**Works:** Binary executes and is properly encrypted

---

**Last Updated:** 2026-01-15 (PostgreSQL config loader completed)
