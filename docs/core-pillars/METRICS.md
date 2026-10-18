# Metrics

Backend-agnostic metric API with OpenTelemetry as the default and
Prometheus as the fallback. Call `create_metrics(app_name)`, register
counters/gauges/histograms, and the manager handles exporter lifecycle
(OTLP push + Prometheus scrape simultaneously), cardinality capping,
and the standard metric groups (`scalo.metrics.groups`). The same code path serves
`/metrics` for scrape and pushes to an OTel collector at the same
time.

```python
from scalo.metrics import create_metrics

m = create_metrics("my_service")
requests = m.counter("requests_total", "Total requests", ["method", "status"])
requests.labels(method="POST", status="200").inc()
```

---

## Backend selection

Backend resolves in this priority: explicit `backend=` arg, then the
`METRICS_BACKEND` env var, then `settings.metrics.backend`, then
`"opentelemetry"`. If OTel SDK imports fail (extras not installed),
the manager logs a warning and falls back to the Prometheus backend so
metrics keep working.

The env var is subject to the env prefix like every other control var:
bare `METRICS_BACKEND` by default, or `<PREFIX>_METRICS_BACKEND` when
the app sets one. There is no `HYPERI_`-prefixed form -- scalo
hard-codes no brand.

`ServiceApp` honours the same cascade and the same default.

| Backend | When chosen | What it does |
|---------|-------------|--------------|
| `opentelemetry` | Default, on the `[metrics]` extra | Prometheus scrape AND OTLP push |
| `prometheus` | Explicit, or OTel SDK missing | Prometheus scrape only |

### OTLP push is on by default

Enabling metrics composes the exporters in: Prometheus scrape, OTLP
metric push and OTLP span export, pointed at a local collector. A
service is a good citizen out of the box rather than only serving
`/metrics` for something else to come and scrape, and matches scalo-rs.

The OTel backend is DUAL -- it pushes and keeps serving `/metrics` --
so a Prometheus-estate deployer loses nothing.

Two ways off, and neither costs the scrape endpoint:

```yaml
metrics:
  opentelemetry:
    enabled: false          # master switch
    endpoint: ""            # or blank the endpoint
```

A blank `OTEL_EXPORTER_OTLP_ENDPOINT` does the same thing, for an
operator who cannot reach the config file. The env var outranks config,
per the OTel spec.

Disable the scrape endpoint separately with `prometheus_scrape: false`.

### When the collector is not there

Laptops and CI runners have no collector, and neither does a service
during a collector outage. The exporters are wrapped in a backoff gate
(`scalo.otel_backoff`): the first failure logs one warning and starts a
wait that doubles to a 15-minute ceiling with 20% jitter, so a fleet
that lost its collector together does not come back in lockstep. One
success resets it and logs what the outage cost. Suppressed exports
report success to the SDK -- OTLP metrics are cumulative, so the next
export that lands carries the full value.

The flush on exit is bounded at 2 seconds, well inside a Kubernetes
termination grace period, so an unreachable collector cannot hold a pod
open until SIGKILL.

---

## Metric types

```python
# Counter -- monotonically increasing.
errors = m.counter("errors_total", "Total errors", ["component"])
errors.labels(component="parser").inc()
errors.labels(component="sink").inc(5)

# Gauge -- up and down.
queue = m.gauge("queue_size", "Items in queue")
queue.set(42); queue.inc(); queue.dec(5)

# Histogram -- distribution; bucket boundaries optional.
latency = m.histogram(
    "request_duration_seconds",
    "HTTP request latency",
    ["method"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)
latency.labels(method="GET").observe(0.123)
```

---

## Built-in metric groups

Composable metric structs that mirror scalo-rs's `groups`. Wire
the groups your app needs; each registers a fixed set of metrics
with standard names and labels, the same in both languages.

| Group | Registers | For |
|-------|-----------|-----|
| `AppMetrics` | `{ns}_info`, `start_time_seconds`, `records_{received,processed,error}_total`, `bytes_{received,written}_total`, `memory_{used,limit}_bytes`, `config_reloads_total` | Every app |
| `ConsumerMetrics` | `consumer_lag`, `consumer_partitions_assigned`, `consumer_rebalance_total`, `consumer_poll_duration_seconds`, `offsets_committed_total` | Kafka consumer apps |
| `BufferMetrics` | `buffer_bytes`, `buffer_records`, `buffer_flush_total`, `buffer_flush_duration_seconds`, `buffer_flush_trigger_total` | Apps that batch before a sink |
| `SinkMetrics` | `sink_duration_seconds`, `sink_errors_total`, `bytes_sent_total`, `concurrent_inserts` | Apps writing to downstream |
| `BackpressureMetrics` | `backpressure_events_total`, `backpressure_duration_seconds_total` | Pipelines that pause |
| `CircuitBreakerMetrics` | `circuit_breaker_state` (gauge: 0=closed, 1=open, 2=half_open), `circuit_breaker_transitions_total` | Apps with circuit-protected downstreams |

