# hyperi-pylib

<!-- BADGES:START -->
[![Build Status](https://github.com/hyperi-io/hyperi-pylib/workflows/CI/badge.svg)](https://github.com/hyperi-io/hyperi-pylib/actions)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-FSL--1.1--ALv2-blue)](LICENSE)
<!-- BADGES:END -->

Enterprise infrastructure for all HyperI Python projects — configuration, logging, metrics, database utilities, Kafka, caching, and CLI framework.

## Features

- **Logging**: Structured JSON logging with automatic sensitive data masking
- **Configuration**: 7-layer cascade (ENV → .env → YAML → defaults), container-aware
- **Runtime**: Container/K8s/local environment detection with standard path resolution
- **Database**: Connection URL builders for PostgreSQL, Redis, and others
- **Metrics**: Prometheus and OpenTelemetry backends
- **Kafka**: Producer, consumer, admin client, and schema analysis
- **Cache**: PostgreSQL-backed distributed cache (msgpack serialisation, psycopg3)
- **HTTP**: httpx-based client with stamina retry support
- **Secrets**: Vault and AWS Secrets Manager providers
- **PII Anonymisation**: ML-based anonymisation via Presidio
- **Expression**: Common Expression Language (CEL) evaluation
- **CLI**: `DfeApp` framework — subclass to get `run`/`version`/`config-check` for free
- **Harness**: Timeout monitors and utility helpers

## Installation

> **Package naming:** `hyperi-pylib` on PyPI, `hyperi_pylib` for Python imports.

```bash
# Core package
uv add hyperi-pylib

# With optional extras
uv add "hyperi-pylib[metrics,cache,kafka]"
```

### Optional Extras

| Extra | Installs |
|---|---|
| `metrics` | Prometheus client |
| `opentelemetry` | OpenTelemetry SDK + exporters |
| `cache` | cashews + msgpack + psycopg3 |
| `kafka` | confluent-kafka + genson |
| `http` | httpx + stamina |
| `api` | FastAPI + uvicorn |
| `presidio` | Presidio analyser + anonymiser |
| `expression` | Common Expression Language |
| `secrets-vault` | OpenBao/Vault via httpx |
| `secrets-aws` | AWS Secrets Manager via boto3 |
| `secrets-all` | All secrets providers |
| `license` | License validation (cryptography + httpx) |
| `version-check` | Version update checks (httpx) |

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
# Full QA pipeline (lint, type-check, security, tests, build)
ci/scripts/local/build-local.sh
```

## License

FSL-1.1-ALv2 — See LICENSE
