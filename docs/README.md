# hs-pylib Documentation

Production-ready infrastructure library for Python applications.

## Core Modules

hs-pylib provides modular infrastructure components that work together or independently:

| Module | Description | Documentation |
|--------|-------------|---------------|
| **logger** | Structured logging with RFC 3339 timestamps | [LOGGING.md](LOGGING.md) |
| **config** | 7-layer configuration cascade | [CONFIG.md](CONFIG.md) |
| **metrics** | Prometheus/OpenTelemetry metrics | [METRICS.md](METRICS.md) |
| **cache** | Disk and PostgreSQL caching | See module docstrings |
| **kafka** | Kafka producer/consumer/admin | See module docstrings |
| **database** | Database URL construction | See module docstrings |
| **runtime** | Container-aware runtime paths | [RUNTIME-ARCHITECTURE.md](RUNTIME-ARCHITECTURE.md) |
| **anonymizer** | PII detection and anonymisation | [ANONYMIZER.md](ANONYMIZER.md) |

## Quick Start

```bash
pip install hs-pylib
```

### Logging

```python
from hs_pylib.logger import logger, info, error, success

# Using convenience functions
info("Application starting", version="1.0.0")
error("Connection failed", database="prod-db", retry=3)
success("Task completed")

# Using logger object directly
logger.info("Processing user", user_id=123, action="login")
```

### Configuration

```python
from hs_pylib.config import settings

# Access configuration (automatic 7-layer cascade)
host = settings.get("database.host", "localhost")
port = settings.get("database.port", 5432)

# Environment variables auto-generated:
# database.host → DATABASE_HOST
```

### Metrics

```python
from hs_pylib.metrics import create_metrics

metrics = create_metrics(namespace="myapp")

# Create metrics
requests = metrics.counter("http_requests", "Total requests", ["method"])
requests.labels(method="GET").inc()

active = metrics.gauge("active_users", "Active users")
active.set(42)

duration = metrics.histogram("request_duration", "Request duration")
duration.observe(0.123)

# Export for Prometheus
print(metrics.export())
```

### Caching

```python
# Disk cache (single pod)
from hs_pylib.cache import configure_cache, cached

configure_cache(directory="/tmp/cache", default_ttl="1h")

@cached("api", key="{url}")
async def fetch_url(url: str) -> dict:
    ...

# PostgreSQL cache (multi-pod)
from hs_pylib.cache import PostgresCache, generate_cache_key

cache = PostgresCache(dsn="postgresql://user:pass@host/db")
await cache.init()

key = generate_cache_key("analytics", "events", org_id="acme")
await cache.set(key, {"data": [...]}, ttl_seconds=300)
value = await cache.get(key)
```

### Kafka

```python
from hs_pylib.kafka import KafkaProducer, KafkaConsumer

# Producer
producer = KafkaProducer({"bootstrap.servers": "localhost:9092"})
producer.produce("my-topic", key=b"key", value=b'{"event": "test"}')
producer.flush()

# Consumer
consumer = KafkaConsumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "my-group",
})
consumer.subscribe(["my-topic"])
for msg in consumer:
    print(msg.value())
```

### Database URLs

```python
from hs_pylib.database import build_database_url

# Reads POSTGRES_HOST, POSTGRES_PORT, etc. from environment
postgres_url = build_database_url("postgresql")

# Reads REDIS_HOST, REDIS_PORT, etc.
redis_url = build_database_url("redis")
```

### Runtime Paths

```python
from hs_pylib.runtime import get_runtime_paths

runtime = get_runtime_paths()
config_file = runtime.config_dir / "app.yaml"   # /config or ~/.config
data_file = runtime.data_dir / "state.db"       # /data or ~/.local/share
# Same code works in K8s, Docker, and local development
```

## Working Examples

See the [examples/](../examples/) directory for complete, runnable projects:

- **[basic-logging](../examples/basic-logging/)** - Structured logging demonstration
- **[config-cascade](../examples/config-cascade/)** - Configuration system
- **[postgres-cache](../examples/postgres-cache/)** - PostgreSQL cache for multi-pod
- **[kafka-producer-consumer](../examples/kafka-producer-consumer/)** - Kafka client usage
- **[fastapi-metrics](../examples/fastapi-metrics/)** - Prometheus metrics with FastAPI

## Additional Documentation

- **[CLI Standards](CLI-STANDARDS.md)** - Typer framework standards
- **[Testing](TESTING.md)** - Testing patterns and best practices
- **[Container Deployment](CONTAINER_DEPLOYMENT.md)** - Docker and Kubernetes deployment
- **[Profiles](PROFILES.md)** - Environment-based configuration profiles

## Installation Options

```bash
# Core only
pip install hs-pylib

# With caching (cashews + psycopg)
pip install hs-pylib[cache]

# With metrics
pip install hs-pylib[metrics]

# All features
pip install hs-pylib[all]
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | INFO |
| `HS_LOG_FORMAT` | Log format (console/json) | auto-detect |
| `HS_CONFIG_DSN` | PostgreSQL config loader DSN | unset |

## Repository

- **GitHub**: <https://github.com/hypersec-io/hs-pylib>
- **Issues**: <https://github.com/hypersec-io/hs-pylib/issues>

## Deprecated: Application Framework

The `Application.*` framework (API, CLI, Daemon, MCP, Oneshot types) was removed in v2.13.6.
It was experimental and had zero production usage. The documentation files (APP-*.md) are
preserved for reference but describe code that is no longer available.

Use the modular APIs directly (logger, config, metrics, etc.) for production code.
See the [examples/](../examples/) directory for current usage patterns.

## License

See LICENSE file in repository.