```python
from scalo.metrics import create_metrics
from scalo.metrics.groups import (
    AppMetrics, ConsumerMetrics, BufferMetrics, SinkMetrics,
)

m = create_metrics("ingest-loader")
app = AppMetrics(m, version="1.0.0", commit="abc123")
consumer = ConsumerMetrics(m)
buffer = BufferMetrics(m)
sink = SinkMetrics(m)

app.record_received(100)
consumer.set_lag(topic="events", partition=0, lag=42)
buffer.record_flush(duration_seconds=0.01, trigger="size")
sink.record_duration(backend="clickhouse", duration_seconds=0.05)
```

Every group prefixes its metrics with the manager's **metric prefix**
-- not its `app_name`. That prefix resolves from `set_metric_prefix()`
/ `METRIC_PREFIX` / `metrics.namespace` and is **bare by default**, so
out of the box these names are unprefixed and two apps DO collide on
name alone. That is deliberate: differentiation is meant to come from
scrape labels (`job`, `instance`, `pod`, `namespace`), which is also
how scalo-rs behaves.

If you want the names themselves namespaced, set it explicitly:

```python
create_metrics("ingest-loader", metric_prefix="ingest_loader")
```

`app_name` only names the backend/meter and supplies the `app` label
on the `AppMetrics` info metric.

---

## Cardinality cap

`CardinalityTracker` tracks unique label combinations per metric and
logs a single warning when the count exceeds the cap (default 50).
This guards against the classic Prometheus blow-up where a user ID or
request path becomes a label and the time-series count explodes.

**It is opt-in, and you must call `track()` yourself.** Nothing in
`MetricsManager` or either backend calls it, so creating metrics the
normal way gets you no cardinality warnings. Wire it into whatever
code chooses the label values.

```python
from scalo.metrics import CardinalityTracker

tracker = CardinalityTracker(max_cardinality=50)
tracker.track("requests_total", {"method": "GET", "status": "200"})
tracker.track("requests_total", {"method": "POST", "status": "201"})
tracker.get_cardinality("requests_total")    # 2
```

The cap does not block anything -- the metric still records; the
warning surfaces the issue so you can drop the offending label.
Reset via `tracker.reset()` (test fixtures only; never in production).

---

## OpenTelemetry config

```yaml
metrics:
  backend: opentelemetry
  opentelemetry:
    enabled: true                           # master switch for OTLP push
    endpoint: http://otel-collector:4317    # or OTEL_EXPORTER_OTLP_ENDPOINT
    protocol: grpc                          # grpc | http
    export_interval_millis: 60000
    export_timeout_millis: 10000            # per-attempt deadline
    headers: {}                             # commonly a backend API key
    resource_attributes: {}                 # applied last, so they win
    prometheus_scrape: true                 # also expose /metrics (default)
```

Standard OTel env vars outrank config: `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_SERVICE_NAME`,
`OTEL_METRIC_EXPORT_INTERVAL`, `OTEL_METRIC_EXPORT_TIMEOUT`.

The resource carries `service.name`, `service.version`,
`service.instance.id` and `deployment.environment.name` -- the stable
semconv key, sourced from scalo's own env detection
(`APP_ENV` / `ENVIRONMENT` / `ENV`), so telemetry is tagged with the
tier without per-app wiring. Anything in `resource_attributes` is
applied last and wins.

`export_timeout_millis` is the per-attempt deadline. Without it an
endpoint that accepts the connection and never answers holds the
exporter open past the next interval and the attempts overlap.

On the `http` protocol the OTLP signal path (`/v1/metrics`) is appended
to the endpoint for you. The SDK only does that for an endpoint it reads
from the environment itself; one passed in is used verbatim, so a base
URL would POST to the collector's root.

