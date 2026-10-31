# HTTP client

Sync and async HTTP clients built on `httpx`, with `stamina`-driven
retries (exponential backoff + jitter) and a 30 s default timeout.
stamina's own retry hooks log and count each retry (see [Observability](#observability)). Replaces ad-hoc `requests` / `httpx` usage where Bandit's
B113 (request without timeout) keeps biting.

```bash
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
- A retry is logged and counted by stamina's default hooks, which name the error by class and status only, never the request URL.
- `stamina.set_testing(True)` disables backoff in tests so suites stay
  fast and deterministic.

---

## Sync vs async

Pick by call site:

```python
# Sync — startup probes, CLI tools, CI checks
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
    if isinstance(exc, (httpx.LocalProtocolError, httpx.UnsupportedProtocol)):
        return False
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
| Retry on | `httpx.TransportError` other than `httpx.LocalProtocolError` and `httpx.UnsupportedProtocol`, 5xx |
| Never retry on | 4xx, `httpx.LocalProtocolError`, `httpx.UnsupportedProtocol` |
| Methods retried | GET, HEAD, PUT, DELETE and OPTIONS always. POST and PATCH only with an idempotency key, or `retry_non_idempotent=True` on the client |

Both mean httpx refused to send the request, so they are raised at once. `httpx.LocalProtocolError` comes from a header value holding a line break, and `httpx.UnsupportedProtocol` from a URL with no `http://` or `https://` scheme. The `LocalProtocolError` message quotes the refused header value, which can be a credential. scalo's logger masks that value whatever its auth scheme (see [Layer 2](../core-pillars/logging.md#layer-2-field-name-regex)), and any other log path needs to log the class rather than the text.

Override via constructor:

```python
client = HttpClient(timeout=60.0, retries=5, base_url="https://slow.api")
```

`response.raise_for_status()` runs before each retry decision — 4xx
escapes immediately, 5xx feeds back into the retry loop.

POST and PATCH are sent once by default, because a request that timed out or came back 5xx may already have been applied, and a resend would apply it twice. A request opts in with `idempotency_key=` (or its own `Idempotency-Key` header), which a deduplicating service such as Stripe or AWS honours. A client whose endpoint dedupes, or whose POST only reads, opts in for every request:

```python
client = HttpClient(base_url="https://query.internal", retry_non_idempotent=True)
```

scalo-rs makes the same split with `retry_non_idempotent` in its HTTP client config.

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

scalo-py adds no retry hooks of its own. stamina enables its defaults whatever the app does: a `stamina.retry_scheduled` warning on the `stamina` logger (through structlog instead when structlog is installed), and a Prometheus retry counter when `prometheus_client` is importable. Call `stamina.instrumentation.set_on_retry_hooks` to change them.

The error those hooks record is named by class, plus the status for an `HTTPStatusError`: `HTTPStatusError(status=503)` or `ConnectError`. An httpx error's own repr carries the request URL, which can hold user ids, so it never reaches them. The Prometheus counter's `error_type` label for these retries is `scalo.http.client._RetriedHTTPError`. The caller still receives the original httpx exception.

For request-level metrics (latency histograms, status-code counters)
wire the HTTP middleware from
[`core-pillars/metrics.md`](../core-pillars/metrics.md).

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
- `httpx.HTTPStatusError` — 5xx after `attempts` retries, a 5xx to a POST or PATCH that was not opted in, or any 4xx
  immediately
- `httpx.TimeoutException` — exceeded `timeout` per attempt
- `httpx.LocalProtocolError`, `httpx.UnsupportedProtocol` -- a request httpx refused to send, immediately

Wrap with `try/except` at the call site; the clients never swallow
exceptions.

---

## When to reach for something else

- **Circuit breaker around downstream**: compose with
  [`resilience.md`](resilience.md)'s `CircuitBreaker`. The HTTP client
  itself is retry-only; circuit breaking is a separate concern.
- **Streaming responses**: drop down to raw `httpx` —
  `HttpClient._client` is the underlying instance if you really need it,
  but prefer building a sibling helper that exposes the bits you need.
- **HTTP/2 server push, WebSockets**: out of scope. Use `httpx` or
  `websockets` directly.

---

## Related

- [../integration.md](../integration.md)
- [resilience.md](resilience.md)
- [concurrency.md](concurrency.md)
- [../core-pillars/metrics.md](../core-pillars/metrics.md)
- [../core-pillars/logging.md](../core-pillars/logging.md)
- [../extras-flags.md](../extras-flags.md)
