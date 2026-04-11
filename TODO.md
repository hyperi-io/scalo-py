# hyperi-pylib TODO

## Active

### Secrets Abstraction Extensions — Plan 4 (Cloud Providers) `[DEFERRED TO WORK VM]`

**Spec:** `docs/superpowers/specs/2026-04-10-secrets-abstraction-extensions-design.md`

**Status:** Plans 1-3 shipped in v2.27.0. Plan 4 deferred — needs cloud creds available on
`desktop-derek` work VM. Resume there.

- [x] Plan 1: Types (`SecretMetadata`, `SecretFilter`), Exceptions (`SecretAlreadyExistsError`, `SecretPermissionError`, `SecretVersionNotFoundError`, `VersioningNotSupportedError`), ABC (`SecretProvider` Tier 1 methods, `VersionedProvider` mixin)
- [x] Plan 2: File-based providers (`FileProvider` + `AnsibleVaultProvider` Tier 1 methods — list, metadata, create, update, delete)
- [x] Plan 3: `SecretsManager` extensions (batch_get, list, get_metadata, CRUD delegation, version capability checks)
- [ ] **Plan 4:** Cloud providers — OpenBao, AWS, GCP, Azure. Replace `NotImplementedError` stubs with real SDK calls for Tier 1 (list/metadata/CRUD) + Tier 2 (get_version/list_versions).

**Resume on desktop-derek work VM:**

1. `cd /projects/hyperi-pylib && git pull` — pull v2.27.0 (Plans 1-3)
2. Copy `.env` with cloud creds from `~/secrets/` or `hyperi-infra` to repo root (gitignored)
3. Verify creds available:
   - **OpenBao:** `VAULT_ADDR`, `VAULT_TOKEN` (devex `10.66.0.101` is safe for testing)
   - **AWS:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or IAM role — or use **LocalStack** / **moto** for offline testing
   - **GCP:** `GOOGLE_APPLICATION_CREDENTIALS` path to service account JSON
   - **Azure:** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_VAULT_URL`
4. Implement in this order (easiest → hardest): OpenBao → AWS → GCP → Azure
5. Each provider needs ~14 methods: `list/get_metadata/create/update/delete` (sync+async) + versioning (`get_version/list_versions`). Stubs currently in `src/hyperi_pylib/secrets/providers/{openbao,aws,gcp,azure}.py`.
6. AWS: use native `batch_get_secret_value` when implementing `batch_get_async` (see `manager.py:batch_get` — it already delegates).
7. Write integration tests using existing docker-compose pattern (see `test_secrets_cache.py` for the Postgres fixture example). LocalStack docker-compose for AWS if not using real tenant.
8. Target: v2.28.0 (minor bump, new capabilities on existing providers).

**Files to modify:**

- `src/hyperi_pylib/secrets/providers/openbao.py` — search for `NotImplementedError`
- `src/hyperi_pylib/secrets/providers/aws.py`
- `src/hyperi_pylib/secrets/providers/gcp.py`
- `src/hyperi_pylib/secrets/providers/azure.py`

**Important design notes from Plans 1-3:**

- Cloud providers inherit from `VersionedProvider` (not `SecretProvider`) — they MUST implement `get_version_async/sync` and `list_versions_async/sync`.
- File providers inherit from `SecretProvider` — `isinstance(p, VersionedProvider)` check in `SecretsManager.get_version` raises `VersioningNotSupportedError` for them.
- `SecretFilter.prefix` is the efficient path (server-side on cloud), `pattern` is client-side fnmatch post-filter.
- Error handling: map provider-specific errors to `SecretNotFoundError`, `SecretAlreadyExistsError`, `SecretPermissionError(provider, operation, path, hint)`, `SecretVersionNotFoundError`.

### BLOCKER: Fix OTel atexit exit code 1 in CI tests — **2h**

**Status:** Blocking pylib GA release (v2.25.0)

**Problem:** OTel SDK's `PeriodicExportingMetricReader` tries to flush to `localhost:4317` at process exit. When no OTel collector is running (CI), the error propagates as exit code 1 — even though all 1482 tests pass.

**Root cause:** The OTel OTLP exporter defaults to `http://localhost:4317`. In CI, no collector runs. The SDK's atexit handler flushes and fails, setting exit code 1.

