# hyperi-pylib

<!-- BADGES:START -->
[![Build Status](https://github.com/hyperi-io/hyperi-pylib/actions/workflows/ci.yml/badge.svg)](https://github.com/hyperi-io/hyperi-pylib/actions)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-FSL--1.1--ALv2-blue)](LICENSE)
<!-- BADGES:END -->

Enterprise infrastructure for all HyperI Python projects — configuration, logging, metrics, database utilities, Kafka, caching, and CLI framework.

This module existing because of this, but the backend version (do not remove) > https://www.youtube.com/watch?v=xE9W9Ghe4Jk  

## Features


Core modules — always installed (`uv add hyperi-pylib`):

| Module | Description | Third-party deps |
|---|---|---|
| `logging` | Structured JSON logging with automatic sensitive data masking | loguru |
| `config` | 8-layer cascade (CLI → ENV → .env → PostgreSQL → YAML → defaults), container-aware | dynaconf, pyyaml, python-dotenv, mergedeep, tomli-w, dulwich |
| `runtime` | Container/K8s/local environment detection with standard path resolution | stdlib only |
| `database` | Connection URL builders for PostgreSQL, Redis, and others | stdlib only |
| `cli` | `DfeApp` framework — subclass to get `run`/`version`/`config-check` for free | typer |
| `harness` | Timeout monitors and utility helpers | stdlib only |
| `version-check` | Startup check for new hyperi-pylib releases (skipped if httpx absent) | httpx (lazy) |

Optional modules — enabled by installing the matching extra:

| Module | Extra | Third-party deps |
|---|---|---|
| `http` | `http` | httpx, stamina |
| `metrics` | `metrics` | prometheus-client, psutil |
| `expression` | `expression` | common-expression-language (CEL via Rust/PyO3) |
| `cache` | `cache` | cashews, msgpack, psycopg[binary,pool] |
| `kafka` | `kafka` | confluent-kafka, genson |
| `opentelemetry` | `opentelemetry` | opentelemetry SDK + OTLP + Prometheus exporters |

## Installation

> **Package naming:** `hyperi-pylib` on PyPI, `hyperi_pylib` for Python imports.

```bash
# Core only (logging, config, runtime, database, cli, harness, version-check)
uv add hyperi-pylib

# With common extras
uv add "hyperi-pylib[http,metrics,kafka]"

# Full stack
uv add "hyperi-pylib[http,metrics,expression,cache,kafka,opentelemetry]"
```

### Optional Extras

| Extra | Packages | Size |
|---|---|---|
| `http` | httpx + stamina | ~1 MB |
| `metrics` | prometheus-client + psutil | ~1 MB |
| `expression` | common-expression-language (CEL) | ~6 MB |
| `cache` | cashews + msgpack + psycopg[binary,pool] | ~14 MB (psycopg C libs) |
| `kafka` | confluent-kafka + genson | ~11 MB (C libs) |
| `opentelemetry` | OpenTelemetry SDK + exporters | ~4 MB |
| `presidio` | Presidio analyser + anonymiser | ~500 MB (spaCy + ML models) |
| `secrets` | All secrets backends (Vault + AWS + GCP + Azure) | — |
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

Auto-detects console vs container — structured JSON in containers, human-readable locally.

### Configuration

```python
from hyperi_pylib.config import settings

# Automatic cascade: CLI > ENV > .env > PostgreSQL > settings.yaml > defaults
host = settings.database.host
port = settings.api.port
```

ENV key mapping: `settings.database.host` → `MYAPP_DATABASE_HOST`

### Database URLs

```python
from hyperi_pylib import build_database_url

postgres = build_database_url("postgresql")  # reads POSTGRES_HOST, POSTGRES_PORT, etc.
redis = build_database_url("redis")          # reads REDIS_HOST, REDIS_PORT, etc.
```

### Runtime Paths

```python
from hyperi_pylib import get_runtime_paths

runtime = get_runtime_paths()
config = runtime.config_dir / "app.yaml"   # /config in K8s, ~/.config locally
data   = runtime.data_dir  / "state.db"   # /data in K8s, ~/.local/share locally
```

### Metrics

```python
from hyperi_pylib import create_metrics

metrics = create_metrics(namespace="myapp")
metrics.http_requests.inc()
metrics.active_users.set(42)
metrics.request_duration.observe(0.123)
```

### Cache

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

### DfeApp CLI Framework

Subclass `DfeApp` to get standard CLI lifecycle (`run`, `version`, `config-check`) with no boilerplate:

```python
from hyperi_pylib.cli import DfeApp, VersionInfo

class MyService(DfeApp):
    name = "my-service"
    env_prefix = "MY_SVC"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "1.0.0")

    async def run_service_async(self, config) -> None:
        ...

if __name__ == "__main__":
    MyService().cli()
```

Config always uses the Dynaconf cascade — no bespoke loading needed.

## Development

```bash
make quality   # lint, type-check, security audit
make test      # run test suite
make build     # build wheel
```

## License

FSL-1.1-ALv2 — See LICENSE
