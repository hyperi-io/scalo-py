# Database

Two distinct concerns under one doc:

1. **Connection URL builders** (`hyperi_pylib.database`) — construct
   `postgresql://`, `mysql://`, `mongodb://`, `redis://`,
   `clickhouse://`, `sqlite://` URLs from env vars or kwargs.
2. **PostgreSQL data store** (`hyperi_pylib.config.postgres_loader`) —
   the async loader that reads `config_values` rows for the standard
   config cascade. The config-cascade integration itself is documented
   in [`../core-pillars/CONFIG.md`](../core-pillars/CONFIG.md); this doc
   covers the loader API for callers who want to read or write
   `config_values` directly.

```
pip install hyperi-pylib   # builders only, no DB driver (the [database] extra is a marker for documentation; add psycopg / pymongo / etc. directly)
```

---

## Quick start

```python
from hyperi_pylib.database import build_database_url

# Reads POSTGRES_HOST / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DATABASE
db_url = build_database_url("postgresql")
engine = create_engine(db_url)
```

---

## Connection URL builders

### Auto-detection from env vars

```python
from hyperi_pylib.database import build_database_url

postgres_url = build_database_url("postgresql")   # POSTGRES_*
mysql_url    = build_database_url("mysql")        # MYSQL_*
mongo_url    = build_database_url("mongodb")      # MONGO_*
redis_url    = build_database_url("redis")        # REDIS_*
clickhouse   = build_database_url("clickhouse")   # CLICKHOUSE_*
```

The builder reads the standard cloud-native names (`POSTGRES_HOST`,
`POSTGRES_USER`, etc.), substitutes any kwargs you pass, and URL-encodes
the username and password before assembling the URL. Default ports are
applied per database type when `*_PORT` isn't set.

### Custom prefixes for multi-database services

```python
# Service has two PostgreSQL connections — primary and replica
primary  = build_database_url("postgresql", env_prefix="PRIMARY")
# Reads PRIMARY_HOST / PRIMARY_USER / PRIMARY_PASSWORD / PRIMARY_DATABASE

replica  = build_database_url("postgresql", env_prefix="REPLICA")
```

### Inspect the parsed config

```python
from hyperi_pylib.database import get_database_config

config = get_database_config("postgresql")
# {"host": "...", "port": 5432, "user": "...", "password": "...",
#  "database": "...", "sslmode": "prefer", "connect_timeout": "10"}
```

### Parse an existing URL

```python
from hyperi_pylib.database import parse_database_url

parts = parse_database_url("postgresql://u:p@db:5432/app?sslmode=require")
# {"scheme": "postgresql", "host": "db", "port": 5432, "user": "u",
#  "password": "p", "database": "app", "params": {"sslmode": "require"}}
```

### Env-or-DSN

```python
from hyperi_pylib.database import get_database_url_from_env

url = get_database_url_from_env("DATABASE_URL", fallback_type="postgresql")
# Reads DATABASE_URL if set, otherwise builds from POSTGRES_* env vars.
# Returns None if neither is configured.
```

### Standard env-var names

| DB | Vars (also accepts `*_SERVICE_HOST` / `*_SERVICE_PORT` from K8s) |
|----|------------------------------------------------------------------|
| PostgreSQL | `POSTGRES_*`, `POSTGRESQL_*`, `PG_*` |
| MySQL / MariaDB | `MYSQL_*`, `MARIADB_*` |
| MongoDB | `MONGODB_*`, `MONGO_*` |
| Redis | `REDIS_*` |

Port values are validated (1–65535), Redis DB numbers are validated
(`>= 0`), and out-of-range values raise `ValueError` with the offending
env-var name in the message.

### Convenience wrappers

```python
from hyperi_pylib.database import (
    get_postgresql_url, get_mysql_url, get_mongodb_url, get_redis_url,
)

url = get_postgresql_url(host="db", database="app")
```

Equivalent to `build_database_url("postgresql", **kwargs)` — there for
readability when you're only ever using one database type.

---

## PostgreSQL data store: `PostgresConfigLoader`

The loader backs the optional PostgreSQL layer of the standard config
cascade. Enable it by setting `HYPERI_CONFIG_DSN`; the loader is
discoverable for direct use too.

### Direct loader

