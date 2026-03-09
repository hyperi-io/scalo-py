# hyperi-pylib Documentation

Production-ready infrastructure library for Python applications.

## Core Modules

hyperi-pylib provides modular infrastructure components that work together or independently:

| Module | Description | Documentation |
|--------|-------------|---------------|
| **logger** | Structured logging with RFC 3339 timestamps | [LOGGING.md](LOGGING.md) |
| **config** | 8-layer configuration cascade | [CONFIG.md](CONFIG.md) |
| **metrics** | Prometheus/OpenTelemetry metrics | [METRICS.md](METRICS.md) |
| **cache** | PostgreSQL-backed distributed cache | See module docstrings |
| **kafka** | Kafka producer/consumer/admin | [KAFKA.md](KAFKA.md) |
| **database** | Database URL construction | See module docstrings |
| **runtime** | Container-aware runtime paths | [RUNTIME-ARCHITECTURE.md](RUNTIME-ARCHITECTURE.md) |
| **anonymizer** | PII detection and anonymisation | [ANONYMIZER.md](ANONYMIZER.md) |
| **secrets** | Vault / AWS Secrets Manager providers | [SECRETS.md](SECRETS.md) |
| **cli** | DfeApp CLI framework | See module docstrings |
| **http** | httpx client with stamina retries | See module docstrings |
| **expression** | Common Expression Language (CEL) | See module docstrings |

## Quick Start

```bash
uv add hyperi-pylib
```

### Logging

```python
from hyperi_pylib.logger import logger, info, error, success

# Using convenience functions
info("Application starting", version="1.0.0")
error("Connection failed", database="prod-db", retry=3)
success("Task completed")

# Using logger object directly
logger.info("Processing user", user_id=123, action="login")
```

### Configuration

```python
from hyperi_pylib.config import settings

# Access configuration (automatic 8-layer cascade)
host = settings.get("database.host", "localhost")
port = settings.get("database.port", 5432)

# Environment variables auto-generated:
# database.host → DATABASE_HOST
```

### Metrics

```python
from hyperi_pylib.metrics import create_metrics

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
from hyperi_pylib.cache import configure_cache, cached

configure_cache(directory="/tmp/cache", default_ttl="1h")

@cached("api", key="{url}")
async def fetch_url(url: str) -> dict:
    ...

# PostgreSQL cache (multi-pod)
from hyperi_pylib.cache import PostgresCache, generate_cache_key

cache = PostgresCache(dsn="postgresql://user:pass@host/db")
await cache.init()

key = generate_cache_key("analytics", "events", org_id="acme")
await cache.set(key, {"data": [...]}, ttl_seconds=300)
value = await cache.get(key)
```

### Kafka

```python
from hyperi_pylib.kafka import KafkaProducer, KafkaConsumer

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
from hyperi_pylib.database import build_database_url

# Reads POSTGRES_HOST, POSTGRES_PORT, etc. from environment
postgres_url = build_database_url("postgresql")

# Reads REDIS_HOST, REDIS_PORT, etc.
redis_url = build_database_url("redis")
```

### Runtime Paths

```python
from hyperi_pylib.runtime import get_runtime_paths

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

- **[CLI Standards](CLI-STANDARDS.md)** - Typer/DfeApp framework standards
- **[Testing](TESTING.md)** - Testing patterns and best practices
- **[Profiles](PROFILES.md)** - Environment-based configuration profiles
- **[Secrets](SECRETS.md)** - Vault/AWS secrets management
- **[Kafka](KAFKA.md)** - Kafka client design and usage

## Installation Options

```bash
# Core only
uv add hyperi-pylib

# Common combinations
uv add "hyperi-pylib[metrics]"
uv add "hyperi-pylib[cache]"
uv add "hyperi-pylib[kafka]"
uv add "hyperi-pylib[secrets-vault]"
uv add "hyperi-pylib[secrets-aws]"
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | INFO |
| `LOG_FORMAT` | Log format (console/json) | auto-detect |
| `HYPERI_CONFIG_DSN` | PostgreSQL config loader DSN | unset |

## Repository

- **GitHub**: <https://github.com/hyperi-io/hyperi-pylib>
- **Issues**: <https://github.com/hyperi-io/hyperi-pylib/issues>

## License

See LICENSE file in repository.
