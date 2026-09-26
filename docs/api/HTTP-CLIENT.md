# HTTP client

Sync and async HTTP clients built on `httpx`, with `stamina`-driven
retries (exponential backoff + jitter) and a 30 s default timeout.
Pylib wires `httpx + stamina + loguru`; Prometheus / structlog
hooks are Stamina-library opt-ins you wire at your own site if
needed. Replaces ad-hoc `requests` / `httpx` usage where Bandit's
B113 (request without timeout) keeps biting.

```
pip install scalo[http]
```

---

## Quick start

```python
from scalo.http import HttpClient

client = HttpClient(base_url="https://api.example.com")
response = client.get("/users/123")
data = response.json()
```

---

## Why this exists

- Default 30 s timeout silences Bandit B113 and stops hung connections
  from stealing a worker forever.
- Stamina retries cover the cases everyone forgets: transport errors and
  5xx server errors, with exponential backoff and jitter. 4xx errors
  surface immediately — retrying client errors is a bug.
- Stamina exposes Prometheus / structlog hooks; scalo-py does not wire
  them. If you want retry attempts on `/metrics`, follow Stamina's
  own setup at your site.
- `stamina.set_testing(True)` disables backoff in tests so suites stay
  fast and deterministic.

---

## Sync vs async

Pick by call site:

```python
# Sync — startup probes, CLI tools, hyperi-ci checks
from scalo.http import HttpClient

with HttpClient(base_url="https://api.example.com") as client:
    r = client.get("/health")
    assert r.status_code == 200

# Async — anything running inside an asyncio loop
from scalo.http import AsyncHttpClient

async with AsyncHttpClient(base_url="https://api.example.com") as client:
    r = await client.get("/users/123")
```

Both expose the same surface: `get`, `post`, `put`, `patch`, `delete`,
`head`, `options`. All return `httpx.Response`.

---

## Retry policy

```python
def _is_retryable(exc):
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return False
```

| Setting | Default |
|---------|---------|
| `attempts` | 3 (configurable via `retries=`) |
| `wait_initial` | 0.5 s |
| `wait_max` | 10 s |
| `wait_jitter` | 1.0 s |
| Retry on | `httpx.TransportError`, 5xx |
| Never retry on | 4xx |

Override via constructor:

```python
client = HttpClient(timeout=60.0, retries=5, base_url="https://slow.api")
```

`response.raise_for_status()` runs before each retry decision — 4xx
escapes immediately, 5xx feeds back into the retry loop.

---

## Passing through to httpx

Extra kwargs on the constructor flow into `httpx.Client(...)`:

```python
client = HttpClient(
    base_url="https://api.example.com",
    headers={"User-Agent": "my-service/1.0"},
    verify="/etc/ssl/ca-bundle.pem",
    follow_redirects=True,
    auth=("user", "pass"),
)
```

Extra kwargs on each call flow into `client.request(...)`:

```python
client.post("/data", json={"k": "v"}, headers={"X-Trace-Id": trace_id})
client.get("/search", params={"q": "term", "limit": 10})
```

---

## TLS

Both clients build their TLS context with `scalo.crypto.ssl_context` and the `PROD` profile: TLS 1.2 minimum, AES-256-GCM ciphers, peer certificate and hostname verified. `cafile=` or `capath=` trusts that CA in place of the system store, `crypto_profile=CryptoProfile.HIGHSEC` raises the minimum to TLS 1.3, and `crypto_profile=None` falls back to plain httpx defaults. Any `verify=` kwarg, like the CA bundle in the example above, replaces the scalo context outright.

Two environment variables change the context scalo builds. They are read when a client is constructed and apply to every client in the process that lets scalo build its context, including the OpenBao secrets provider. Each logs one warning per process when it takes effect.

| Variable | Default | Effect |
|---|---|---|
| `SCALO_TLS_VERIFY` | unset: verify | `false`, `0`, `no` or `off` stops checking the peer certificate and hostname. The TLS 1.2 minimum and cipher list stay. |
| `SCALO_TLS_ALLOW_WEAK` | unset: floor enforced | `true`, `1`, `yes` or `on` drops the minimum to TLS 1.0 and opens the cipher list at OpenSSL security level 0, which admits SHA-1, short keys and CBC. `HIGHSEC` ignores it. |

When to set them:

- `SCALO_TLS_VERIFY=false` is for a dev or test endpoint with a self-signed certificate. Anything on the network path can then impersonate the server, so never set it in production. Pointing `cafile=` at the issuing CA keeps verification on and is the better fix.
- `SCALO_TLS_ALLOW_WEAK=true` weakens TLS. It exists only for a legacy endpoint that cannot negotiate TLS 1.2 with AES-256-GCM, and only until that endpoint is upgraded. It applies to every client in the process, so to confine it to the one legacy peer pass `verify=scalo.crypto.ssl_context(allow_weak=True)` to that client instead.

---

## Lifecycle

Always close the client — connection pools and the underlying HTTP/2
multiplex live until you do.

```python
# Context manager (preferred)
with HttpClient() as client:
    ...

async with AsyncHttpClient() as client:
    ...

# Manual
client = HttpClient()
try:
    ...
finally:
    client.close()      # sync
    await client.aclose()  # async
```

---

## Observability

Pylib wires the HTTP client to `httpx + stamina + loguru` only.
Stamina has its own Prometheus / structlog integration hooks --
opt in at your own site if you want retry-attempt metrics or
structured retry logs. Pylib doesn't auto-wire them.

For request-level metrics (latency histograms, status-code counters)
wire the HTTP middleware from
[`core-pillars/METRICS.md`](../core-pillars/METRICS.md).

---

## Testing

```python
import stamina

def test_my_service():
    stamina.set_testing(True)  # No backoff between retries
    ...
```

Single global flag, no per-client wiring. Use `httpx`'s `MockTransport`
for fully offline tests:

```python
import httpx
from scalo.http import HttpClient

def handler(request):
    return httpx.Response(200, json={"ok": True})

# Pass a custom transport through to httpx.Client
client = HttpClient(transport=httpx.MockTransport(handler))
assert client.get("/anything").json() == {"ok": True}
```

---

## Errors

Errors that escape after retries are exhausted:

- `httpx.TransportError` — DNS, TCP, TLS, read/write errors
- `httpx.HTTPStatusError` — 5xx after `attempts` retries, or any 4xx
  immediately
- `httpx.TimeoutException` — exceeded `timeout` per attempt

Wrap with `try/except` at the call site; the clients never swallow
exceptions.

---

## When to reach for something else

- **Circuit breaker around downstream**: compose with
  [`RESILIENCE.md`](RESILIENCE.md)'s `CircuitBreaker`. The HTTP client
  itself is retry-only; circuit breaking is a separate concern.
- **Streaming responses**: drop down to raw `httpx` —
  `HttpClient._client` is the underlying instance if you really need it,
  but prefer building a sibling helper that exposes the bits you need.
- **HTTP/2 server push, WebSockets**: out of scope. Use `httpx` or
  `websockets` directly.

---

## Related

- [../INTEGRATION.md](../INTEGRATION.md)
- [RESILIENCE.md](RESILIENCE.md)
- [CONCURRENCY.md](CONCURRENCY.md)
- [../core-pillars/METRICS.md](../core-pillars/METRICS.md)
- [../core-pillars/LOGGING.md](../core-pillars/LOGGING.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