At shutdown, the backend registers an atexit hook that runs before
the OTel SDK's own hook (LIFO order) to flush pending metrics; see
[SHUTDOWN.md](SHUTDOWN.md#otel-flush).

---

## HTTP exposition

```python
from fastapi import FastAPI, Response
from scalo.metrics import create_metrics

# fastapi 0.142+ otherwise reads OTEL_EXPORTER_OTLP_ENDPOINT and adds http/protobuf exporters, which fail against a gRPC collector.
app = FastAPI(telemetry={"auto_configure": False})
m = create_metrics("my_service")

@app.get("/metrics")
def metrics_endpoint() -> Response:
    return Response(content=m.metrics, media_type=m.content_type)
```

`m.metrics` returns bytes in the backend's native format; `m.metrics_text`
is the same as a decoded string. `m.content_type` matches what
Prometheus expects.

In OTLP-only mode (`prometheus_scrape: false`, no Prometheus reader),
the endpoint returns an informational message -- scraping is
unnecessary because metrics push to the collector.

### Request metrics

`HttpServerMetricsMiddleware` records one histogram,
`http_server_request_duration_seconds` (`http.server.request.duration`
over OTLP), labelled by method, route template and status code.

The route label is the full template from the app root, with every router prefix and mount path above the route: `/api/v1/accounts/{username}`, never `/api/v1/accounts/alice`. A mount keeps its own template, so `/orgs/{org}` is one label for every org. A request no route matched is labelled `__unmatched__`.

A request whose template cannot be named without a request value is labelled `__unresolved__`, so a scan of values never mints a series per value. That covers a parameter in an included router's prefix, a mount inside an included router, a Host route with a parameter, and a typed value written in a non-canonical form (`/items/007` on `{x:int}`, `1.50` on a float, an uppercase UUID).

fastapi 0.142+ records the same instrument itself, so turn its copy off
or every request is counted twice:

```python
from scalo.metrics.http_server import HttpServerMetricsMiddleware

app = FastAPI(telemetry={"auto_configure": False, "metrics": False})
app.add_middleware(HttpServerMetricsMiddleware, metrics=m)
```

---

## Process and container collectors

The two backends register different sets.

**Prometheus backend.** Its own psutil collector, on the backend's private registry:

- `process_info` (app name, pid, Python version, platform, container detection)
- `process_cpu_percent`, `process_cpu_seconds_total`
- `process_memory_rss_bytes`, `process_memory_vms_bytes`, `process_memory_percent`
- `process_threads_total`, `process_fds_open`, `process_uptime_seconds`

In a container it adds `container_memory_limit_bytes`, `container_memory_usage_bytes`,
`container_memory_available_bytes`, `container_memory_pressure_percent`,
`container_oom_kills_total`, `container_cpu_quota` and
`container_cpu_throttled_seconds_total`, read from the cgroup files the runtime detector walks.

**OpenTelemetry backend.** `ResourceMetrics` (`scalo.metrics.groups`), which `ServiceApp`
registers automatically. It reads each value fresh at every collection and pushes it over OTLP
as a gauge, under the bare names scalo-rs uses:

- `process_cpu_seconds_total`, `process_resident_memory_bytes`, `process_virtual_memory_bytes`
- `process_open_fds` (Linux only), `process_start_time_seconds`
- in a cgroup: `container_memory_usage_bytes`, `container_memory_limit_bytes` (unlimited is
  2^64 - 1, as scalo-rs reports it), `container_cpu_limit_cores`

Registering them unregisters prometheus_client's default process collector, so `/metrics`
on this backend serves each `process_*` name once. `process_cpu_seconds_total` is a gauge
there, not prometheus_client's counter.

---

## Naming

Stick to Prometheus conventions; the OTel backend rewrites to OTel
semantic conventions on export.

| Type | Convention |
|------|------------|
| Counter | `..._total` suffix |
| Duration | `..._seconds` suffix |
| Size | `..._bytes` suffix |
| Style | `snake_case`, lowercase |

---

## Related

- [CONFIG.md](CONFIG.md) -- `metrics:` settings live in the cascade
- [LOGGING.md](LOGGING.md) -- cardinality warnings log here
- [HEALTH.md](HEALTH.md) -- probes are not exported as metrics
- [SHUTDOWN.md](SHUTDOWN.md) -- OTel atexit ordering matters
- [api/RESILIENCE.md](../api/RESILIENCE.md) -- pairs with `CircuitBreakerMetrics`
- [transport/KAFKA.md](../transport/KAFKA.md) -- pairs with `ConsumerMetrics`
- [EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md) -- what `[metrics]` installs