**Fix options:**
1. Spin up OTel collector container in CI test fixtures (proper fix)
2. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to empty in CI-only env (but breaks `test_dual_export`)
3. Fix the OTel backend to catch atexit errors (partial — atexit handler registration order)

**Constraint:** Release CI must use docker services, NEVER local environment services.

### CI test infrastructure: release CI must use docker — **4h**

**Status:** Not started — critical architectural rule to enforce

**Rule:** Release/CI tests MUST use docker-based services (OTel collector, Postgres, Kafka, etc.), NEVER assume local host services are running. Local services are for developer convenience only.

**Task:**
- Add OTel collector container to CI test fixtures (docker-compose or testcontainers)
- Update conftest.py to auto-start OTel collector when `TEST_MODE=docker`
- Ensure all integration tests have docker fallback
- Document the rule in hyperi-ai standards

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

### Update documentation for session work — **2h**

**Status:** Not started

**Task:**
- Update hyperi-ai CI standards docs for two-tier quality profiles
- Update hyperi-ai skills (release, ci-check) for new tooling
- Add "how to iterate and add ruff allows" guide to hyperi-ci docs
- Update hyperi-ci DESIGN.md with two-tier quality architecture
- Add spike/alpha/beta channel support to hyperi-ci TODO

### Remove TEMP test_ignore entries from pylib and dfe-engine — **0.5h**

**Status:** Waiting for hyperi-ci v1.4.0 to propagate to CI runners

**Task:**
- Once CI runners pick up hyperi-ci v1.4.0 (two-tier quality), re-shrink ignore lists
- Remove all entries marked `# TEMP: remove after hyperi-ci two-tier quality released`
- Verify CI passes with shrunk lists

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

### [BACKLOG] hyperi_pylib.kafka: Opinionated SASL-SCRAM helpers - **1h**

**Status:** Not started — identified during dfe-loader E2E test work

**Task:**

- Add `KafkaConfig.external_sasl_scram(brokers, username, password)` classmethod — SASL_SSL + SCRAM-SHA-512
- Add `KafkaConfig.internal_sasl_scram(brokers, username, password)` classmethod — SASL_PLAINTEXT + SCRAM-SHA-512
- Encodes the org-wide decision: SCRAM works unchanged on Apache Kafka, AutoMQ, MSK, Confluent Cloud
- Removes per-project manual assembly of `security.protocol` + `sasl.*` fields

---

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

## Completed (2026-03-22)

### Rustlib/Pylib gap remediation (P0-P2)

- DFE metric groups (AppMetrics, BufferMetrics, ConsumerMetrics, SinkMetrics, CircuitBreakerMetrics, BackpressureMetrics)
- Health endpoint FastAPI router (/health/live, /health/ready, /health/startup)
- VersionInfo.from_env() classmethod
- Scaling pressure calculator (0-100 composite score for KEDA)
- Circuit breaker (Closed/Open/HalfOpen state machine)
- Auto metrics init in DfeApp
- Config reload wrapper (on_reload callbacks)
- Label cardinality validation
- Shared masking pattern + metrics naming test fixtures (hyperi-ai submodule)
- Log throttle parity verification

### Dependency updates + 4 CVE fixes

- dynaconf 3.2.13 (CVE-2026-33154), black 26.3.1 (CVE-2026-32274)
- pyasn1 0.6.3 (CVE-2026-30922), pyjwt 2.12.1 (CVE-2026-32597)
- sphinx 7→9, myst-parser 4→5
- All 30+ packages upgraded to latest

### Tooling modernisation

- Replaced interrogate with ruff D rules (pydocstyle)
- Replaced bandit with ruff S rules
- Added ruff rule groups: S, N, PT, RUF, PIE, T20
- Removed py package CVE (PYSEC-2022-42969)

---

**Last Updated:** 2026-03-22
