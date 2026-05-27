# hyperi-pylib

<!-- BADGES:START -->
[![Build Status](https://github.com/hyperi-io/hyperi-pylib/actions/workflows/ci.yml/badge.svg)](https://github.com/hyperi-io/hyperi-pylib/actions)
[![PyPI](https://img.shields.io/pypi/v/hyperi-pylib?logo=pypi)](https://pypi.org/project/hyperi-pylib/)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-FSL--1.1--ALv2-blue)](LICENSE)
<!-- BADGES:END -->

> **There's plenty of sage advice out there about how to run Python services
> in production at scale — config cascades, structured logging, masking
> secrets, multi-backend secrets management, Prometheus, OpenTelemetry,
> backpressure, graceful shutdown — but almost none of it as code you can
> just install and use.**
>
> **This is that code.**
>
> Opinionated, drop-in, working out of the box. The patterns from blog posts
> as actual library — not a framework you assemble from twelve packages and a
> weekend.

Built as the foundation for HyperI's production data services. Generic
enough that you don't need to be at HyperI to use it.

## What this is (and isn't) for

**For:** control-plane APIs, UI backends, orchestrators, CLI tools,
integration glue, batch workloads, configuration management.

**Not for:** the hot path. If you're processing millions of messages
per second and shaving microseconds matters, that code belongs in
Rust — see `hyperi-rustlib`. Pylib is "fast enough for control plane
and integration"; rustlib is "fast enough for the hot path".

We optimise pylib sensibly — no gratuitously slow choices, no obvious
algorithmic mistakes — but the lean is toward **stability,
expressiveness, and integration** rather than microseconds. Readable
abstractions beat inlined ones; clean composition beats hand-rolled
loops; heavier deps are acceptable when they earn their keep. This
design decision is why pylib ships NER-grade PII masking
(5–200ms/call), allows substantial dependency trees, and doesn't
agonise over async dispatch overhead. We don't hard-iterate the hot
path the way rustlib does, because that's rustlib's job.

This module exists because of this — but the backend version: <https://www.youtube.com/watch?v=xE9W9Ghe4Jk>

## What you get

Core modules — always installed (`uv add hyperi-pylib`):

| Module | Description | Third-party deps |
|---|---|---|
| `logger` | Structured JSON logging with automatic sensitive-data masking, container-aware output | loguru |
| `config` | 8-layer cascade (CLI → ENV → .env → PostgreSQL → YAML → defaults), container-aware path resolution | dynaconf, pyyaml, python-dotenv, mergedeep, tomli-w, dulwich |
| `runtime` | Auto-detects K8s / Docker / local, resolves config and data paths accordingly | stdlib only |
| `database` | Connection-URL builders for PostgreSQL, Redis, etc. from standard env vars | stdlib only |
| `cli` | `DfeApp` base class — subclass to get `run` / `version` / `config-check` for free | typer |
| `harness` | Activity-based subprocess timeouts, pattern-matched failure detection | stdlib only |
| `version-check` | Optional startup check for new releases (no-op if `httpx` not installed) | httpx (lazy) |

Optional modules — install via extras:

| Module | Extra | Third-party deps |
|---|---|---|
| `http` | `http` | httpx, stamina (retry with jitter) |
| `metrics` | `metrics` | prometheus-client, psutil (auto-collects process/container metrics) |
| `expression` | `expression` | common-expression-language (CEL via Rust/PyO3) |
| `cache` | `cache` | cashews, msgpack, psycopg[binary,pool] (PostgreSQL-backed async cache) |
| `kafka` | `kafka` | confluent-kafka, genson |
| `opentelemetry` | `opentelemetry` | OpenTelemetry SDK + OTLP + Prometheus exporters |
| `secrets` | `secrets` | All backends (Vault/OpenBao + AWS + GCP + Azure) |

## Installation

```bash
# Core only (logger, config, runtime, database, cli, harness, version-check)
uv add hyperi-pylib

# With common extras
uv add "hyperi-pylib[http,metrics,kafka]"

# Full stack
uv add "hyperi-pylib[http,metrics,expression,cache,kafka,opentelemetry,secrets]"
```

> **Package naming:** `hyperi-pylib` on PyPI, `hyperi_pylib` for Python imports.

### Optional Extras Sizes

| Extra | Packages | Approx size |
|---|---|---|
| `http` | httpx + stamina | ~1 MB |
| `metrics` | prometheus-client + psutil | ~1 MB |
| `expression` | CEL via Rust/PyO3 | ~6 MB |
| `cache` | cashews + msgpack + psycopg[binary,pool] | ~14 MB (psycopg C libs) |
| `kafka` | confluent-kafka + genson | ~11 MB (C libs) |
| `opentelemetry` | OpenTelemetry SDK + exporters | ~4 MB |
| `presidio` | Presidio analyser + anonymiser | ~500 MB (spaCy + ML models) |
| `secrets` | All secrets backends | — |
| `secrets-vault` | OpenBao / HashiCorp Vault (uses `http` extra) | convenience marker |
| `secrets-aws` | AWS Secrets Manager via boto3 | ~100 MB |
| `secrets-gcp` | GCP Secret Manager | ~80–100 MB |
| `secrets-azure` | Azure Key Vault | ~50 MB |

## Quick Start

### Logging

```python
from hyperi_pylib.logger import logger

logger.info("Service starting", version="1.0.0")
logger.error("DB connection failed", host="postgres", retry=3)
```

Auto-detects console vs container — structured JSON in containers, human-readable
locally. Sensitive fields (passwords, tokens, API keys, etc.) are masked
automatically.

### Configuration

```python
from hyperi_pylib.config import settings

# Cascade: CLI args → ENV → .env → PostgreSQL → settings.yaml → defaults
host = settings.database.host
port = settings.api.port
```

ENV key mapping: `settings.database.host` → `MYAPP_DATABASE_HOST` (prefix is
configurable per app).

### Database URLs

```python
from hyperi_pylib import build_database_url

postgres = build_database_url("postgresql")  # reads POSTGRES_HOST, POSTGRES_PORT, etc.
redis = build_database_url("redis")          # reads REDIS_HOST, REDIS_PORT, etc.
```

### Runtime Paths (container-aware)

```python
from hyperi_pylib import get_runtime_paths

runtime = get_runtime_paths()
config = runtime.config_dir / "app.yaml"   # /config in K8s, ~/.config locally
data   = runtime.data_dir  / "state.db"    # /data in K8s, ~/.local/share locally
```

### Metrics

```python
from hyperi_pylib import create_metrics

metrics = create_metrics(namespace="myapp")
metrics.http_requests.inc()
metrics.active_users.set(42)
metrics.request_duration.observe(0.123)
```

Automatic process and container metrics (CPU, memory, FDs, uptime) come for
free — no extra wiring.

### Cache (PostgreSQL-backed)

```python
from hyperi_pylib.cache import PostgresCache, generate_cache_key

cache = PostgresCache(dsn="postgresql://user:pass@host/db")
await cache.init()

key = generate_cache_key("analytics", "events", org_id="acme")
await cache.set(key, {"data": [...]}, ttl_seconds=300, namespace="analytics")
value = await cache.get(key)

await cache.close()
```

### Kafka

```python
from hyperi_pylib.kafka import KafkaClient, KafkaConsumer, KafkaProducer
```

Uses `confluent-kafka-python` (librdkafka) under the hood. Schema-registry
integration, health checks, and admin operations included.

### Secrets (multi-backend)

```python
from hyperi_pylib.secrets import SecretsManager

# Picks the configured backend: file, OpenBao/Vault, AWS, GCP, Azure
manager = SecretsManager.from_config()
api_key = await manager.get("stripe/api_key")
```

Two-tier caching (memory + disk), stale-cache fallback for backend outages.

### CLI Framework (`DfeApp`)

Subclass `DfeApp` to get a standard service-CLI lifecycle (`run`, `version`,
`config-check`) with no boilerplate. Config flows through the 8-layer cascade
automatically.

```python
from hyperi_pylib.cli import DfeApp, VersionInfo

class MyService(DfeApp):
    name = "my-service"
    env_prefix = "MY_SVC"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "1.0.0")

    async def run_service_async(self, config) -> None:
        # your service code
        ...

if __name__ == "__main__":
    MyService().cli()
```

> The `Dfe` prefix is internal naming (HyperI's data-services framework).
> A friendlier alias may land in a future release; the class is intentionally
> stable for now.

## Health Check Endpoints — The Probe Trinity

For services deployed to Kubernetes, hyperi-pylib's HTTP server provides
the three K8s probe types:

| Probe | Path | Checks | On failure |
|---|---|---|---|
| Startup | `/healthz/startup` | Init complete | K8s waits, then restarts |
| Liveness | `/healthz/live` | Process not deadlocked | Restart pod |
| Readiness | `/healthz/ready` | Deps healthy + ready flag set | Stop routing traffic |

Liveness MUST NEVER check downstream dependencies (a DB outage shouldn't
restart your replicas). Readiness checks dependencies AND requires an
explicit `set_ready()` call — cleared during graceful shutdown.

## Development

```bash
make quality   # lint, type-check, security audit
make test      # run test suite
make build     # build wheel
```

## License

[FSL-1.1-ALv2](LICENSE) — Functional Source License, transitions to Apache 2.0
after 2 years.

## Related

- **[hyperi-rustlib](https://github.com/hyperi-io/hyperi-rustlib)** — sister
  library for Rust services. Same opinions, same patterns, native Rust
  performance for hot-path workloads.
