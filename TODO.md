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

### Add hs_pylib.cache module (Cashews wrapper) - **4h**

**Status:** Not started - identified as gap during dfe-control-plane metrics work

**Solution:** Wrap [Cashews](https://github.com/Krukov/cashews) (527 stars, MIT, active)

**Task:**
- Create `hs_pylib.cache` module wrapping Cashews with disk backend
- Cache tuple: `(source, identifier, value, time)` - source-based TTLs
- Per-source TTL config: `{"http": "24h", "tavily": "1h", "db": "30m"}`
- `@cached("http", key="{url}")` decorator
- Built-in metrics (hit/miss) via hs_pylib.metrics

**Dependencies:**
```toml
"cashews[diskcache]>=7.0"
```

**Rationale:**
- Disk-backed (SQLite) reduces memory, survives restarts
- Native async, FastAPI integration
- Thin wrapper around battle-tested library

**Design:** See dfe-control-plane/HS-LIB-UPDATE.md §5

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

**Status:** Removed from hs-pylib v2.13.5, preserved in git history

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

**Last Updated:** 2025-12-05 (kafka module completed)
