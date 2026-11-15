# Resilience

Two primitives, both in the base package with no extra to install:

- `CircuitBreaker` -- trip-and-reject a one-shot outbound call. It runs the three-state machine (CLOSED / OPEN / HALF_OPEN) and the defaults of the breaker in scalo-rs's tiered sink, `src/tiered_sink/circuit.rs`. The API differs, and so do the behaviours listed under "Cross-language parity" below.
- `ReconnectingResilience` -- reconnect and retry a pooled connection through a transient outage, until it recovers or a budget runs out. It is for a dependency you hold a pool against (a ClickHouse client, or any other pooled backend) rather than a single request/response call. scalo-rs has no equivalent.

```python
from scalo.resilience import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError, CircuitState,
    ReconnectingResilience, ResilienceConfig, ServiceUnavailable, OutageState,
)
```

---

## Quick start

```python
cb = CircuitBreaker("payments", CircuitBreakerConfig(failure_threshold=3))

with cb:
    response = call_downstream()  # raises CircuitBreakerError if OPEN
```

---

## State machine

```mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: consecutive_failures >= failure_threshold
    OPEN --> HALF_OPEN: reset_timeout elapsed
    HALF_OPEN --> CLOSED: record_success()
    HALF_OPEN --> OPEN: record_failure()
```

| State | Behaviour |
|-------|-----------|
| `CLOSED` | All calls permitted. Successes reset the failure counter, failures increment it. Hitting `failure_threshold` consecutive failures opens the circuit. |
| `OPEN` | All calls rejected with `CircuitBreakerError`. After `reset_timeout` seconds elapses, the breaker auto-transitions to `HALF_OPEN` on the next state check. |
| `HALF_OPEN` | A small number of probe calls (`half_open_max_calls`, default 1) are permitted. A success closes the breaker and a failure reopens it. Subsequent calls during the probe window are rejected. A probe slot with no outcome once `reset_timeout` has passed since the newest probe was admitted is lost, and the next caller probes again. |

The OPEN -> HALF_OPEN transition is **lazy**: it happens the next time the state is read, not at the `reset_timeout` instant. Reading `cb.state` or calling `cb.is_call_permitted()` triggers the check.

---

## Configuration

```python
from scalo.resilience import CircuitBreakerConfig

cfg = CircuitBreakerConfig(
    failure_threshold=5,    # consecutive failures before opening
    reset_timeout=30.0,     # seconds to wait in OPEN before probing
    half_open_max_calls=1,  # number of probe calls in HALF_OPEN
)
```

Defaults match Rust: `failure_threshold=5`, `reset_timeout=30.0`,
`half_open_max_calls=1`.

---

## Sync usage

```python
from scalo.resilience import CircuitBreaker, CircuitBreakerError

cb = CircuitBreaker("payments")

try:
    with cb:
        response = payment_gateway.charge(amount)
except CircuitBreakerError:
    # OPEN, or HALF_OPEN with every probe slot taken -- short-circuit the caller
    return {"status": "queued_for_later"}
```

The context manager records a success on clean exit and a failure on any exception, and the exception always propagates (`__exit__` never returns truthy).

---

## Async usage

```python
cb = CircuitBreaker("kafka-broker-1")

async with cb:
    await producer.send(topic, key, value)
```

The async path delegates to the sync `__enter__` / `__exit__`, because taking the internal lock does no I/O. The breaker is safe for concurrent use from many tasks or threads via a `threading.Lock`.

---

## Manual record / probe

```python
if cb.is_call_permitted():
    try:
        do_thing()
        cb.record_success()
    except Exception:
        cb.record_failure()
        raise
```

Use the explicit `record_success` / `record_failure` API when you can't wrap the call in a `with` block, for example inside someone else's retry harness. `is_call_permitted()` is advisory and reserves no slot, so in HALF_OPEN two callers can both see `True`. Use `with cb:` or `cb.probe()` for atomic admission.

```python
cb.reset()  # force CLOSED, clear counters (operational override)
```

Atomic admission (no TOCTOU) for code that cannot use `with cb:`:

```python
with cb.probe() as acquired:
    if not acquired:
        return {"status": "queued_for_later"}  # OPEN, or HALF_OPEN with no slot free
    response = payment_gateway.charge(amount)
```

`cb.probe()` wraps `cb.try_acquire_probe()` and always records
success/failure on exit, even if the body raises before the caller
could record manually. Any exception is a failure, `asyncio.CancelledError`
included, so a cancelled probe reopens the circuit, which probes again
after `reset_timeout`, and the cancel is re-raised. CLOSED always returns `True`,
with no slot accounting. In HALF_OPEN it reserves one of `half_open_max_calls`
slots and returns `False` once they are all taken, and OPEN always returns
`False`. Call `try_acquire_probe()` directly only when you need the
True/False result without the context-manager cleanup. On `True` you
must then call `record_success()` or `record_failure()` yourself. A slot
never recorded is lost once `reset_timeout` has passed since the newest
probe was admitted, so a caller cancelled before it records cannot hold
the breaker HALF_OPEN for good. A call guarded by `with cb:` that runs
longer than `reset_timeout` loses its slot the same way.

