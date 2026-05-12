# hyperi-pylib TODO

## Active

### Replace or split [presidio] extra — Explosion AI ecosystem held back (2026-05-13)

**Problem.** The `[presidio]` extra pulls `presidio-analyzer` → `spaCy` →
`thinc` → `blis` / `confection` / `weasel`. The "bleeding edge"
deps pass tried to push thinc 8 → 9; this forced the entire Explosion
cluster to MAJOR-DOWNGRADE because spaCy stayed on thinc 8.x. Research
shows `thinc 9.1.1` (Sep 2024) is a dormant branch — spaCy 3.8.x is
the active line.

**Trigger.** Per the new "lib-review-on-block" policy below: one library
has been holding back the ecosystem for >18 months. Time to evaluate
alternatives.

**Candidates** (web-search 2026-05-13):

| Library | Approach | F1 | Trade-off |
|---|---|---|---|
| **scrubadub** | Pure regex + cleaners. No spaCy in core. | ~0.33 | Fastest, lowest dep weight. Misses names/locations. |
| **datafog** | Modular: regex core; `[nlp]` extra adds spaCy/GLiNER opt-in. | ~0.40+ | Best fit for "regex by default, NLP opt-in" — matches pylib's existing simple/advanced split. |
| **pii-anon** | Modular regex with checksum validation (Luhn, IBAN, ABA, VIN). Optional swarm: GLiNER + Presidio + XGBoost meta-learner. | ~0.50 | Best accuracy without spaCy at base tier. |
| **presidio + Transformers backend** | Same Presidio, swap NLP backend to huggingface. | ~0.65+ | Avoids thinc but pulls in huggingface (also heavy). |
| **Keep presidio** | Current state. | ~0.65 | Heaviest dep tree. Blocks ecosystem updates. |

**Proposed direction.** Two-tier extras:
- `[pii]` — datafog or scrubadub core, pure regex + checksums, no spaCy.
  Default for the masking_level="advanced" path.
- `[pii-ner]` — opt-in NER backend (presidio OR datafog[nlp]).
  Only consumers who genuinely need name/location masking install this.

Effect: routine `/deps` passes no longer fight the Explosion cluster;
heavy users pay the cost explicitly.

### Lib-review-on-block policy (2026-05-13)

When a single library (or library cluster) has been holding back the
rest of the dependency tree for **weeks or months, not days**, that's
the trigger to research alternatives — not "wait it out".

The /deps workflow should flag any package whose lower-bound pin is
forcing other transitive deps to regress, and any package that has
been unable to take its upstream's latest for >6 weeks. Each /deps
pass surfaces these as candidates for replacement.

Active examples:
- **thinc 8 / spaCy 3.8 / presidio cluster** — see entry above.
  thinc 9.1.1 from Sep 2024 abandoned; spaCy stays on 8.x indefinitely.

### Async correctness migration (2026-05-13)

`hyperi_pylib.concurrency` shipped (`run_blocking`, `make_async`,
`Bulkhead`, `gather_with_timeouts`). The AST audit in
`tests/unit/test_async_correctness.py` flags 14 known sync-in-async
bugs in `file.py`, `ansible_vault.py`, `openbao.py`. These are
tracked in `KNOWN_UNFIXED` and need migration:

- [ ] `secrets/providers/file.py` — 6 `X_async = self.X_sync()` calls
  → use `X_async = make_async(X_sync)`
- [ ] `secrets/providers/ansible_vault.py` — 7 same-pattern bugs
- [ ] `secrets/providers/openbao.py:208` — single `path.read_text()`
  inside async → wrap in `await run_blocking(path.read_text)`

Each fix removes the file's entry from KNOWN_UNFIXED.

### De-HyperI-isation for OSS adoption (2026-05-07)

**Plan:** [`docs/superpowers/plans/2026-05-07-de-hyperi-isation.md`](docs/superpowers/plans/2026-05-07-de-hyperi-isation.md)

**Why:** pylib is on PyPI and the README now positions it as a generic toolkit, but the source still leaks HyperI-internal naming and defaults — `dfe_*` metric prefix hardcoded in metric groups, `DfeApp` as the headline CLI base class, `DEFAULT_API_URL` pointing at `releases.hyperi.io`, `DEFAULT_IMAGE_REGISTRY` baked to `ghcr.io/hyperi-io`. An OSS adopter sees these and concludes the library isn't really for them.

