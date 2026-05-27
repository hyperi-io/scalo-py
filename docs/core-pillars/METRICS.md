# Metrics

Backend-agnostic metric API with OpenTelemetry as the default and
Prometheus as the fallback. Call `create_metrics(app_name)`, register
counters/gauges/histograms, and the manager handles exporter lifecycle
(OTLP push + Prometheus scrape simultaneously), cardinality capping,
and the standard DFE metric catalogue. The same code path serves
`/metrics` for scrape and pushes to an OTel collector at the same
time.

```python
from hyperi_pylib.metrics import create_metrics

m = create_metrics("my_service")
requests = m.counter("requests_total", "Total requests", ["method", "status"])
requests.labels(method="POST", status="200").inc()
```

---

## Backend selection

Backend resolves in this priority: explicit `backend=` arg, then
`HYPERI_METRICS_BACKEND` env var, then `settings.metrics.backend`,
then `"opentelemetry"`. If OTel SDK imports fail (extras not
installed), the manager logs a warning and falls back to the
Prometheus backend so metrics keep working.

| Backend | When chosen | Default extras |
|---------|-------------|----------------|
| `opentelemetry` | Default, with `[opentelemetry]` extra installed | Prometheus scrape on; OTLP push opt-in |
| `prometheus` | Explicit, or OTel SDK missing | Prometheus scrape only |

OTLP push is silent by default -- set `endpoint:` in config or
`OTEL_EXPORTER_OTLP_ENDPOINT` to enable it. Previously the default
``http://localhost:4317`` caused tests and local dev to spam
"Transient error" logs against a collector that wasn't running.
Prometheus scrape stays on by default; disable with
`prometheus_scrape: false`.

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

## DFE groups

Composable metric structs that mirror rustlib's `dfe_groups`. Wire
the groups your app needs; each registers a fixed set of metrics
with the standard names and labels HyperI services emit.

| Group | Registers | For |
|-------|-----------|-----|
| `AppMetrics` | `{ns}_info`, `start_time_seconds`, `records_{received,processed,error}_total`, `bytes_{received,written}_total`, `memory_{used,limit}_bytes`, `config_reloads_total` | Mandatory for every DFE app |
| `ConsumerMetrics` | `consumer_lag`, `consumer_partitions_assigned`, `consumer_rebalance_total`, `consumer_poll_duration_seconds`, `offsets_committed_total` | Kafka consumer apps |
| `BufferMetrics` | `buffer_bytes`, `buffer_records`, `buffer_flush_total`, `buffer_flush_duration_seconds`, `buffer_flush_trigger_total` | Receiver, loader, archiver |
| `SinkMetrics` | `sink_duration_seconds`, `sink_errors_total`, `bytes_sent_total`, `concurrent_inserts` | Apps writing to downstream |
| `BackpressureMetrics` | `backpressure_events_total`, `backpressure_duration_seconds_total` | Pipelines that pause |
| `CircuitBreakerMetrics` | `circuit_breaker_state` (gauge: 0=closed, 1=open, 2=half_open), `circuit_breaker_transitions_total` | Apps with circuit-protected downstreams |

```python
from hyperi_pylib.metrics import create_metrics
from hyperi_pylib.metrics.dfe_groups import (
    AppMetrics, ConsumerMetrics, BufferMetrics, SinkMetrics,
)

m = create_metrics("dfe_loader")
app = AppMetrics(m, version="1.0.0", commit="abc123")
consumer = ConsumerMetrics(m)
buffer = BufferMetrics(m)
sink = SinkMetrics(m)

app.record_received(100)
consumer.set_lag(topic="events", partition=0, lag=42)
buffer.record_flush(duration_seconds=0.01, trigger="size")
sink.record_duration(backend="clickhouse", duration_seconds=0.05)
```

Every group prefixes its metrics with the manager's `app_name`, so
`dfe_loader` and `dfe_archiver` never collide on the scrape.

---

## Cardinality cap

`CardinalityTracker` tracks unique label combinations per metric and
logs a single warning when the count exceeds the cap (default 50).
This prevents the classic Prometheus blow-up where a user ID or
request path becomes a label and the time-series count explodes.

```python
from hyperi_pylib.metrics import CardinalityTracker

tracker = CardinalityTracker(max_cardinality=50)
tracker.track("requests_total", {"method": "GET", "status": "200"})
tracker.track("requests_total", {"method": "POST", "status": "201"})
tracker.get_cardinality("requests_total")    # 2
```

The cap is enforced at observation time -- the metric still records;
the warning surfaces the issue so you can drop the offending label.
Reset via `tracker.reset()` (test fixtures only; never in production).

---

## OpenTelemetry config

```yaml
metrics:
  backend: opentelemetry
  opentelemetry:
    endpoint: http://otel-collector:4317   # or OTEL_EXPORTER_OTLP_ENDPOINT
    protocol: grpc                          # grpc | http
    prometheus_scrape: true                 # also expose /metrics (default)
```

Standard OTel env vars (`OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_RESOURCE_ATTRIBUTES`) are honoured.
At shutdown, the backend registers an atexit hook that runs before
the OTel SDK's own hook (LIFO order) to flush pending metrics; see
[SHUTDOWN.md](SHUTDOWN.md#otel-flush).

---

## HTTP exposition

```python
from fastapi import FastAPI, Response
from hyperi_pylib.metrics import create_metrics

app = FastAPI()
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

---

## Process and container collectors

The Prometheus backend automatically registers:

- `process_cpu_seconds_total`
- `process_resident_memory_bytes`
- `process_open_fds`, `process_max_fds`
- `process_virtual_memory_bytes`
- `process_start_time_seconds`

In containers, it also registers `container_memory_usage_bytes`,
`container_memory_limit_bytes`, `container_cpu_usage_seconds_total`,
`container_cpu_quota`, `container_cpu_period` -- read from the
cgroup files the runtime detector walks. OTel backend leaves
process/container metrics to the OTel SDK's resource attributes.

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
- [EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md) -- `[metrics]` vs `[opentelemetry]`
