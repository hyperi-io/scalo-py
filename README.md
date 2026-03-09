# hyperi-pylib

<!-- BADGES:START -->
[![Build Status](https://github.com/hyperi-io/hyperi-pylib/actions/workflows/ci.yml/badge.svg)](https://github.com/hyperi-io/hyperi-pylib/actions)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-FSL--1.1--ALv2-blue)](LICENSE)
<!-- BADGES:END -->

Enterprise infrastructure for all HyperI Python projects — configuration, logging, metrics, database utilities, Kafka, caching, and CLI framework.

## Features

Core modules, always installed:

| Module | Description |
|---|---|
| `logging` | Structured JSON logging with automatic sensitive data masking |
| `config` | 7-layer cascade (ENV → .env → YAML → defaults), container-aware |
| `runtime` | Container/K8s/local environment detection with standard path resolution |
| `database` | Connection URL builders for PostgreSQL, Redis, and others |
| `http` | httpx client with stamina retry support |
| `metrics` | Prometheus metrics (counters, gauges, histograms) |
| `expression` | Common Expression Language (CEL) evaluation |
| `cli` | `DfeApp` framework — subclass to get `run`/`version`/`config-check` for free |
| `harness` | Timeout monitors and utility helpers |
| `version-check` | Startup check for new hyperi-pylib releases |

## Installation

> **Package naming:** `hyperi-pylib` on PyPI, `hyperi_pylib` for Python imports.

```bash
# Core package
uv add hyperi-pylib

# With optional extras
uv add "hyperi-pylib[cache,kafka]"
```

### Optional Extras

| Extra | Installs | Why optional |
|---|---|---|
| `opentelemetry` | OpenTelemetry SDK + exporters | Large SDK set; only needed for OTel trace/metric export |
| `cache` | cashews + msgpack + psycopg3 | psycopg3 requires C binary; only needed for `PostgresCache` |
| `kafka` | confluent-kafka + genson | Heavy C extension (~10 MB); only Kafka services need it |
| `presidio` | Presidio analyser + anonymiser | Pulls in spaCy + ML models (~500 MB); very niche use |
| `secrets` | All backends: Vault + AWS + GCP + Azure | Full secrets stack — all cloud provider deps combined |
| `secrets-aws` | AWS Secrets Manager via boto3 | boto3 is large (~100 MB); only AWS-deployed services need it |
| `secrets-gcp` | GCP Secret Manager | grpcio + googleapis (~80-100 MB); only GCP-deployed services need it |
| `secrets-azure` | Azure Key Vault | azure-identity + azure-keyvault-secrets (~50 MB); only Azure-deployed services need it |

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

# Automatic cascade: ENV > .env > settings.yaml > defaults
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
