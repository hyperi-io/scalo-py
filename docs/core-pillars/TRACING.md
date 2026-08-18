# Tracing

OTLP span export, composed in at `logger.setup()`. An app that calls it
and nothing else gets distributed tracing.

```python
from scalo.logger import setup

setup(service_name="my-service")   # spans now export
```

`ServiceApp` does this for you on `run`, passing its own `name` as the
service name.

---

## On by default

Span export is on and pointed at a local collector, the same posture as
metrics and the same as scalo-rs. Opting out is a config line, not a
feature you had to know about:

```yaml
otel_tracing:
  enabled: false        # master switch
  endpoint: ""          # or blank the endpoint
```

A blank `OTEL_EXPORTER_OTLP_ENDPOINT` does the same, for an operator who
cannot reach the config file.

Two paths deliberately do NOT dial a collector: the one-shot
subcommands (`config-check`, `version`, `generate-artefacts`), and
importing `scalo.logger` under `AUTO_LOGGER_CONFIG`. Importing a library
must not start an exporter thread.

---

## Configuration

```yaml
otel_tracing:
  enabled: true
  endpoint: http://localhost:4317      # OTEL_EXPORTER_OTLP_ENDPOINT
  protocol: grpc                        # grpc | http, OTEL_EXPORTER_OTLP_PROTOCOL
  service_name: ""                      # OTEL_SERVICE_NAME
  sample_ratio: 0.05                    # OTEL_TRACES_SAMPLER_ARG
  batch_scheduled_delay_millis: 5000
  batch_max_queue_size: 2048
  batch_max_export_batch_size: 512
  export_timeout_millis: 10000
```

Env vars outrank config, per the OTel spec.

`service_name` has no default on purpose. A package-name default would
report every service in the fleet as "scalo".

On the `http` protocol the signal path (`/v1/traces`) is appended for
you, for the same reason as metrics.

---

## Sampling

The sampler is parent-based over a ratio well under 1.0. A request
already sampled upstream is always kept, so distributed traces stay
whole; the ratio only governs traces that START here. A busy service
creates spans at request rate and exporting all of them costs more than
the traces are worth.

Turn it up for one service without a config change:

```bash
OTEL_TRACES_SAMPLER_ARG=1.0
```

---

## Bounded, so a missing collector costs telemetry and nothing else

- **The queue is bounded.** Once `batch_max_queue_size` fills, new spans
  are dropped rather than buffered, so an unreachable collector costs
  spans instead of growing memory without bound.
- **Each export has a deadline.** It goes on the exporter, not the batch
  processor -- `BatchSpanProcessor` accepts an `export_timeout_millis`
  and never uses it.
- **Failures back off.** Same gate as the metric exporter: doubling to a
  15-minute ceiling with jitter, one warning per outage, reset on
  success. See [METRICS.md](METRICS.md#when-the-collector-is-not-there).
- **The flush on exit is bounded at 2 seconds**, well inside a
  Kubernetes termination grace period. The bound is applied to the
  processor, because `TracerProvider.shutdown()` takes no timeout and
  would let the SDK's 30-second default stand, and scalo's exporter
  wrapper declares `timeout_millis` so the processor forwards what is
  left of that budget to the exporter as well. An exporter whose
  signature is copied from the `SpanExporter` base gets called bare and
  silently drops the bound.
- **Startup never fails on telemetry.** A collector that is missing or
  misconfigured degrades tracing and the service still starts.

---

## Parity note

scalo-rs filters its own export path (tonic, hyper, h2) out of the OTel
layer, because those crates emit `tracing` spans and feeding them to the
exporter makes every export generate the spans for the next one. There
is no equivalent filter here and none is needed: the Python SDK attaches
`_SUPPRESS_INSTRUMENTATION_KEY` around every export, so instrumentation
on the transport cannot re-enter.

---

## Related

- [METRICS.md](METRICS.md) -- the metric half of the same posture
- [LOGGING.md](LOGGING.md) -- where span export is composed in
- [SHUTDOWN.md](SHUTDOWN.md) -- flush on exit
