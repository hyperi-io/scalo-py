# scalo

<!-- BADGES:START -->
<!-- Build Status badge omitted: the repo is private, so GitHub's Actions
     badge SVG 404s for anonymous PyPI viewers (shields.io can't read a
     private repo's status either). Re-add at the public-visibility flip:
     [![Build Status](https://github.com/hyperi-io/scalo-py/actions/workflows/ci.yml/badge.svg)](https://github.com/hyperi-io/scalo-py/actions) -->
[![PyPI](https://img.shields.io/pypi/v/scalo?logo=pypi)](https://pypi.org/project/scalo/)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
<!-- BADGES:END -->

> There's plenty of sage advice about running services in production at
> scale -- config cascades, structured logging, secret masking, Prometheus,
> OpenTelemetry, health probes, backpressure, graceful shutdown -- but almost
> none of it as code you can just install and use.
>
> This is that code.

scalo is an integrated runtime for control-plane services.
Config, logging and metrics come as one pre-wired trinity -- global singletons
you just use, no plumbing, no init dance. Everything else leans on that same
integration: the config cascade flows straight into the CLI so
`run`/`version`/`config-check` just work; the metrics and health wiring feed
the K8s probe trinity; and the deployment contract generates your Helm,
Dockerfile and Argo manifests from the config the app already declares.

Attach scalo to your service and a whole class of production pain -- the kind
done wrong a hundred times elsewhere -- just goes away. Battle-tested, and
almost no code on your side **to do it properly**. It's not a bag of utility
functions you wire up yourself; it's the wiring, done right, for free.

scalo comes in two halves that share one set of conventions, idiomatic in each
language. **scalo-py** (this package) is the **control plane** -- orchestration,
APIs and integration glue (`pip install scalo`). **scalo-rs** is the **data
plane** -- the Rust hot path where every microsecond and byte counts
(`cargo add scalo`).

## What this is (and isn't) for

**For:** control-plane APIs, UI backends, orchestrators, CLI tools,
integration glue, batch workloads, configuration management.

**Not for:** the hot path. If you're processing millions of messages
per second and shaving microseconds matters, that code belongs in
Rust -- see [scalo-rs](https://github.com/hyperi-io/scalo-rs). scalo-py
is "fast enough for control plane and integration"; scalo-rs is "fast
enough for the hot path".

We optimise scalo-py sensibly -- no gratuitously slow choices, no obvious
algorithmic mistakes -- but the lean is toward **stability,
expressiveness, and integration** rather than microseconds. Readable
abstractions beat inlined ones; clean composition beats hand-rolled
loops; heavier deps are acceptable when they earn their keep. This
design decision is why scalo-py allows substantial dependency trees and
doesn't agonise over async dispatch overhead. We don't hard-iterate the
hot path the way scalo-rs does, because that's scalo-rs's job.

This module exists because of this -- but for the backend:
<https://www.youtube.com/watch?v=xE9W9Ghe4Jk>

## What you get

Core modules - always installed (`uv add scalo`):

| Module | Description | Third-party deps |
|---|---|---|
| `logger` | Structured JSON logging with automatic PII masking and secrets filtering, container-aware output | loguru |
| `config` | 7-layer cascade (CLI -> ENV -> .env -> YAML -> defaults), container-aware path resolution | dynaconf, pyyaml, python-dotenv, mergedeep, tomli-w, dulwich |
| `runtime` | Auto-detects K8s / Docker / local, resolves config and data paths accordingly | stdlib only |
| `cli` | `ServiceApp` base class -- subclass to get `run` / `version` / `config-check` for free | typer |
| `version-check` | Optional startup check for new releases (no-op if `httpx` not installed) | httpx (lazy) |

Optional modules - install via extras:

| Module | Extra | Third-party deps |
|---|---|---|
| `http` | `http` | httpx, stamina (retry with jitter) |
| `metrics` | `metrics` | prometheus-client, psutil (auto-collects process/container metrics) |
| `expression` | `expression` | common-expression-language (CEL via Rust/PyO3) |
| `kafka` | `kafka` | confluent-kafka, genson |
| `opentelemetry` | `opentelemetry` | OpenTelemetry SDK + OTLP + Prometheus exporters |
| `secrets` | `secrets` | All backends (Vault/OpenBao + AWS + GCP + Azure) |
| `deployment` | `deployment` | pydantic (Dockerfile / Helm / Argo / compose generators) |

## Installation

```bash
# Core only (logger, config, runtime, cli, version-check)
uv add scalo

# With common extras
uv add "scalo[http,metrics,kafka]"

# Full stack
uv add "scalo[http,metrics,expression,kafka,opentelemetry,secrets,deployment]"
```

> **Package naming:** `scalo` on PyPI, `scalo` for Python imports.

### Optional Extras Sizes

| Extra | Packages | Approx size |
|---|---|---|
| `http` | httpx + stamina | ~1 MB |
| `metrics` | prometheus-client + psutil | ~1 MB |
| `expression` | CEL via Rust/PyO3 | ~6 MB |
| `kafka` | confluent-kafka + genson | ~11 MB (C libs) |
| `opentelemetry` | OpenTelemetry SDK + exporters | ~4 MB |
| `deployment` | pydantic | ~2 MB |
| `secrets` | All secrets backends | - |
| `secrets-vault` | OpenBao / HashiCorp Vault (uses `http` extra) | convenience marker |
| `secrets-aws` | AWS Secrets Manager via boto3 | ~100 MB |
| `secrets-gcp` | GCP Secret Manager | ~80-100 MB |
| `secrets-azure` | Azure Key Vault | ~50 MB |

## Quick Start

### Logging

```python
from scalo.logger import logger

logger.info("Service starting", version="1.0.0")
logger.error("DB connection failed", host="postgres", retry=3)
```

Auto-detects console vs container - structured JSON in containers, human-readable
locally. Sensitive fields (passwords, tokens, API keys, etc.) are masked
automatically.

### Configuration

```python
from scalo.config import settings

# Cascade: CLI args -> ENV -> .env -> settings.yaml -> defaults
host = settings.database.host
port = settings.api.port
```

ENV key mapping: `settings.database.host` -> `MYAPP_DATABASE_HOST` (prefix is
configurable per app).

### Runtime Paths (container-aware)

```python
from scalo import get_runtime_paths

runtime = get_runtime_paths("myapp")
config = runtime.config_dir / "app.yaml"   # /config in K8s, ~/.config locally
data   = runtime.data_dir  / "state.db"    # /data in K8s, ~/.local/share locally
```

### Metrics

```python
from scalo import create_metrics

metrics = create_metrics("myapp")
requests = metrics.counter("http_requests", "Total HTTP requests")
active   = metrics.gauge("active_users", "Signed-in users")
duration = metrics.histogram("request_duration", "Request duration (s)")

requests.inc()
active.set(42)
duration.observe(0.123)
```

Automatic process and container metrics (CPU, memory, FDs, uptime) come for
free - no extra wiring.

### Kafka

```python
from scalo.kafka import KafkaClient, KafkaConsumer, KafkaProducer
```

Uses `confluent-kafka-python` (librdkafka) under the hood. Schema-registry
integration, health checks, and admin operations included.

### Secrets (multi-backend)

```python
from scalo.secrets import SecretsManager

# Picks the configured backend: file, OpenBao/Vault, AWS, GCP, Azure
manager = SecretsManager.from_config(config)   # config dict per docs/api/SECRETS.md
api_key = await manager.get("stripe/api_key")
```

Two-tier caching (memory + disk), stale-cache fallback for backend outages.

### CLI Framework (`ServiceApp`)

Subclass `ServiceApp` to get a standard service-CLI lifecycle (`run`, `version`,
`config-check`) with no boilerplate. Config flows through the 7-layer cascade
automatically.

```python
from scalo.cli import ServiceApp, VersionInfo

class MyService(ServiceApp):
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

> `DfeApp` remains as a deprecated alias for `ServiceApp` to ease migration
> from `hyperi-pylib`; prefer `ServiceApp` in new code.

## Observability port - health and metrics

`ServiceApp` binds a dedicated observability listener on `--metrics-addr`
(default `0.0.0.0:9090`, env `METRICS_ADDR`) for the whole time the service
runs, and serves:

| Path | Purpose | On failure |
|---|---|---|
| `/metrics` | Prometheus scrape | - |
| `/livez` | Liveness - process not deadlocked | Restart pod |
| `/readyz` | Readiness - deps healthy + ready flag set | Stop routing traffic |

Those two are the whole surface - there are no aliases. A second path meaning
the same thing eventually stops meaning the same thing, and an alias that keeps
answering 200 hides a probe still aimed at a retired name.

Startup has no path of its own: aim `startupProbe` at `/livez`. Kubernetes
suspends liveness until the startup probe passes, so one path gives both a
generous boot budget and a tight liveness period without the two drifting.

This is a **separate port from your application's**, on purpose: exposing
user traffic must never expose the operator surface. Probe the
observability port in your manifests, not the traffic port.

Register checks and flip readiness on the manager scalo serves, or
`/readyz` will report something your service does not mean:

```python
class MyService(ServiceApp):
    name = "my-service"
    env_prefix = "MYAPP"

    def run_service(self, config):
        self.health().register_ready_check("db", db.is_connected)
        self.health().set_ready()
```

Liveness MUST NEVER check downstream dependencies (a DB outage shouldn't
restart your replicas). Readiness checks dependencies AND requires an
explicit `set_ready()` call - cleared during graceful shutdown.

The listener is stdlib-only, so it works without the FastAPI extra. Set
`serve_observability = False` on your `ServiceApp` for a service that has
no business binding a port (a one-shot CLI, say). A bind failure is fatal
by design - a service reporting healthy on a port nobody is listening to
is the failure this exists to prevent.

## Development

```bash
make quality   # lint, type-check, security audit
make test      # run test suite
make build     # build wheel
```

## License

[Apache-2.0](LICENSE). Third-party attributions are recorded in [NOTICE](NOTICE).

## Related

- **[scalo-rs](https://github.com/hyperi-io/scalo-rs)** -- sister library for
  Rust services. Same opinions, same patterns, native Rust performance for
  hot-path workloads.
- **[Migrating from hyperi-pylib](docs/MIGRATING-FROM-HYPERI-PYLIB.md)** --
  `scalo` is the renamed, Apache-2.0 continuation of `hyperi-pylib`; this guide
  covers the mechanical changes.