```python
from hyperi_pylib.config.postgres_loader import (
    PostgresConfigLoader, PostgresConfigError, PostgresConfigUnavailable,
)

loader = PostgresConfigLoader(
    dsn="postgresql://app:pw@db:5432/app",
    namespace="my-app",
)
config = await loader.load()    # dict — flat key→value
```

`load()` returns the cached dict if the TTL hasn't elapsed; otherwise
queries PostgreSQL and refreshes the cache. The cache is class-level,
so multiple `PostgresConfigLoader` instances pointing at the same DSN +
namespace share state.

### Default loader

```python
from hyperi_pylib.config.postgres_loader import get_default_loader

loader = get_default_loader()   # reads HYPERI_CONFIG_* env vars; returns
                                # None when HYPERI_CONFIG_DSN is unset
```

### Schema

```sql
CREATE TABLE IF NOT EXISTS config_values (
    namespace  TEXT NOT NULL DEFAULT 'default',
    key        TEXT NOT NULL,
    value      JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    PRIMARY KEY (namespace, key)
);

CREATE INDEX idx_config_namespace ON config_values (namespace);
CREATE INDEX idx_config_key_prefix ON config_values
    USING btree (key text_pattern_ops);
```

Optional `config_values_history` audit table is created when
`ensure_table(with_audit=True)` is called.

### Configuration via env vars

| Env var | Default | Purpose |
|---------|---------|---------|
| `HYPERI_CONFIG_DSN` | (required) | PostgreSQL DSN. |
| `HYPERI_CONFIG_TABLE` | `config_values` | Table name. |
| `HYPERI_CONFIG_NAMESPACE` | `default` | Per-app isolation. |
| `HYPERI_CONFIG_CACHE_TTL` | `60` | Cache TTL (s). |
| `HYPERI_CONFIG_CONNECT_TIMEOUT` | `5` | Connect timeout (s). |
| `HYPERI_CONFIG_QUERY_TIMEOUT` | `10` | Query timeout (s). |
| `HYPERI_CONFIG_RETRY_ATTEMPTS` | `3` | Retry attempts. |
| `HYPERI_CONFIG_RETRY_DELAY_MS` | `1000` | Delay between retries (ms). |
| `HYPERI_CONFIG_OPTIONAL` | `true` | If `false`, raise on PG failure. |
| `HYPERI_CONFIG_FALLBACK_ENABLED` | `false` | Write a local fallback file. |
| `HYPERI_CONFIG_FALLBACK_FILE` | `/tmp/{namespace}_config_fallback.yaml` | Fallback file path. |
| `HYPERI_CONFIG_FALLBACK_MODE` | `replace` | `replace` or `merge`. |

### Fallback file

When `HYPERI_CONFIG_FALLBACK_ENABLED=true`, every successful load
serialises the result to a local YAML file. If PostgreSQL is later
unavailable, the loader reads the fallback file — your service stays
up through a database outage. The default path is
`/tmp/{namespace}_config_fallback.yaml`; override with
`HYPERI_CONFIG_FALLBACK_FILE`.

### Exceptions

| Exception | When |
|-----------|------|
| `PostgresConfigError` | base class — connection failures, query errors |
| `PostgresConfigUnavailable` | PostgreSQL unreachable in optional mode (loader returns `{}` and you may want to warn) |

In **optional mode** (`HYPERI_CONFIG_OPTIONAL=true`, the default), a
PostgreSQL outage causes `PostgresConfigUnavailable` to be logged as a
warning and `load()` returns the last known good cache (or the fallback
file, or `{}`). In **strict mode** (`HYPERI_CONFIG_OPTIONAL=false`), the
loader raises and startup fails.

---

## Cascade priority

PostgreSQL configuration sits at priority 4 in the 8-layer cascade —
above file-based configuration, below env vars and CLI args:

```
1. CLI args               (--host=X)
2. ENV vars               (MYAPP_DATABASE_HOST=...)
3. .env file              (.env)
4. PostgreSQL             (config_values table)    ← this loader
5. settings.<env>.yaml
6. settings.yaml
7. defaults.yaml
8. Hard-coded fallback
```

Full cascade rules: [`../core-pillars/CONFIG.md`](../core-pillars/CONFIG.md).

---

## Related

- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [DIRECTORY-CONFIG.md](DIRECTORY-CONFIG.md)
- [CACHE.md](CACHE.md)
- [SECRETS.md](SECRETS.md)
- [../runtime/RUNTIME-CONTEXT.md](../runtime/RUNTIME-CONTEXT.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
