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

- Zero production usage across dfe-* projects
- 2,656 lines of experimental code
- Production apps use FastAPI/Typer directly with hs_pylib.metrics/logger/config

**Reactivation criteria:**

- When 2+ production apps need standardized application patterns
- When profile-based config provides value over direct configuration

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

---

## Completed (2026-01-15)

### PostgreSQL Cache Backend (v2.14.0) ✅

- `PostgresCache` class with async connection pooling (psycopg3)
- msgpack serialization, TTL expiration, bulk invalidation
- `generate_cache_key()` helper
- Unit + integration tests with Docker fixtures
- Released as v2.14.0

### PostgreSQL Config Loader ✅

- `PostgresConfigLoader` for shared configuration store
- Layer 5 in 8-layer config cascade (enabled via `HS_CONFIG_DSN`)
- Namespace isolation, cache TTL, sync/async modes
- 31 unit + 25 integration tests

### dfe-engine Updated ✅

- Updated to `hs-pylib>=2.14.0`
- Security fixes: urllib3, werkzeug CVEs

---

## Completed (2025-12-30)

### Kafka Docker testing infrastructure ✅

- Created `docker-compose.kafka.yml` (Apache Kafka 3.9.0, KRaft mode)
- Smart fixtures in conftest.py with remote/Docker fallback
- Unit tests for fixture logic (19 tests)

### Removed unused application framework ✅

- Deleted 2,656 lines of unused code
- Zero production usage across all dfe-* projects

### Fixed CI runner issue ✅

- Set repo-level `GH_RUNNER_DEFAULT=ubuntu-latest` for hs-pylib
- Published v2.13.6 to JFrog

---

## Completed (2025-12-05)

### hs_pylib.kafka module ✅

Full Kafka client library with corporate defaults (160 unit + 19 integration tests)

---

**Last Updated:** 2026-01-15
