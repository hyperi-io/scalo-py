# Post-GA deferred review items

Items identified in the pre-GA ultrathink review (2026-05-27) that were
classified DEFERRED rather than BLOCKER or SHIP-NICE. Each is genuinely
defensible to ship without; they belong on the post-GA improvement
backlog rather than the release gate.

The review file the BLOCKER/SHIP-NICE items came from has been merged
into the branch as commits. This file is the residual.

## D1: HTTP client connection pool limits

**Issue:** `httpx.Client` / `httpx.AsyncClient` constructed without an
explicit `httpx.Limits(...)` object. The library accepts httpx defaults
(100 max_connections, 20 max_keepalive_connections) silently.

**Why deferred:** httpx defaults are sane for the typical pylib
consumer (an internal service making a few hundred outbound calls).
File descriptor exhaustion at the defaults requires sustained
high-concurrency abuse that the consumer would notice in their own
metrics first.

**Post-GA action:** expose `limits: httpx.Limits | None = None` on
`HttpClient.__init__` / `AsyncHttpClient.__init__`. Document the
defaults + a tuning recipe in `docs/api/HTTP.md`.

## D2: HTTP response body size limit

**Issue:** No cap on response body bytes. A misbehaving upstream or
attacker-controlled endpoint can stream unbounded bytes and OOM the
client process.

**Why deferred:** pylib HTTP consumers in our deployments only call
internal services. Untrusted upstreams are out of scope. If a future
consumer hits a public endpoint (webhook receiver, federation
endpoint), this becomes BLOCKER for them.

**Post-GA action:** add `max_response_bytes: int | None = None`
kwarg. Stream the body and raise on overrun. Document the trade-off
(some downstream APIs return large legitimate payloads -- caller must
opt in).

## D3: Config hot-reload / change callbacks

**Issue:** Config loaded once at module import (`config.config:_load_postgres_config_layer()`
runs at import time). No watcher, no change callback, no
`refresh()` API. To pick up new values, the app restarts.

**Why deferred:** static-at-startup config is what every consumer
service in our deployment expects. Hot-reload is a feature, not a
fix. Adding it touches Dynaconf's cascade ordering and requires
careful thread-safety review.

**Post-GA action:** if the use case appears (a long-running daemon
that should pick up rotated secrets or rebalanced quotas without a
pod restart), design a watcher + `refresh()` API. K8s pattern is
typically "rolling restart on ConfigMap change", which side-steps
this entirely.

## D4: Per-dependency Bulkhead convenience factories

**Issue:** Callers must remember to wrap each `run_blocking` call site
in a Bulkhead if they want isolation from the global anyio worker
thread pool (40 threads, shared across all `run_blocking` callers
process-wide). No `bulkhead_for("kafka", limit=16)` factory ships.

**Why deferred:** the Bulkhead primitive itself is documented; this
is ergonomic syntactic sugar, not a missing safety property. Pylib's
own code uses run_blocking without Bulkheads because none of the
internal call sites can starve the pool under realistic load.

**Post-GA action:** if profiling shows shared-pool contention between
subsystems (e.g. kafka producer stalls cache reads), add a small
factory function and document the recipe. Probably a 30-line PR.

## D5: Kafka producer `queue.buffering.max.messages` auto-tuning

**Issue:** Producer config defaults to librdkafka's
`queue.buffering.max.messages=100000`. No auto-tuning based on
broker count, partition count, or expected throughput.

**Why deferred:** librdkafka's default is well-chosen for general
use; auto-tuning would be a heuristic with no clearly-better answer.
The B7 fix already handles BufferError gracefully (poll + retry once)
so a saturated queue surfaces a clean exception rather than a silent
drop or deadlock.

**Post-GA action:** if a consumer reports sustained BufferError under
load, expose a tuning knob with documented guidance: typically
either increase `queue.buffering.max.messages` (more RAM, more
in-flight) or decrease `linger.ms` (smaller batches, more frequent
flush). No code change needed; just a doc page.

## D6: FastAPI `response_model` on health endpoints

**Issue:** `/health/live`, `/health/ready`, `/health/startup` return
`JSONResponse` with no Pydantic `response_model`. OpenAPI schema shows
`object` for the response body.

**Why deferred:** these endpoints are consumed by kubelet (which only
cares about the status code) and by ops dashboards (which parse the
JSON manually). No production caller generates a typed client from
the OpenAPI schema.

**Post-GA action:** if a UI tool starts generating types from the
schema, define a `HealthResponse` Pydantic model and add
`response_model=HealthResponse` to each route decorator. Trivial PR.

## D7: PostgresCache scheduled cleanup integration

**Issue:** `PostgresCache.cleanup_expired()` exists and works but no
background task auto-runs it. Stale rows accumulate until the caller
schedules it manually (or the lazy-delete-on-read path catches them
during `get()`).

**Why deferred:** scheduled background tasks are a deployment-shape
concern, not a library concern. Pylib doesn't ship an in-process
scheduler. Consumers either use APScheduler, a separate cron job, a
Kubernetes CronJob, or the `cleanup_expired()` call from their own
startup task -- each appropriate for different deployment shapes.

**Post-GA action:** document the four patterns in `docs/api/CACHE.md`
with copy-paste examples. No code change.

## D8: CircuitBreaker observability properties

**Issue:** `CircuitBreaker` exposes `state` and `name` publicly but
keeps `_consecutive_failures`, `_half_open_calls`, `_last_failure_time`
as private. A metrics scraper has to repeatedly poll `state` to infer
internal counters.

**Why deferred:** the recommended observability path is to wire
`CircuitBreakerMetrics` (already in `metrics/dfe_groups/circuit_breaker.py`)
into a `MetricsManager`. That gives Prometheus + OTel exporters
proper counters without exposing internal state via public properties
that lock in our representation.

**Post-GA action:** if a use case appears that needs to read counters
WITHOUT a metrics backend (e.g. a custom health check that
introspects breaker state), add `@property` accessors. Until then,
keep the encapsulation.

---

## Items that are emphatically NOT deferred (already shipped in this branch)

For the avoidance of doubt -- the following are DONE, not deferred:

- **B1, B2** -- Logger scrubs `record.extra` + exception chain args
- **B3** -- PostgresConfigError DSN masking
- **B4, B5, S3** -- Async health checks + per-check timeout +
  registration lock
- **B6, S1, S2, S6** -- DiskCache atomic write + 0o600 perms + KDF
  documentation + clear() error signal
- **B7** -- Async Kafka producer delivery-report future + BufferError
  retry
- **S4** -- CircuitBreaker probe context manager (releases slot on
  exception)
- **S5** -- CardinalityTracker LRU eviction (memory bounded)
- **S7, S8** -- HTTP traceparent + Idempotency-Key passthrough
- **S9** -- Sensitive-data filter regex pre-compilation
- **S10** -- Kafka client `__repr__` masks SASL/SSL credentials
- **S11** -- Obsoleted by license subsystem removal (OSS GA)
- **S12** -- Retry/CircuitBreaker composition documented + tests