---

## Inspect state

```python
state = cb.state           # CircuitState.CLOSED | OPEN | HALF_OPEN
permitted = cb.is_call_permitted()
name = cb.name             # the instance label
```

`cb.state` triggers the OPEN -> HALF_OPEN auto-transition if the reset timeout has elapsed, which lets a metric report "would this call go through?" without attempting the call.

---

## Composition with HTTP and bulkheads

A breaker around a downstream call layered with a `Bulkhead`:

```python
from scalo.concurrency import Bulkhead
from scalo.resilience import CircuitBreaker
from scalo.http import AsyncHttpClient

cb = CircuitBreaker("payments")
bulkhead = Bulkhead("payments", limit=16)
http = AsyncHttpClient(base_url="https://payments.example.com")

async def charge(amount: int):
    async with bulkhead:
        async with cb:
            return await http.post("/charge", json={"amount": amount})
```

Layer order: bulkhead **outside** the breaker, so a slow downstream that never trips the breaker still holds at most `limit` calls. While the breaker is OPEN it rejects inside the bulkhead at once, so a rejected call frees its slot straight away.

---

## Naming convention

One `CircuitBreaker` per `(downstream service, endpoint)` pair. Name
follows the dotted path of what's being protected:

```python
payments_cb = CircuitBreaker("payments.charge")
inventory_cb = CircuitBreaker("inventory.reserve")
vault_cb = CircuitBreaker("vault.read")
```

The name appears in `CircuitBreakerError` messages. Pass the same string as the `target` label of `CircuitBreakerMetrics` to graph the breaker.

---

## Cross-language parity (CircuitBreaker)

The Rust breaker is `scalo::tiered_sink::CircuitBreaker`, in `src/tiered_sink/circuit.rs`.

| Behaviour | scalo-py | scalo-rs |
|-----------|----------|----------|
| States | `closed`, `open`, `half_open` strings | `Closed`, `Open`, `HalfOpen` enum |
| Default threshold | 5 consecutive failures | 5, the tiered sink's `circuit_failure_threshold` |
| Default reset timeout | 30.0 seconds | 30 seconds, the tiered sink's `circuit_reset_timeout_ms` |
| OPEN -> HALF_OPEN | On any state read | Only on `allow_request()`, while `state()` reports `HalfOpen` without moving |
| Probes in HALF_OPEN | `half_open_max_calls`, default 1 | 1 |
| A probe that never reports | Lost once `reset_timeout` has passed since the newest probe was admitted, and the next caller probes. `probe()` and `with cb:` also count any exception as a failure, a cancel included | Lost once `reset_timeout` has passed since it went out, and the next caller probes |
| `reset()` | Force CLOSED, clear all counters | The same |
| Thread safety | `threading.Lock` | `std::sync::Mutex` |

---

## Errors (CircuitBreaker)

`CircuitBreakerError` is raised on entry when:

- The circuit is `OPEN`, or
- The circuit is `HALF_OPEN` and `half_open_max_calls` probes are
  already in flight.

The error message includes the breaker name. It is a plain `Exception` subclass, so catch it with `try/except CircuitBreakerError`.

---

## Reconnecting resilience

Where the breaker trip-and-rejects a one-shot outbound call, `ReconnectingResilience` reconnects and retries a **pooled** connection through a transient outage. A transient failure gives the caller a result or a `ServiceUnavailable`, and a non-transient error re-raises as it was. The caller injects the error classifiers and a name, so the same engine serves any pooled backend, a ClickHouse client among them.

```python
from scalo.resilience import ReconnectingResilience, ResilienceConfig, ServiceUnavailable
```

### Quick start

A call site that waits out a ClickHouse which is down or does not know its user yet:

```python
from scalo.resilience import ReconnectingResilience, ResilienceConfig

def is_transient(exc: Exception) -> bool:
    return isinstance(exc, (ConnectionError, RateLimited))  # worth retrying at all

def is_connection_outage(exc: Exception) -> bool:
    return isinstance(exc, ConnectionError)  # rebuild the pool; a rate-limit should not

retrying = ReconnectingResilience(
    ResilienceConfig(budget_seconds=60.0, waking_budget_seconds=300.0),
    name="ClickHouse",
    is_transient=is_transient,
    is_reconnectable=is_connection_outage,
    reconnect=lambda: client.close(),  # tear down; the next attempt rebuilds it
)

try:
    rows = retrying.run(lambda: client.query("SELECT 1"))
except ServiceUnavailable as exc:
    # exc.waking is True if a warm-up hook fired (extended cold-start budget)
    return {"status": 503, "detail": str(exc)}
```

`run()` returns `op()`'s result on the first success. A non-transient
error (a syntax error, an auth failure `is_transient` does not classify
as retryable) re-raises immediately, un-retried. A transient error backs
off exponentially (`wait_initial` -> `wait_max`, multiplied by
`wait_multiplier` each attempt) and retries until `budget_seconds` runs
out, then raises `unavailable_exc` (default `ServiceUnavailable`).

