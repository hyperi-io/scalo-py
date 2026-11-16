# KEDA autoscaling

Two models. `KedaConfig` is the runtime side -- include it in your
app's `Config` so KEDA thresholds participate in the Dynaconf cascade
and are env-var overridable. `KedaContract` is the deploy side --
attach it to `DeploymentContract.keda` and the
[scalo-service](https://github.com/hyperi-io/scalo-rs/blob/main/charts/scalo-service/README.md)
chart renders a `ScaledObject` from it.

```python
from scalo.deployment import KedaConfig, KedaContract
```

Both subclass `BaseModel` with `extra="forbid"` and have the same numeric bounds, so a nonsense value fails at construction, not at deploy.

## `KedaConfig` -- runtime

| Field | Default | Constraint |
|---|---|---|
| `enabled` | `True` | -- |
| `min_replicas` | `1` | `>= 0` (0 enables scale-to-zero) |
| `max_replicas` | `10` | `>= 1` |
| `polling_interval` | `15` (seconds) | `>= 1` |
| `cooldown_period` | `300` (seconds) | `>= 0` |
| `kafka_lag_threshold` | `1000` | `>= 0` (KEDA's `lagThreshold`, a target for the group's total lag summed over partitions) |
| `activation_lag_threshold` | `0` | `>= 0` (lag to wake from zero replicas) |
| `cpu_enabled` | `True` | -- |
| `cpu_threshold` | `80` (percent) | `1..100` |

Under the env prefix `APP`, `APP_KEDA__KAFKA_LAG_THRESHOLD=5000` sets `keda.kafka_lag_threshold`: one `_` after the prefix, `__` between levels.

## `KedaContract` -- deploy

The same fields, plus `kafka_trigger`. Built from `KedaConfig` via:

```python
keda_contract = KedaContract.from_config(my_config.keda)
```

`from_config` copies every field verbatim, `enabled` included, and takes the default `kafka_trigger`.

`enabled=False` and `keda=None` both render no ScaledObject, so off has one meaning. A contract with no `enabled` key loads with it on.

With `enabled` true, `DeploymentContract` rejects KEDA when the Kafka lag trigger and the CPU trigger are both off, because there is nothing to scale on. It rejects a CPU-only KEDA with `min_replicas` of 0, because KEDA's CPU scaler cannot wake a workload from zero.

`kafka_trigger` (`KafkaLagTrigger`) says where the Kafka lag trigger reads its connection details in the chart's values. Each path is dotted and `.Values`-relative:

| Field | Default |
|---|---|
| `enabled` | `True` |
| `brokers_path` | `config.kafka.brokers` |
| `group_path` | `config.kafka.group_id` |
| `topics_path` | `config.kafka.topics` |

`KafkaLagTrigger.under("config.source")` reads the three under another section, and `KafkaLagTrigger.disabled()` says there is no Kafka lag trigger. Both serialise as scalo-rs's `KafkaLagTrigger` does. The scalo-service chart reads each path against the config the app ends up running -- the contract's `default_config`, then `config`, then `configOverrides` -- and fails to render when one has no value. Set it, or turn the trigger off for that deployment with `keda.kafka.enabled: false`.

## When the chart renders a ScaledObject

The scalo-service chart renders a ScaledObject called `<fullname>-scaler`
while KEDA is on: `DeploymentContract.keda` is set with `enabled=True`, unless `keda.enabled` in values says otherwise. A singleton never gets one, and `keda.enabled: true` on a singleton fails the render. The chart's `keda.*` values override the contract's bounds, thresholds and trigger switches per deployment.

With KEDA off, `autoscaling.enabled: true` renders a CPU
HorizontalPodAutoscaler instead, so clusters without the KEDA operator
still scale on CPU by setting `keda.enabled: false` and
`autoscaling.enabled: true`.

The Deployment sets `replicas: <replicaCount>` when neither KEDA nor the HPA is on, and not otherwise, because whichever is on owns the replica count and a GitOps sync must not revert a scale. A singleton is pinned at `replicas: 1`.

## The triggers it derives

| Trigger | Switched by | Threshold, then its values override |
|---|---|---|
| `cpu`, `metricType: Utilization` | `cpu_enabled`, then `keda.cpu.enabled` | `cpu_threshold` percent, then `keda.cpu.targetUtilization` |
| `kafka` | `kafka_trigger.enabled`, then `keda.kafka.enabled` | `kafka_lag_threshold` and `activation_lag_threshold`, then `keda.kafka.lagThreshold` and `keda.kafka.activationLagThreshold` |

In each pair the `keda.*` value wins. The Kafka trigger's brokers, consumer group and topic come from the `kafka_trigger` paths: a broker list is joined with commas, and the first topic is taken whether the topics are a list or a comma-separated string.

`keda.triggers` replaces both, and `keda.extraTriggers` is appended after
them. KEDA scales to the max of all triggers -- high lag OR high CPU
grows the pool, and both must subside to shrink.

The chart renders a TriggerAuthentication called `<fullname>-trigger-auth`
when `keda.triggerAuthentication.secretTargetRef` is set, and not otherwise, and the
Kafka trigger then references it. The trigger has no `sasl` or `tls`:
KEDA's Kafka scaler takes both as authentication parameters, so the
operator sets them in that `secretTargetRef` beside the credentials, to
match the listener. With neither set KEDA uses no SASL and no TLS.

The scalo-service README lists every `keda.*` value the chart reads.

`scalo.scaling.ScalingPressure` is a weighted 0-100 score of memory, queue depth, latency, error rate and one custom signal. `register_gauge` writes it as the `scaling_pressure` gauge, which a KEDA Prometheus trigger in `keda.extraTriggers` can target once Prometheus scrapes the service. See [../api/scaling.md](../api/scaling.md).
