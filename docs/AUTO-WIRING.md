# Auto-wiring

What pylib does automatically when you import a module, versus what
you wire by hand. The principle: opinionated defaults that just work,
escape hatches when you need them.

The deprecated `Application` framework was the rustlib-style "wire
everything from one call" entry point. It's gone. Pylib's auto-wiring
is now per-module and happens at first use.

---

## What's automatic

| Module | Wired at | What's automatic |
|---|---|---|
| `config` | First `from hyperi_pylib.config import settings` | Dynaconf cascade construction, `.env` loading, PostgreSQL config source (if `HYPERI_CONFIG_DSN` set), sensitive masking, `RuntimePaths.config_dir` selection |
| `logger` | First import | Loguru sink installed, JSON/text autodetect (TTY vs not), RFC 3339 format, level from `LOG_LEVEL` env (default INFO), scrub filters loaded from `data/gitleaks.toml` + `data/national_ids.toml`, CI mode autodetect (GitHub Actions / GitLab CI / Jenkins) for ASCII-only output |
| `runtime` | First `get_runtime_paths()` call | K8s / Docker / BareMetal detection (7 indicators), path-set materialisation, `CONTAINER_BASE_PATH` env override |
| `metrics` | First `create_metrics(namespace)` call | Backend selection (OTel default, Prometheus fallback if OTel not installed), `MetricsManager` content + content-type for an app-served route, process collector (RSS, CPU, FDs via psutil), cardinality cap |
| `health` | First `HealthManager()` instantiation | Probe handlers ready; `/health/live` is unconditionally 200; `/health/ready` returns 503 until `set_ready()` is called and all registered downstream checks pass |
| `version_check` | `check_on_startup(product, version)` call | Daemon thread fires-and-forgets a probe to HyperI version API; never blocks, never raises |
| `secrets` | `SecretsManager.from_config(...)` | Provider class selected from `settings.secrets.provider`; backend extras (`secrets-vault`, `secrets-aws`, etc.) imported lazily |

---

## What's manual

| Concern | You wire | Why not automatic |
|---|---|---|
| FastAPI server with `/health/*` router | `app.include_router(create_health_router(...))` | Pylib doesn't own your HTTP framework. `/metrics` is served by the app using `MetricsManager.content` + `content_type` (see core-pillars/METRICS.md). No `/config` router ships |
| Kafka producer flush on shutdown | `producer.flush()` in your signal handler | Producer lifecycle is app-specific; we don't intercept SIGTERM |
| Cache initialisation | `await cache.init()` (PostgresCache) or `configure_cache(...)` (Cashews SQLite) | Cache backend choice + connection details are app-specific |
| Circuit breaker around a downstream | `with CircuitBreaker(config): call()` or `@with_resilience` decorator | Failure modes vary per downstream; sensible defaults exist but explicit is better |
| Metric registration | `m.counter(name, help, labels)` per metric | Metrics are app-specific; we provide the framework, not the catalogue |
| Application class / runtime entry point | Nothing — compose modules directly | The `Application` framework was experimental and deprecated; production code uses the modules directly |

---

## You-get-this-for-free matrix

Read top-to-bottom: install the extra in the first column, get every
"automatic" item from every row above it for free.

| Install | Adds | Automatic |
|---|---|---|
| `hyperi-pylib` (base) | `config`, `logger`, `runtime`, `cli`, `health`, `database`, `version_check`, `concurrency`, `harness` | Cascade, structured logs, path detection, version probe |
| `hyperi-pylib[metrics]` | `metrics` + `prometheus-client` + `psutil` | Above + `MetricsManager.content` for app-served `/metrics` route + process collector + cardinality cap |
| `hyperi-pylib[opentelemetry]` | OTel SDK + exporters | Above + OTel metric backend + OTLP export (dual with Prometheus) |
| `hyperi-pylib[http]` | `http` + `httpx` + `stamina` + `purgatory` | Above + HTTP client with retry + circuit breaker + metrics integration |
| `hyperi-pylib[cache]` | `cache` + `cashews` + `psycopg` | Above + `@cached` decorator + SQLite or PostgreSQL backend |
| `hyperi-pylib[kafka]` | `kafka` + `confluent-kafka` + `genson` | Above + producer/consumer/admin + schema sampling + consumer-lag health |
| `hyperi-pylib[secrets-{vault,aws,gcp,azure,ansible-vault}]` | `secrets` provider | Above + uniform interface, lazy-loaded provider |
| `hyperi-pylib[deployment]` | `deployment` + `pydantic` | Above + `DeploymentContract` + generators + `ContractIdentity` + `test_support` |
| `hyperi-pylib[expression]` | `expression` + `common-expression-language` | Above + CEL evaluation (Python/Rust parity via PyO3) |
| `hyperi-pylib[resilience]` | `resilience` + `stamina` + `purgatory` | Above + standalone circuit breaker (already pulled in by `http`/`cache`/`secrets-*`) |

---

## Lifecycle

```mermaid
flowchart TB
    Start["Process start"]
    Import["import hyperi_pylib.{config,logger,runtime}"]
    Cascade["config: load 8 layers"]
    LogFmt["logger: detect TTY/CI, install sink"]
    RtDetect["runtime: detect K8s/Docker/BareMetal"]
    AppInit["App startup logic"]
    Metrics["metrics: create_metrics(ns)"]
    Health["health: HealthManager()"]
    DepCheck["health: register checks"]
    Connect["Connect downstream deps (db, kafka, secrets)"]
    Ready["health.set_ready()"]
    Serve["Serve traffic / consume events"]
    Sigterm["SIGTERM received"]
    Flush["Flush producers, close connections"]
    Stop["Process exit"]

    Start --> Import
    Import --> Cascade
    Import --> LogFmt
    Import --> RtDetect
    Cascade --> AppInit
    LogFmt --> AppInit
    RtDetect --> AppInit
    AppInit --> Metrics
    AppInit --> Health
    Health --> DepCheck
    AppInit --> Connect
    Connect --> Ready
    Ready --> Serve
    Serve --> Sigterm
    Sigterm --> Flush
    Flush --> Stop
```

Three points:

- The import-time work is cheap (no I/O except cascade file reads).
  Apps can `import hyperi_pylib.config` from a `__init__.py` without
  startup latency surprises.
- `set_ready()` is explicit, not inferred. Until you call it, `/readyz`
  returns 503 — which is the desired K8s rolling-update behaviour.
- SIGTERM handling is the app's job. We expose `concurrency` primitives
  (cancellation tokens, bulkheads) but don't install signal handlers
  on import.

---

## Related

- [README.md](README.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [INTEGRATION.md](INTEGRATION.md)
- [EXTRAS-FLAGS.md](EXTRAS-FLAGS.md)
- [core-pillars/CONFIG.md](core-pillars/CONFIG.md)
- [core-pillars/HEALTH.md](core-pillars/HEALTH.md)
