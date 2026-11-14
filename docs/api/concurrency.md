# Concurrency

Four async primitives, in the base package with no extra to install. `run_blocking`, `make_async` and `Bulkhead` are built on AnyIO and asyncer, so they run under asyncio or trio. `gather_with_timeouts` uses `asyncio.timeout` and `asyncio.gather`, so it needs asyncio. scalo's own health checks, Kafka async wrappers and secrets providers go through `run_blocking`.

```python
from scalo.concurrency import (
    run_blocking, make_async, Bulkhead, gather_with_timeouts,
)
```

Retry, circuit breaker and reconnect-and-retry are in [`resilience.md`](resilience.md). This module is the building blocks you wrap them around, and there is no decorator that does it for you, so compose them explicitly, as resilience.md's examples do.

---

## Quick start

```python
from scalo.concurrency import run_blocking, Bulkhead

aws_bulkhead = Bulkhead("aws-secrets", limit=32)

async def get_secret(path: str) -> bytes:
    async with aws_bulkhead:
        return await run_blocking(boto3_client.get_secret_value, SecretId=path)
```

---

## Discipline (the reason this module exists)

- Never call `loop.run_in_executor` directly. Use `run_blocking`.
- Never write `async def foo_async(...): return self.foo_sync(...)`, which blocks the event loop. Use `make_async` or the dual-API pattern below.
- Never share one global `ThreadPoolExecutor` across many downstreams. Use one `Bulkhead` per dependency.

---

## `run_blocking` -- sync-to-async bridge

```python
import anyio
from scalo.concurrency import run_blocking

async def read_config(path: Path) -> bytes:
    return await run_blocking(path.read_bytes)

# With a per-call concurrency limit
limiter = anyio.CapacityLimiter(8)
data = await run_blocking(expensive_sync_call, limiter=limiter)
```

Built on `anyio.to_thread.run_sync` for portable cancellation across
asyncio and trio. AnyIO's global limiter (40 threads) caps total thread
usage. Pass a per-dependency limiter or a `Bulkhead` for finer control.

| Arg | Default | What it does |
|-----|---------|--------------|
| `abandon_on_cancel` | `False` | If `False`, the task waits for the thread even when cancelled. Python cannot interrupt a running thread, so the wait keeps result handling deterministic. |
| `limiter` | AnyIO default (40) | `anyio.CapacityLimiter` to bound this specific call. |

---

## `make_async` -- dual-API pattern

When wrapping a sync library, implement `X_sync()` once and bind
`X_async = make_async(X_sync)` at class level:

```python
from scalo.concurrency import make_async

class FileProvider:
    def get_sync(self, path: str) -> bytes:
        return Path(path).read_bytes()

    get_async = make_async(get_sync)
```

`make_async` is `asyncer.asyncify`, so type checkers see the wrapped signature and the async version always offloads to a worker thread. The bad pattern, `async def foo(): return self.foo_sync()`, blocks the loop without a word. scalo's own `tests/unit/test_async_correctness.py` fails on it in scalo's code, and your code needs its own check.

---

## `Bulkhead` -- bounded concurrency per dependency

Pattern: one `Bulkhead` instance per `(service, endpoint)` pair. When
the in-flight count hits `limit`, the next async caller waits.

```python
from scalo.concurrency import Bulkhead

vault_bulkhead = Bulkhead("vault-read", limit=16)
db_bulkhead    = Bulkhead("postgres", limit=8)

async def fetch_with_isolation(path: str):
    async with vault_bulkhead:
        return await vault_client.read(path)
```

A slow Vault doesn't starve every other coroutine that needs Postgres, because each downstream has its own queue.

```mermaid
stateDiagram-v2
    [*] --> Available
    Available --> AtCapacity: limit reached
    AtCapacity --> Available: a call completes
    Available --> Available: enter while under the limit
    AtCapacity --> AtCapacity: enter waits
```

Built on `anyio.Semaphore`. `limit` must be `>= 1`.

---

## `gather_with_timeouts` -- parallel exec with per-task timeout

Each task gets its own `asyncio.timeout(per_task_timeout)`. Exceptions (including `TimeoutError`) are captured per task, so one slow check doesn't fail the others.

```python
from scalo.concurrency import gather_with_timeouts

results = await gather_with_timeouts(
    {
        "db":    lambda: db.ping(),
        "cache": lambda: cache.ping(),
    },
    per_task_timeout=1.0,
)

healthy = {k: v for k, v in results.items() if not isinstance(v, Exception)}
```

Values in the input dict are **coroutine factories**, not coroutines: passing a coroutine directly couples its lifetime to the gather call and prevents clean cancellation. Each factory must return an awaitable, so wrap a sync call in `run_blocking`.

It returns `dict[str, T | Exception]`. Inspect with `isinstance(v, Exception)` to separate success from failure.

---

## When to reach for which primitive

| You have | Reach for |
|----------|-----------|
| A sync function you must call from async code | `run_blocking` |
| A sync class you want to expose async methods on | `make_async` (one bind per method) |
| A downstream service that occasionally goes slow | `Bulkhead` around the call |
| A bunch of independent async health checks | `gather_with_timeouts` |
| Retry + circuit breaker + bulkhead | Compose `CircuitBreaker` / `ReconnectingResilience` from [`resilience.md`](resilience.md) with `Bulkhead` |
| Parallel CPU-bound work | Not this module -- use `ProcessPoolExecutor` or move to Rust |

---

## Anti-patterns

```python
# Don't
async def get_async(self, k):
    return self.get_sync(k)  # blocks the loop

# Do
get_async = make_async(get_sync)

# Don't
shared_pool = ThreadPoolExecutor(max_workers=32)
async def call_a():
    return await loop.run_in_executor(shared_pool, slow_a)
async def call_b():
    return await loop.run_in_executor(shared_pool, slow_b)
# Slow A starves B

# Do
bulkhead_a = Bulkhead("service-a", limit=16)
bulkhead_b = Bulkhead("service-b", limit=16)
async def call_a():
    async with bulkhead_a:
        return await run_blocking(slow_a)
```

---

## Related

- [resilience.md](resilience.md)
- [http-client.md](http-client.md)
- [secrets.md](secrets.md)
- [../core-pillars/health.md](../core-pillars/health.md)
- [../integration.md](../integration.md)
