# Tracing

OTLP span export, composed in at `logger.setup()`. An app that calls it and nothing else gets distributed tracing, once the OTel SDK is installed (the `metrics` or `opentelemetry` extra). Without it `setup()` skips span export and logs that at DEBUG.

```python
from scalo.logger import setup

setup(service_name="my-service")   # spans now export
```

`ServiceApp` does this for you on `run`, passing its `name` as the service name.

## On by default, and the settings

Span export is on and pointed at a local collector, as metric push is and as scalo-rs does. Opting out is a config line:

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

`setup()` reads `otel_tracing` from the module-level `settings`, so a file `ServiceApp` adds with `--config` does not reach it, and the env vars always do. Env vars outrank config, per the OTel spec. The per-signal
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL`
outrank the generic pair, and a per-signal endpoint is used as given. With no
endpoint set anywhere, the default port follows the resolved protocol (4317 for
gRPC, 4318 for http).

`service_name` has no default on purpose. A package-name default would
report every service in the fleet as "scalo".

On the `http` protocol the signal path (`/v1/traces`) is appended to a
generic or configured endpoint for you, for the same reason as metrics.

The sampler is parent-based over a ratio well under 1.0. A request sampled upstream is always kept, so distributed traces stay whole, and the ratio governs the traces that START here and no others. A busy service creates spans at request rate and exporting all of them costs more than the traces are worth.

Turn it up for one service without a config change:

```bash
OTEL_TRACES_SAMPLER_ARG=1.0
```

## Bounded, so a missing collector costs telemetry and nothing else

- The queue is bounded. Once `batch_max_queue_size` fills, further spans are dropped rather than buffered, so an unreachable collector costs spans instead of growing memory without bound.
- Each export has a deadline. It goes on the exporter, not the batch processor -- `BatchSpanProcessor` accepts an `export_timeout_millis` and never uses it.
- Failures back off, through the same gate as the metric exporter: doubling to a 15-minute ceiling with jitter, one warning per outage, reset on success. See [metrics.md](metrics.md#backend-selection).
- Spans still buffered at exit are flushed, bounded at 2 seconds for the flush and the provider shutdown together. scalo registers an `atexit` hook in place of the SDK's, which would wait 30 seconds. The SDK bounds neither step -- `BatchSpanProcessor.force_flush()` ignores its timeout and `TracerProvider.shutdown()` takes none -- so both run on a daemon thread that exit stops waiting for at the bound, and spans still queued then are dropped. Call `scalo.otel_tracing.shutdown()` to flush earlier: it is the same bounded path, and a second call does nothing.
- Startup never fails on telemetry. A collector that is missing or misconfigured degrades tracing and the service still starts.

## Beside FastAPI and scalo-rs

fastapi 0.142+ reads `OTEL_EXPORTER_OTLP_ENDPOINT` as the app starts and adds span, metric and log exporters of its making to the providers scalo installed. It builds http/protobuf exporters and no others, and with `OTEL_EXPORTER_OTLP_PROTOCOL` unset it assumes http/protobuf whatever the port. Pointed at scalo's default gRPC collector on 4317, each of its span exports ends in "Failed to export spans batch due to timeout, max retries or shutdown", logged beside scalo's gRPC exporter.

Turn FastAPI's environment setup off. Its request spans still record, into scalo's provider:

```python
app = FastAPI(telemetry={"auto_configure": False})
```

Against scalo-rs: scalo-rs filters its export path (tonic, hyper, h2) out of the OTel
layer, because those crates emit `tracing` spans and feeding them to the
exporter makes every export generate the spans for the next one. There
is no equivalent filter here and none is needed: the Python SDK attaches
`_SUPPRESS_INSTRUMENTATION_KEY` around every export, so instrumentation
on the transport cannot re-enter.
