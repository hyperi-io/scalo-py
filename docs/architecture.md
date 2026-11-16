# Architecture

How the pieces fit: the layering, which module imports which, and what each module exports. [README.md](README.md) has what scalo does for a service, and [integration.md](integration.md) the recipe for building one.

## Layering

Three layers, top to bottom:

- Core: `config` and `logger`, always installed and importing each other. Nearly every other module imports one or both.
- Runtime: environment detection (K8s / Docker / BareMetal) and container-aware paths. `config` runs its container detection at import, which `runtime` reuses, and `metrics` reads `RuntimeEnvironment` for its container gauges.
- Feature modules, which an app wires as it needs them: metrics, health, HTTP, secrets, expression and rules, resilience, concurrency, version-check, scaling, the CLI, API conventions and MCP. Most stand alone. `cli` imports `metrics`, `health`, `http` and `deployment`, `mcp` imports `api`, and `rules` imports `expression`.

Beside them sit the Kafka producer, consumer and admin clients (sync and async), and the deployment generators: the `DeploymentContract` Pydantic model and the Dockerfile, container manifest, Compose and ArgoCD AppProject generators. The scalo-service chart renders the Kubernetes objects from the serialised contract. `health` needs no extra: `HealthManager` and the observability listener run on the base install, and `create_health_router` alone needs FastAPI.

## Module import graph

`cli` sits on top and pulls in most of the library, and `config`, `logger`, `concurrency` and `crypto` import nothing outside themselves.

```mermaid
flowchart LR
    accTitle: L4 Detail -- scalo-py module tiers
    accDescr: cli imports modules from every tier. metrics, deployment, rules and mcp import from the tier below them. runtime, secrets, health, http, kafka and five more import from the base tier, which holds config, logger, concurrency and crypto.

    cli["cli"]
    tier2["metrics, deployment,<br/>rules, mcp"]
    tier1["runtime, secrets, health,<br/>http, kafka and 5 more"]
    base["config, logger,<br/>concurrency, crypto"]

    cli --> tier2
    tier2 --> tier1
    tier1 --> base

    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A
```

*Figure 1. L4 Detail -- scalo-py module tiers.* Up: [L1 Context -- scalo-py](README.md#what-scalo-py-talks-to).

An arrow means some module in the box imports one in the next box, and a module may import from any box to its right. The table has every edge, counting imports at module level and inside a function. Private helpers (`_env_compat`, `_yaml`, `_openapi`, `otel_backoff`, `otel_tracing`) are left out.

| Module | Imports from scalo |
|---|---|
| `cli` | `config`, `logger`, `metrics`, `health`, `http`, `deployment`, `crypto` |
| `metrics` | `config`, `logger`, `runtime` |
| `deployment` | `config`, `secrets` |
| `rules` | `expression` |
| `mcp` | `api`, `logger` |
| `secrets` | `config`, `logger`, `concurrency`, `crypto` |
| `kafka` | `config`, `logger`, `concurrency` |
| `health` | `logger`, `concurrency` |
| `http` | `logger`, `crypto` |
| `runtime` | `config`, `logger` |
| `api` | `config`, `logger` |
| `expression`, `version_check` | `config` |
| `resilience`, `ddl` | `logger` |
| `config` / `logger` | each other |
| `concurrency`, `crypto`, `scaling` | nothing |

`resilience` is a hand-rolled `CircuitBreaker` and `ReconnectingResilience` that nothing else in scalo imports, so wrap a call in one yourself. The HTTP client retries with stamina and has no breaker.

## Module map

Each module under `src/scalo/` and what you import from it:

| Module | Public API entry |
|---|---|
| `api` | `Hierarchy`, `install`, `scalo_extra`, `permission`, `PreconditionHeaders`, `ListParams`, `Page`, `ProblemError`, `assert_conformant` (the `api` extra) |
| `cli` | `ServiceApp`, `CommonArgs`, `VersionInfo`, re-exported Typer types, and `cli.openapi`, a CLI built from a spec (the `cli` extra) |
| `concurrency` | `run_blocking`, `make_async`, `Bulkhead`, `gather_with_timeouts` |
| `config` | `settings`, `get_config`, `get_environment`, `get_app_name`, `init_config_directory`, `ConfigReloader`, `DirectoryConfigStore` |
| `crypto` | `CryptoProfile`, `ssl_context`, the TLS policy the HTTP client and secrets providers share |
| `data` | data files: gitleaks rules and national-ID definitions |
| `ddl` | `EngineResolver`, `parse_engine`: ClickHouse table-engine selection |
| `deployment` | `DeploymentContract`, `generate_*`, `ContractIdentity`, `test_support` |
| `expression` | `evaluate`, `evaluate_condition`, `validate`, `compile_expression` |
| `health` | `HealthManager`, `create_health_router`, `serve_observability` |
| `http` | `HttpClient`, `AsyncHttpClient` |
| `kafka` | `KafkaProducer`, `KafkaConsumer`, `AsyncKafka*`, `KafkaAdmin`, `SchemaAnalyser` |
| `logger` | `logger`, convenience fns, `scrub/` package |
| `mcp` | `mount`, `McpServer`, `tools_from_spec` (the `mcp` extra) |
| `metrics` | `create_metrics`, `groups/*`, `CardinalityTracker` |
| `resilience` | `CircuitBreaker`, `CircuitBreakerConfig`, `ReconnectingResilience` |
| `rules` | `RuleSet`, `Clamp`, `RuleUsage` |
| `runtime` | `get_runtime_paths`, `RuntimePaths`, `RuntimeEnvironment` |
| `scaling` | `ScalingPressure`, `ScalingPressureConfig`, `PressureSnapshot` |
| `secrets` | `SecretsManager`, providers (file/openbao/aws/gcp/azure/kubernetes) |
| `version_check` | `check_on_startup`, `VersionCheckConfig` |

## Against scalo-rs

scalo-rs has pieces scalo-py does not, by design. It has a transport layer, with Kafka, gRPC, HTTP, File, Pipe and Memory transports behind its `TransportSender` and `TransportReceiver` traits, where scalo-py has Kafka clients and no transport abstraction. It has the pieces its `docs/pipeline/` covers: `BatchEngine`, `WorkerPool`, `TieredSink`, `Spool`, DLQ and STRmatch. Python's async model and the GIL make the hot-path concurrency story different, so scalo-py has `concurrency.gather_with_timeouts` for the simple cases. scalo-py has pieces scalo-rs does not: `api` (FastAPI conventions), `mcp`, and `cli.openapi`.

| Concept | scalo-rs | scalo-py |
|---|---|---|
| Runtime entry point | `ServiceApp` trait + `ServiceRuntime` | `ServiceApp` base class |
| HTTP client | `reqwest` + `backon` retry | `httpx` + stamina retry |
| Circuit breaker | hand-rolled `tiered_sink::CircuitBreaker` | hand-rolled `resilience.CircuitBreaker` |
| Config | `figment` 7-layer | `dynaconf` 7-layer |
| Logger | `tracing` | `loguru` |
| Metrics | `metrics` crate + `metrics-exporter-prometheus` + OTel | `prometheus-client` + `opentelemetry-*` |
| CLI | `clap` + `src/cli/app.rs` | `typer` + `src/scalo/cli/app.py` |
| Expression | the `cel` crate (cel-rust) | `common-expression-language`, Python bindings built on the same crate |

The doc subdirs match where the concept maps one to one. Where scalo-py lacks the concept, the subdir is absent: there is no `pipeline/`, and `transport/` covers Kafka alone.
