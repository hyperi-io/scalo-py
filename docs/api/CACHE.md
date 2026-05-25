# Cache

Two complementary caches behind one module. `cashews`-backed local cache
(SQLite via `diskcache`, in-process memory fallback) for per-pod
caching, and `PostgresCache` for state shared across many pods.

```
pip install hyperi-pylib[cache]
```

Pulls in `cashews`, `diskcache`, `msgpack`, and `psycopg`. The disk
backend is optional — falls back to in-memory cashews if `diskcache` is
missing.

---

## Quick start

```python
from hyperi_pylib.cache import configure_cache, cached

configure_cache(directory="/cache/myapp", default_ttl="1h",
                source_ttls={"http": "24h", "db": "30m"})

@cached("http", key="{url}")
async def fetch(url: str) -> dict:
    async with AsyncHttpClient() as c:
        return (await c.get(url)).json()
```

---

## Pick a backend

| Backend | Scope | When |
|---------|-------|------|
| Disk cache (cashews + diskcache) | Per-pod | Single-instance, expensive computations, fan-out to slow downstreams |
| In-memory (cashews `mem://`) | Per-process | Short-lived caches, tests, environments without `diskcache` |
| `PostgresCache` | Cluster-wide | Multi-pod deployments where every replica must see the same answer |

You can use both — disk for transient HTTP responses, Postgres for
materialised query results shared across analytics pods.

---

## Disk cache: `configure_cache`

Call once at startup, before any decorated function runs.

```python
from hyperi_pylib.cache import configure_cache
from hyperi_pylib.metrics import create_metrics

metrics = create_metrics("myapp")

configure_cache(
    directory="/cache/myapp",
    default_ttl="1h",
    source_ttls={
        "http":   "24h",
        "tavily": "1h",
        "db":     "30m",
        "file":   "12h",
    },
    size_limit=10 * 1024 * 1024 * 1024,  # 10 GiB
    metrics=metrics,                      # cache_hits_total / cache_misses_total
)
```

TTL strings follow cashews syntax — `30s`, `15m`, `2h`, `7d`. Per-source
TTL lets you tune cache freshness by the cost of regenerating the value:
cheap recomputes get short TTLs, expensive external calls get long ones.

---

## `@cached` decorator

```python
@cached("http", key="{url}")
async def fetch_url(url: str) -> dict: ...

@cached("db", key="{table}:{query_hash}", ttl="5m")  # override per-call
async def query(table: str, query_hash: str) -> list: ...

@cached("tavily", key="{query}")
async def search(query: str) -> list: ...
```

- `source` selects which TTL applies (looked up in `source_ttls`).
- `key` is a cashews template — placeholders are replaced from the
  function's named arguments.
- `ttl` overrides the source TTL for this specific decoration.
- The cache key is automatically prefixed with the source name —
  `http:https://example.com/api` — so `invalidate_source("http")`
  clears every HTTP entry without touching DB results.

---

## Manual get/set

```python
from hyperi_pylib.cache import get_cached, set_cached

value = await get_cached("http", "https://example.com/api")
if value is None:
    value = await fetch()
    await set_cached("http", "https://example.com/api", value)
```

When `metrics=` was passed to `configure_cache`,
`cache_hits_total{source="http"}` and `cache_misses_total{source="http"}`
counters tick over automatically.

---

## Invalidation

```python
from hyperi_pylib.cache import invalidate_source

await invalidate_source("http")    # clear every "http:*" entry
await invalidate_source("tavily")  # clear every "tavily:*" entry
```

Source-scoped — one expired API token doesn't blow away your slow
database results.

For finer control, the global cashews `cache` object is re-exported:

```python
from hyperi_pylib.cache import cache

await cache.delete("http:https://example.com/specific-url")
await cache.delete_match("http:*example.com*")
```

---

## `PostgresCache` — shared across pods

```python
from hyperi_pylib.cache import PostgresCache, generate_cache_key

cache = PostgresCache(dsn="postgresql://app:pw@db:5432/myapp")
await cache.init()                  # creates table + indexes if missing

key = generate_cache_key("clickhouse", "events_by_day",
                         org_id="acme", params={"date": "2026-05-25"})
await cache.set(key, result, ttl_seconds=300, namespace="clickhouse", org_id="acme")
value = await cache.get(key)

await cache.close()
```

Uses BYTEA + msgpack — any msgpack-serialisable value works. `init()`
creates the `cache_entries` table:

```sql
CREATE TABLE cache_entries (
    cache_key TEXT PRIMARY KEY,
    namespace TEXT NOT NULL DEFAULT 'default',
    org_id TEXT,
    value BYTEA NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    hit_count INTEGER DEFAULT 0,
    size_bytes INTEGER
);
```

Plus four indexes for lookups by expiry, namespace, org_id, and the
namespace+org_id pair.

---

## `PostgresCache` operations

| Method | Use |
|--------|-----|
| `get(key)` | Returns value or `None`. Lazy-deletes expired entries via a background task. |
| `set(key, value, ttl_seconds, namespace, org_id)` | Atomic upsert (`ON CONFLICT DO UPDATE`). |
| `delete(key)` | Returns `True` if a row was removed. |
| `exists(key)` | Cheap "is it still valid" check. |
| `invalidate_by_prefix(prefix)` | `DELETE WHERE cache_key LIKE 'prefix%'`. |
| `invalidate_by_namespace(namespace, org_id=None)` | Scoped purge. |
| `invalidate_by_org(org_id)` | Tenant-wide purge — useful after data load or tenant deletion. |
| `cleanup_expired()` | Run on a scheduler every few minutes. |
| `stats()` | `{entry_count, total_size_bytes, expired_count, namespaces}`. |

Hits increment `hit_count` via a fire-and-forget task so reads never
block on the counter update.

---

## Generating deterministic keys

```python
from hyperi_pylib.cache import generate_cache_key

key = generate_cache_key(
    namespace="clickhouse",
    identifier="events_by_day",
    org_id="acme",
    params={"start": "2026-05-01", "end": "2026-05-25"},
)
# → "clickhouse:acme:events_by_day:a1b2c3d4e5f6g7h8"
```

Params hashed via SHA-256 (truncated to 16 chars) and sorted before
hashing — argument order doesn't change the key.

---

## Lifecycle and shutdown

```python
cache = PostgresCache(dsn=...)
await cache.init()
# ... service runs ...
await cache.close()  # release pool, joined to your shutdown handler

# Or as a context manager
async with PostgresCache(dsn=...) as cache:
    ...
```

`cache.close()` returns the connection pool. The class re-uses
`psycopg_pool.AsyncConnectionPool` — sized via `pool_min_size` /
`pool_max_size` (defaults 2 / 10).

---

## Metrics

When `metrics=` is passed:

| Metric | Labels | Source |
|--------|--------|--------|
| `cache_hits_total` | `source` | Disk cache, `@cached` + `get_cached` |
| `cache_misses_total` | `source` | Disk cache, `@cached` + `get_cached` |
| `postgres_cache_hits_total` | `namespace` | `PostgresCache.get` |
| `postgres_cache_misses_total` | `namespace` | `PostgresCache.get` |

---

## Related

- [../INTEGRATION.md](../INTEGRATION.md)
- [HTTP-CLIENT.md](HTTP-CLIENT.md)
- [DATABASE.md](DATABASE.md)
- [CONCURRENCY.md](CONCURRENCY.md)
- [../core-pillars/METRICS.md](../core-pillars/METRICS.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