A caller that wants to wait out an outage forever, with nothing else to do until the dependency comes back, sets `budget_seconds=math.inf` and `waking_budget_seconds=math.inf`. `run()` then never raises `ServiceUnavailable`, though a non-transient error still re-raises.

### `ResilienceConfig`

Back-off and budget knobs, a dataclass the app fills from its config so an operator widens the budget for a slow cold start without a code change:

| Field | Default | Meaning |
|-------|---------|---------|
| `enabled` | `True` | `False` runs `op()` once, un-retried -- a kill switch. |
| `wait_initial` | `0.5` | First back-off, in seconds. |
| `wait_max` | `10.0` | Back-off cap per attempt (the poll cadence once ramped). |
| `wait_multiplier` | `2.0` | Exponential factor applied each retry. |
| `budget_seconds` | `60.0` | Total time budget for a plain transient outage before raising. |
| `waking_budget_seconds` | `300.0` | Extended budget once a warm-up hook reports `WAKING` (cold start). |

### `ReconnectingResilience(config, *, name, is_transient, is_reconnectable, reconnect, on_connect_failure=None, unavailable_exc=ServiceUnavailable, sleep=time.sleep, now=time.monotonic)`

| Argument | Type | Meaning |
|----------|------|---------|
| `config` | `ResilienceConfig` | The back-off + budget knobs. |
| `name` | `str` | The dependency's name, for log lines (`"ClickHouse"`, ...). |
| `is_transient` | `Callable[[Exception], bool]` | `True` when an error is worth retrying at all (a connection outage OR a rate-limit). `False` for a query or logic error, which re-raises immediately un-retried. |
| `is_reconnectable` | `Callable[[Exception], bool]` | `True` when an error is a CONNECTION outage (rebuild the pool between attempts). `False` for a transient-but-connected error (e.g. a rate-limit), where reconnecting would be wrong. |
| `reconnect` | `Callable[[], None]` | Tears down the pooled client so the next attempt rebuilds a fresh one. Called only when `is_reconnectable` was `True`. |
| `on_connect_failure` | `Callable[[], bool] \| None` | Optional warm-up hook, called once when a CONNECTION outage begins. Returning `True` extends the budget to `waking_budget_seconds` and flips the state to `WAKING`. A hook that raises is caught and logged, and the outage is then treated as plain `TRANSIENT`. |
| `unavailable_exc` | `type[ServiceUnavailable]` | The exception type raised when the budget is exhausted. Subclass it so a backend keeps its own typed exception that its surface already catches. |
| `sleep` / `now` | `Callable` | Injectable clock, so tests pass fakes that never really sleep or race real time. |

Methods and properties:

- `run(op: Callable[[], T]) -> T` -- execute `op`, retrying a transient error with exponential back-off, see "Quick start" above.
- `state -> OutageState` -- the current outage state, for a health or readiness probe.
- `healthy -> bool` -- `state == OutageState.HEALTHY`.

### Outage states

```python
from scalo.resilience import OutageState
```

| State | Meaning |
|-------|---------|
| `HEALTHY` | The last operation succeeded. |
| `TRANSIENT` | Backing off after a failure that was not a connection outage (or no warm-up hook fired). |
| `WAKING` | Backing off after a connection outage whose warm-up hook returned `True`: a known cold start, not a dead dependency. |
| `DEAD` | The budget ran out. The next `run()` call that fails starts a fresh outage from `TRANSIENT`/`WAKING`. |

### Errors (ReconnectingResilience)

`ServiceUnavailable(message, *, waking=False)` is raised by `run()` when
the resilience budget is exhausted. A surface maps it to `503`
(retryable), never a `500`/crash. `exc.waking` is `True` when the outage
was a known warm-up, so the surface can say "warming up" instead of
"down". Pass a subclass as `unavailable_exc` to raise a backend-specific
type instead.

The message counts the calls `run()` made, the first one included, so a `budget_seconds=0.0` outage reads `ClickHouse unreachable after 0s (1 attempt): <last error>`. The `<name> recovered` and `<name> unavailable after resilience budget exhausted` log lines carry the same count in their `attempts` field.

### When to reach for which

| You have | Reach for |
|----------|-----------|
| A one-shot outbound call (HTTP request, RPC) that should fail fast once a downstream is known-bad | `CircuitBreaker` |
| A pooled connection (a DB client, a broker connection) that should reconnect and retry through a transient outage | `ReconnectingResilience` |
| Both -- a pooled client behind a breaker that also protects callers who are not retrying | Layer them: breaker around the pool's call sites, `ReconnectingResilience` inside the pool's own reconnect logic |

---

## Related

- [concurrency.md](concurrency.md)
- [http-client.md](http-client.md)
- [secrets.md](secrets.md)
- [scaling.md](scaling.md)
- [../core-pillars/metrics.md](../core-pillars/metrics.md)
- [../integration.md](../integration.md)
