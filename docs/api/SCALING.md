# Scaling

`ScalingPressure` — a weighted composite 0-100 score that KEDA's
external scaler can target. Matches `hyperi-rustlib`'s
`src/scaling/pressure.rs` byte for byte, so Python and Rust services in
the same fleet produce comparable scores. Ships in the base package.

```python
from hyperi_pylib.scaling import (
    ScalingPressure, ScalingPressureConfig, PressureSnapshot,
)
```

---

## Quick start

```python
from hyperi_pylib.scaling import ScalingPressure

pressure = ScalingPressure()
pressure.set_memory(used_bytes=900_000_000, limit_bytes=1_000_000_000)
pressure.set_component("queue_depth", 0.7)
pressure.set_component("latency", 0.4)

score = pressure.calculate()   # 0-100, feed to KEDA external scaler
```

---

## Gate logic

Three gates evaluated in order:

1. **Circuit open** → `0.0`. Scaling cannot help if a downstream is
   tripped — adding pods just trips more breakers.
2. **Memory ≥ gate threshold** (`0.85` by default) → `100.0`. Scale
   immediately before OOMKill.
3. **Otherwise** → weighted sum of components × 100.

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

Weights sum to 1.0. The memory gate threshold (`memory_gate_threshold =
0.85`) means anything above 85% memory utilisation pegs the score at
100 regardless of the other components — a KEDA scaler watching this
metric scales out instantly.

Override via `ScalingPressureConfig`:

```python
from hyperi_pylib.scaling import ScalingPressureConfig

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
pressure.set_component("anything-else", 0.5)  # → custom slot
```

Saturation values are clamped to `[0.0, 1.0]`. Unknown component names
land in the `custom` slot — useful for one-off pressure signals (open
DB connections, in-flight ML predictions). Multiple calls to
`set_component("custom-x", ...)` overwrite each other; only one custom
signal is held at a time.

Convenience helper for memory:

```python
pressure.set_memory(used_bytes=psutil.Process().memory_info().rss,
                    limit_bytes=cgroup_memory_limit())
```

Calls `set_component("memory", used / limit)` with the right
clamping. Returns 0.0 if `limit_bytes <= 0` (no limit set).

---

## Circuit-open signal

```python
pressure.set_circuit_open(True)   # downstream tripped — calculate() now returns 0.0
...
pressure.set_circuit_open(False)  # recovered — back to weighted sum
```

Wire this into your `CircuitBreaker` state changes. The whole point of
the gate is to keep KEDA from scaling out under a failure mode that
adding pods can't fix.

---

## Reading the score

```python
score = pressure.calculate()       # float in [0.0, 100.0]
```

Call from your metrics gauge update path. The lock is held only long
enough to read and recompute — calling `calculate()` once per scrape
interval is cheap.

For a frozen, consistent view of every component plus the overall
score:

```python
snap = pressure.snapshot()
# PressureSnapshot(
#   overall=72.5,
#   memory=0.60,
#   queue=0.80,
#   latency=0.40,
#   error=0.10,
#   circuit_open=False,
# )
```

`PressureSnapshot` is frozen — useful for structured-log lines and unit
test assertions where you want one atomic read of state.

---

## Exposing as a Prometheus gauge

```python
from hyperi_pylib.metrics import create_metrics
from hyperi_pylib.scaling import ScalingPressure

metrics = create_metrics("my_service")
pressure = ScalingPressure()
pressure.register_gauge(metrics)   # creates "scaling_pressure" gauge

# calculate() now also updates the gauge automatically
pressure.set_component("queue_depth", 0.7)
score = pressure.calculate()
```

The metric name is `scaling_pressure` with the description
`"Composite scaling pressure score (0-100)"`. KEDA's Prometheus scaler
points at this:

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

All mutating methods (`set_component`, `set_memory`,
`set_circuit_open`) and read methods (`calculate`, `snapshot`) take
`self._lock`. Safe to call from any thread or async task without
external synchronisation.

---

## Cross-language parity

Same struct in Rust (`hyperi_rustlib::scaling::ScalingPressure`), same
default weights, same gate thresholds, same calculation. A KEDA scaler
that targets `scaling_pressure >= 70` works identically against a
Python service and a Rust service in the same deployment.

---

## Related

- [RESILIENCE.md](RESILIENCE.md)
- [../deployment/KEDA.md](../deployment/KEDA.md)
- [../core-pillars/METRICS.md](../core-pillars/METRICS.md)
- [../core-pillars/HEALTH.md](../core-pillars/HEALTH.md)
- [CONCURRENCY.md](CONCURRENCY.md)
- [../INTEGRATION.md](../INTEGRATION.md)