**Scope:** five phased passes — cosmetic docstring-pass → metric prefix decoupling → `version-check` URL mandatory → `DfeApp` rename to `ServiceApp` (with deprecated alias) → deployment defaults mandatory. Each phase ships independently. All commits are `fix:` (PATCH) or `feat:` (MINOR) per pre-GA discipline.

**Status:** plan written. Phase 1 (cosmetic) ready to execute. Sister plan in [hyperi-rustlib](../hyperi-rustlib/docs/superpowers/plans/2026-05-07-de-hyperi-isation.md).

**Already done in prep (commit `2edb6e8`):** removed JFrog UV index, generalised registry-helper env vars (with `ARTIFACTORY_*` legacy fallback), routed license discovery to `~/.hyperi/` ahead of legacy `~/.hypersec/`, README rewrite with positioning manifesto, `__init__.py` module doc with positioning, sample-namespace strings (`hypersec` → `myorg`).

---

### Cross-language byte-parity tests for `hyperi_pylib.deployment` — **deferred until rustlib fixtures land**

**Status:** Deployment module shipped in v2.28.0 with snapshot/structural tests
(61 unit tests). True cross-language parity tests require
`hyperi-rustlib/tests/parity/fixtures/` which doesn't exist yet — the rustlib
side will add fixtures in 2.7.0+, then this repo vendors them.

**Steps once fixtures land:**

1. Vendor `hyperi-rustlib/tests/parity/fixtures/` into
   `tests/parity/fixtures/` (git-submodule or periodic copy).
2. Add `tests/parity/test_parity.py` parameterised over each fixture dir:
   - `expected/Dockerfile`, `expected/Dockerfile.runtime`,
     `expected/container-manifest.json`, `expected/argocd-application.yaml`
3. Each generator must produce byte-identical output to the rustlib fixture.
4. Wire as a CI gate.

### M365 / Azure tenant recreation refresh — **after recreation completes**

**Status:** STATE.md notes the current Azure tenant + M365 environment will be
deleted and recreated. Anything depending on tenant ID, vault URL, service
principal will break post-recreation.

**Steps:**

1. Refresh `HYPERI_TEST_AZURE_VAULT_URL`, `AZURE_TENANT_ID`, etc. in test
   environments.
2. Re-seed `hyperi-pylib-test` secret in the new vault.
3. Run `tests/integration/test_secrets_cloud_providers.py::TestAzureProviderIntegration`
   end-to-end against the new tenant.

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

## Completed (2026-05-01) — v2.28.0

### Cloud secrets Tier 1+2 (OpenBao, AWS, GCP, Azure) ✅

Plan 4 of `2026-04-10-secrets-abstraction-extensions-design.md`:

- 56 NotImplementedError stubs replaced (14 × 4 providers)
- AWS native `batch_get_secret_value` with `hasattr(p, "batch_get_async")` delegation in `SecretsManager`
- 141 unit tests + 10 OpenBao integration tests against real Vault container
- moto for AWS unit tests; pytest-httpx for OpenBao; helper-only for GCP/Azure
- OpenBao docker-compose fixture in `tests/conftest.py` (mirrors Kafka/Postgres cascade)

### `hyperi_pylib.deployment` module ✅

Mirror of `hyperi_rustlib::deployment`:

- Pydantic v2 contract models (DeploymentContract, KedaContract, NativeDepsContract, OciLabels, etc.)
- 6 generators with f-string templating: Dockerfile, runtime stage, container manifest JSON,
  Compose fragment, full Helm chart, ArgoCD Application
- Cascade helpers for image registry / base image / ArgoCD repo URL
- `DfeApp.deployment_contract()` hook + `generate-artefacts` CLI subcommand
- 61 unit tests including YAML parse-validation, generator determinism, Pydantic guards
- Opt-in via `[deployment]` extra (pydantic>=2.13)

### Quality cleanup ✅

- HttpClient retries via stamina decorators (was manual time.sleep loop)
- Kafka `external_sasl_scram` / `internal_sasl_scram` helpers (HyperI standard)
- 41 RUF013/RUF022 violations auto-fixed; TEMP ignores removed
- `tests/**` ruff per-file-ignores added (S101/PT017/PT011/PT012 etc.)

### OTel atexit blocker ✅ (resolved earlier; v2.28.0 confirms)

`conftest.py:18` sets `OTEL_EXPORTER_OTLP_ENDPOINT=""` + atexit handler at
`opentelemetry_backend.py:402` — sufficient. v2.27.x and v2.28.0 both ship clean
exit codes from CI test runs.

---

**Last Updated:** 2026-05-01
