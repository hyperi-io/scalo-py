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

Both subclass `BaseModel` with `extra="forbid"`; both share the same
numeric field validators -- nonsense values fail at construction, not
at deploy.

---

## `KedaConfig` -- runtime

| Field | Default | Constraint |
|---|---|---|
| `enabled` | `True` | -- |
| `min_replicas` | `1` | `>= 0` (0 enables scale-to-zero) |
| `max_replicas` | `10` | `>= 1` |
| `polling_interval` | `15` (seconds) | `>= 1` |
| `cooldown_period` | `300` (seconds) | `>= 0` |
| `kafka_lag_threshold` | `1000` | `>= 0` (per-partition lag to trigger scale-up) |
| `activation_lag_threshold` | `0` | `>= 0` (lag to wake from zero replicas) |
| `cpu_enabled` | `True` | -- |
| `cpu_threshold` | `80` (percent) | `1..100` |

Cascade env-var overrides follow the standard `__` nesting:
`APP__KEDA__KAFKA_LAG_THRESHOLD=5000`.

---

## `KedaContract` -- deploy

The same fields, plus `kafka_trigger`. Built from `KedaConfig` via:

```python
keda_contract = KedaContract.from_config(my_config.keda)
```

`from_config` copies every field verbatim, `enabled` included, and takes the default `kafka_trigger`.

`enabled=False` renders exactly what `keda=None` does -- no ScaledObject -- so off has one meaning. A contract written before `enabled` existed loads with it on.

With `enabled` true, `DeploymentContract` refuses KEDA when the Kafka lag trigger and the CPU trigger are both off, because there is nothing to scale on. It also refuses a CPU-only KEDA with `min_replicas` of 0, because KEDA's CPU scaler cannot wake a workload from zero.

`kafka_trigger` (`KafkaLagTrigger`) says where the Kafka lag trigger reads its connection details in the chart's values. Each path is dotted and `.Values`-relative:

| Field | Default |
|---|---|
| `enabled` | `True` |
| `brokers_path` | `config.kafka.brokers` |
| `group_path` | `config.kafka.group_id` |
| `topics_path` | `config.kafka.topics` |

`KafkaLagTrigger.under("config.source")` reads the three under another section, and `KafkaLagTrigger.disabled()` says there is no Kafka lag trigger. Both serialise as scalo-rs's `KafkaLagTrigger` does. The scalo-service chart reads each path against the config the app ends up running -- the contract's `default_config`, then `config`, then `configOverrides` -- and refuses to render when one has no value. Set it, or turn the trigger off for that deployment with `keda.kafka.enabled: false`.

---

## When the chart renders a ScaledObject

The scalo-service chart renders a ScaledObject named `<fullname>-scaler`
while KEDA is on: `DeploymentContract.keda` is set with `enabled=True`,
unless `keda.enabled` in values says otherwise. A singleton never gets
one. The chart's `keda.*` values override each contract field per
deployment.

With KEDA off, `autoscaling.enabled: true` renders a CPU
HorizontalPodAutoscaler instead, so clusters without the KEDA operator
still scale on CPU by setting `keda.enabled: false` and
`autoscaling.enabled: true`.

The Deployment sets `replicas: <replicaCount>` exactly when neither KEDA
nor the HPA is on, because whichever is on owns the replica count and a
GitOps sync must not revert a scale.

---

## The triggers it derives

1. **CPU** (unless `cpu_enabled` or `keda.cpu.enabled` turns it off) --
   utilisation target `cpu_threshold`, `metricType: Utilization`;
   `keda.cpu.targetUtilization` overrides the target.
2. **Kafka** (unless `kafka_trigger` or `keda.kafka.enabled` turns it
   off) -- `lagThreshold` per partition and `activationLagThreshold` for
   wake-from-zero, from the contract or `keda.kafka.*`. Brokers, consumer
   group and topic come from the `kafka_trigger` paths: a broker list is
   joined with commas, and the first topic is taken whether the topics are
   a list or a comma-separated string.

`keda.triggers` replaces both, and `keda.extraTriggers` is appended after
them. KEDA scales to the max of all triggers -- high lag OR high CPU
grows the pool, and both must subside to shrink.

The chart renders a TriggerAuthentication named `<fullname>-trigger-auth`
only when `keda.triggerAuthentication.secretTargetRef` is set, and the
Kafka trigger then references it. The trigger carries no `sasl` or `tls`:
KEDA's Kafka scaler takes both as authentication parameters, so the
operator sets them in that `secretTargetRef` beside the credentials, to
match the listener. With neither set KEDA uses no SASL and no TLS.

The scalo-service README lists every `keda.*` value the chart reads.

---

## Runtime signal feed

The runtime side of scaling is `scalo.scaling.ScalingPressure`
-- a composite consumer-lag + buffer-pressure + CPU pressure score the
service exports as a single gauge. KEDA's external/prometheus trigger
can scrape that gauge for finer-grained signals than raw consumer lag.
See [../api/scaling.md](../api/scaling.md).

---

## Related

- [contract.md](contract.md)
- [artefacts.md](artefacts.md)
- [../api/scaling.md](../api/scaling.md)
- [identity.md](identity.md)
- [test-support.md](test-support.md)
- [../integration.md](../integration.md)
