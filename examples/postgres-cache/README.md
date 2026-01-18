# PostgreSQL Cache Example

Demonstrates hs-pylib's PostgreSQL cache backend for multi-pod deployments.

## Features

- Shared cache across multiple application pods
- Async connection pooling (psycopg3)
- TTL-based expiration with lazy cleanup
- Bulk invalidation by prefix, namespace, or org_id
- Cache statistics and hit/miss metrics
- msgpack serialisation for efficient storage

## Quick Start

```bash
# Start PostgreSQL
docker compose up -d

# Install dependencies
uv sync

# Run the example
uv run python main.py

# Run tests
uv run pytest

# Clean up
docker compose down -v
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Application                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │         PostgresCache (hs-pylib)                │   │
│  │  ┌─────────────┐  ┌─────────────────────────┐   │   │
│  │  │ Serialiser  │  │ AsyncConnectionPool     │   │   │
│  │  │ (msgpack)   │  │ (psycopg3)              │   │   │
│  │  └─────────────┘  └─────────────────────────┘   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │  Pod A  │      │  Pod B  │      │  Pod C  │
    └────┬────┘      └────┬────┘      └────┬────┘
         └────────────────┼────────────────┘
                          ▼
              ┌───────────────────────┐
              │      PostgreSQL       │
              │   cache_entries       │
              └───────────────────────┘
```

## API Usage

```python
from hs_pylib.cache import PostgresCache, generate_cache_key

# Initialise cache
cache = PostgresCache(dsn="postgresql://user:pass@host/db")
await cache.init()

# Generate deterministic keys
key = generate_cache_key("analytics", "events", org_id="acme")

# Set with TTL and namespace
await cache.set(key, {"data": [...]}, ttl_seconds=300, namespace="analytics")

# Get value
value = await cache.get(key)

# Bulk invalidation
await cache.invalidate_by_namespace("analytics")
await cache.invalidate_by_prefix("analytics:")
await cache.invalidate_by_org_id("acme")

# Statistics
stats = await cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.1%}")

# Clean up
await cache.close()
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_DSN` | PostgreSQL connection string | postgresql://postgres:postgres@localhost/cache_example |
| `CACHE_TABLE` | Cache table name | cache_entries |

## Docker Compose

The included `docker-compose.yml` starts PostgreSQL for local testing:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: cache_example
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
```

## See Also

- [hs-pylib Cache Documentation](../../docs/CACHE.md)
- [PostgreSQL Cache Implementation](../../src/hs_pylib/cache/postgres.py)
