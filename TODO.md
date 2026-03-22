# hyperi-pylib TODO

## Active

### Fix CI markdownlint scanning .venv/ - **0.5h**

**Status:** Quality job creates .venv/ on ARC runner, markdownlint scans it

**Task:**

- Update ci repo markdownlint config to exclude `.venv/` directory
- Also exclude `node_modules/`, `vendor/`, other common dependency dirs

---

## Backlog

### Standardise test infrastructure: dual-mode (remote + docker-local) - **2h**

**Status:** Not started — integration tests currently skip when external services unavailable

**Task:**

- Implement dual-mode test infrastructure per `~/DFE-TEST-INFRA-PROMPT.md` (Python adaptation)
- `TEST_MODE=remote` (default): use devex cluster endpoints from `.env`
- `TEST_MODE=docker`: use `dfe-docker` infra profile (localhost, no auth)
- Add `conftest.py` fixtures for `ClickHouseTestConfig` and `KafkaTestConfig`
- Replace hardcoded env var reads with mode-aware config helpers
- Ensure tests don't skip in CI; they should run against real services

**Rationale:**

- Integration tests that always skip provide no coverage guarantee
- CI should run full integration suite, not just unit tests
- External tool pattern is more reliable than mocking

---

### Add hyperi_pylib.http.HttpClient (Stamina + httpx) - **3h**

**Status:** Not started - identified during dfe-control-plane B113 fixes

**Solution:** Wrap [Stamina](https://github.com/hynek/stamina) (by Hynek, attrs/structlog author) + httpx

**Task:**

- Create `hyperi_pylib.http.HttpClient` wrapping httpx + stamina
- Auto timeout (default 30s) - solves B113 bandit issues
- Auto retries with exponential backoff via stamina
- Stamina auto-detects structlog + prometheus-client

**Dependencies:**

```toml
"httpx>=0.27"
"stamina>=25.1"
```

**Rationale:**

- Stamina auto-integrates with hyperi_pylib.logger (structlog) and hyperi_pylib.metrics (prometheus)
- Testing friendly: `stamina.set_testing(attempts=1)` in pytest
- Same author as attrs/structlog - quality pedigree

**Design:** See dfe-control-plane/HS-LIB-UPDATE.md §4

### [BACKLOG] hyperi_pylib.application: Application Framework - **deferred**

**Status:** Removed from hyperi-pylib v2.13.6, preserved in git history

**What was removed:**

- `src/hyperi_pylib/application/` - API, CLI, Daemon, MCP, Oneshot application types
- Profile-based configuration (dev, docker, prod)
- Health check mixins
- Signal handling

**Why removed:**

- Zero production usage across dfe-* projects
- 2,656 lines of experimental code
- Production apps use FastAPI/Typer directly with hyperi_pylib.metrics/logger/config

**Reactivation criteria:**

- When 2+ production apps need standardized application patterns
- When profile-based config provides value over direct configuration

### [BACKLOG] hyperi_pylib.kafka: JSON key-value offset seek - **2d**

**Status:** Backlog - documented in admin.py:552-582

**Task:** Implement `seek_to_json_match()` - seek to first message where nested JSON field matches value

**Considerations:**

- No index: Worst case is full topic scan
- Parallel partition search for performance
- Cancellation support via threading.Event
- Timeout handling to prevent hangs

---

## Backlog (CI/Build)

### ~~Fix BuildJet runner availability~~ ✅ (replaced by ARC runners)

**Resolved:** Org-level `GH_RUNNER_DEFAULT=arc-runner-16cpu` now uses ARC self-hosted runners.
Repo-level override to `ubuntu-latest` deleted. CI passing on ARC runners (ci v1.59.10).

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

## Completed (2026-01-20)

### hyperi_pylib.license module ✅

Direct Python port of hs-rustlib licensing module for cross-language interoperability.

**Features:**
- AES-256-GCM encryption (Rust-compatible format)
- Ed25519 signature verification
- SHA-256 runtime integrity checks
- License file search cascade (explicit → env var → standard paths → URL → defaults)
- Global singleton API with thread safety

**Files:**
- `src/hyperi_pylib/license/` - 6 module files (error, types, defaults, crypto, integrity, manager)
- `tests/unit/test_license_*.py` - 5 test files

**Security Note:** Obfuscation handled by Nuitka compilation - Python source has plaintext defaults.

**Dependencies:** `cryptography>=42.0` via `pip install hyperi-pylib[license]`

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
- Layer 5 in 8-layer config cascade (enabled via `HYPERI_CONFIG_DSN`)
- Namespace isolation, cache TTL, sync/async modes
- 31 unit + 25 integration tests

### dfe-engine Updated ✅

- Updated to `hyperi-pylib>=2.14.0`
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

- Set repo-level `GH_RUNNER_DEFAULT=ubuntu-latest` for hyperi-pylib
- Published v2.13.6 to JFrog

---

## Completed (2025-12-05)

### hyperi_pylib.kafka module ✅

Full Kafka client library with corporate defaults (160 unit + 19 integration tests)

---

## Completed (2026-03-04)

### OTel metrics backend prometheus-compat adapters ✅

- Added adapter classes (`OtelCounterAdapter`, `OtelGaugeAdapter`, `OtelHistogramAdapter`) to `opentelemetry_backend.py`
- Adapters translate prometheus-client `.labels().inc()` / `.labels().observe()` API to OTel instrument calls
- `OtelGaugeAdapter` implements absolute `.set()` via `_current` state tracking dict (OTel UpDownCounter only accepts deltas)
- Updated `counter()`, `gauge()`, `histogram()` methods to return adapters, not raw instruments
- Added 5 new `@otel_required` tests covering all adapter paths + label name conversion
- 68/68 metrics tests passing
- Removed stale backlog items (FastAPI middleware + DB metrics — both already implemented)
- Updated ci → v1.60.3, ai → 1.14.5

### DfeApp CLI framework (v2.24.0) ✅

- `DfeApp` ABC mirroring rustlib's `cli::app` module
- Standard subcommands: `run`, `version`, `config-check` (no `top` — Python never on hot path)
- `CommonArgs` dataclass (--config, --log-level, --verbose, --quiet, --metrics-addr)
- `VersionInfo` with builder pattern, `CliError` hierarchy
- Supports both sync `run_service()` and async `run_service_async()`
- Config uses existing `hyperi_pylib.config` cascade (Dynaconf)
- `register_commands()` hook for app-specific subcommands
- 35 unit tests, all passing
- Published to JFrog via full CI pipeline

---

## Completed (2026-03-02)

### ARC runner migration ✅

- Deleted repo-level `GH_RUNNER_DEFAULT=ubuntu-latest` override
- Org-level now `GH_RUNNER_DEFAULT=arc-runner-16cpu` (ARC self-hosted)
- Updated ci submodule v1.59.8 → v1.59.10 (Node.js fix, container block removal)
- Regenerated workflows via `./ci/attach.sh --force`
- Migrated config from `.hypersec-ci.yaml` → `.hyperi-ci.yaml`
- CI fully passing: Detect (30s) → Quality (1m15s) → Test (4m19s)

---

**Last Updated:** 2026-03-04
