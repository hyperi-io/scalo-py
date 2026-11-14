# Scaling

`ScalingPressure` is a weighted composite 0-100 score that a KEDA scaler can target. It runs the same three gates, in the same order, as scalo-rs's `src/scaling/pressure.rs` and writes the same `scaling_pressure` gauge, but the component model and the default memory gate differ (see [Cross-language parity](#cross-language-parity)). Ships in the base package.

```python
from scalo.scaling import (
    ScalingPressure, ScalingPressureConfig, PressureSnapshot,
)
```

---

## Quick start

```python
from scalo.scaling import ScalingPressure

pressure = ScalingPressure()
pressure.set_memory(used_bytes=900_000_000, limit_bytes=1_000_000_000)
pressure.set_component("queue_depth", 0.7)
pressure.set_component("latency", 0.4)

score = pressure.calculate()   # 0-100, feed to KEDA external scaler
```

---

## Gate logic

Three gates evaluated in order:

1. Circuit open -> `0.0`. Scaling cannot help if a downstream is tripped, and adding pods trips more breakers.
2. Memory >= the gate threshold (`0.85` by default) -> `100.0`, to scale before an OOMKill.
3. Otherwise -> the weighted sum of the components x 100, clamped to `[0, 100]`.

```python
weighted_sum = (
    memory       * memory_weight       +
    queue_depth  * queue_depth_weight  +
    latency      * latency_weight      +
    error_rate   * error_rate_weight   +
    custom       * custom_weight
) * 100.0
```

---

## Default weights

| Component | Weight | What it measures |
|-----------|--------|------------------|
| `memory` | 0.25 | RSS / memory limit |
| `queue_depth` | 0.30 | Consumer lag, ingress buffer, backlog |
| `latency` | 0.25 | p95 / SLO ratio, or any latency-vs-target ratio |
| `error_rate` | 0.15 | Failed requests / total |
| `custom` | 0.05 | Whatever else matters for this service |

The weights must sum to 1.0, within 0.001, and each sit in `[0.0, 1.0]`. The memory gate threshold sits in `(0.0, 1.0]`. `ScalingPressureConfig` raises `ValueError` at construction otherwise. With `memory_gate_threshold = 0.85`, memory at 85% of its limit or above pegs the score at 100 regardless of the other components, so a KEDA scaler watching it scales out at once.

Override via `ScalingPressureConfig`:

```python
from scalo.scaling import ScalingPressureConfig

cfg = ScalingPressureConfig(
    memory_weight=0.15,
    queue_depth_weight=0.45,   # queue-heavy service
    latency_weight=0.20,
    error_rate_weight=0.15,
    custom_weight=0.05,
    memory_gate_threshold=0.90,
)
pressure = ScalingPressure(cfg)
```

---

## Updating components

```python
pressure.set_component("memory", 0.75)        # 75% memory utilisation
pressure.set_component("queue", 0.4)          # alias for "queue_depth"
pressure.set_component("queue_depth", 0.4)    # same thing
pressure.set_component("latency", 0.6)        # 60% of latency budget consumed
pressure.set_component("error", 0.02)         # alias for "error_rate"
pressure.set_component("error_rate", 0.02)    # same thing
pressure.set_component("anything-else", 0.5)  # -> custom slot
```

Saturation values are clamped to `[0.0, 1.0]`. Unknown component names land in the `custom` slot, for a one-off pressure signal such as open DB connections. Every unknown name writes the same slot, so only one custom signal is held at a time.

Convenience helper for memory:

```python
pressure.set_memory(used_bytes=psutil.Process().memory_info().rss,
                    limit_bytes=cgroup_memory_limit())
```

It calls `set_component("memory", used / limit)`, and sets memory to `0.0` when `limit_bytes <= 0` (no limit set). `cgroup_memory_limit()` above stands for your own reader of the cgroup limit.

---

## Circuit-open signal

```python
pressure.set_circuit_open(True)   # downstream tripped -- calculate() now returns 0.0
...
pressure.set_circuit_open(False)  # recovered -- back to weighted sum
```

Wire this into your `CircuitBreaker` state changes. The gate keeps KEDA from scaling out under a failure that adding pods can't fix.

---

## Reading the score

```python
score = pressure.calculate()       # float in [0.0, 100.0]
```

Call it from your metrics gauge update path. The lock is held only to read and recompute, so calling `calculate()` once per scrape interval is cheap.

For a frozen, consistent view of every component plus the overall
score:

```python
snap = pressure.snapshot()
# PressureSnapshot(
#   overall=50.5,
#   memory=0.60,
#   queue=0.80,
#   latency=0.40,
#   error=0.10,
#   circuit_open=False,
# )
```

`PressureSnapshot` is frozen, so a structured-log line or a test assertion gets one consistent read of the state. It carries no custom slot, though `overall` includes it.

---

## Exposing as a Prometheus gauge

```python
from scalo.metrics import create_metrics
from scalo.scaling import ScalingPressure

metrics = create_metrics("my_service")
pressure = ScalingPressure()
pressure.register_gauge(metrics)   # creates "scaling_pressure" gauge

# A background thread writes calculate() to the gauge every second, so the
# scrape and the OTLP push carry it with no traffic. calculate() also updates it.
pressure.set_component("queue_depth", 0.7)
score = pressure.calculate()

pressure.stop_gauge()              # at shutdown, if you want the thread ended first
```

`register_gauge(metrics, interval=1.0)` takes the seconds between writes,
the same cadence scalo-rs `ServiceRuntime` uses. The thread is a daemon, so
it never holds the process open.

The metric name is `scaling_pressure`, under the manager's metric prefix when one is set, with the description `"Composite scaling pressure score (0-100)"`. KEDA's Prometheus scaler points at it:

```yaml
triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus.monitoring:9090
      metricName: scaling_pressure
      threshold: "70"
      query: |
        avg(scaling_pressure{service="my-service"})
```

Above 70 (configurable per service), KEDA scales out.

---

## Concurrent updates

All mutating methods (`set_component`, `set_memory`, `set_circuit_open`) and read methods (`calculate`, `snapshot`) take one internal lock, so they are safe to call from any thread or async task without external synchronisation.

---

## Cross-language parity

Both libraries gate in the same order (circuit open, then memory, then the weighted sum) and write a `scaling_pressure` gauge once a second. The rest differs:

| | scalo-py | scalo-rs `scalo::scaling::ScalingPressure` |
|---|---|---|
| Components | five fixed slots: `memory`, `queue`, `latency`, `error`, `custom` | the app's own `ScalingComponent(name, weight, saturation)` list |
| `set_component` value | a saturation, clamped to `[0, 1]` | a raw value, scored as `min(value / saturation, 1)` |
| Default weights | 0.25 / 0.30 / 0.25 / 0.15 / 0.05 | none, each app sets its own |
| Default memory gate | `0.85` | `0.8` |
| Kill switch | none | `enabled: false` returns `0.0` |

So the same KEDA threshold means the same thing in both only when the two apps weight comparable signals the same way and set the same memory gate.

---

## Related

- [resilience.md](resilience.md)
- [../deployment/keda.md](../deployment/keda.md)
- [../core-pillars/metrics.md](../core-pillars/metrics.md)
- [../core-pillars/health.md](../core-pillars/health.md)
- [concurrency.md](concurrency.md)
- [../integration.md](../integration.md)
