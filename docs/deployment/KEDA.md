# KEDA autoscaling

Two models. `KedaConfig` is the runtime side -- include it in your
app's `Config` so KEDA thresholds participate in the Dynaconf cascade
and are env-var overridable. `KedaContract` is the deploy side --
attach it to `DeploymentContract.keda` to switch Helm output from a
plain HPA to a `ScaledObject`.

```python
from hyperi_pylib.deployment import KedaConfig, KedaContract
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
`DFE_LOADER__KEDA__KAFKA_LAG_THRESHOLD=5000`.

---

## `KedaContract` -- deploy

Same fields minus `enabled` (the contract is only attached when KEDA
is on). Built from `KedaConfig` via:

```python
keda_contract = KedaContract.from_config(my_config.keda)
```

`from_config` strips `enabled` and copies the rest verbatim.

---

## Generated artefacts

When `DeploymentContract.keda is not None`, `generate_chart` writes
two extra templates:

- `templates/keda-scaledobject.yaml` -- the `keda.sh/v1alpha1
  ScaledObject` with Kafka + (optional) CPU triggers.
- `templates/keda-triggerauth.yaml` -- a `TriggerAuthentication`
  bound to the `kafka` `SecretGroupContract`'s K8s Secret. Only
  emitted when there's a `kafka` group; otherwise the file contains
  a single comment line.

The `values.yaml` `keda:` block exposes:

- `keda.enabled`, `keda.minReplicaCount`, `keda.maxReplicaCount`,
  `keda.pollingInterval`, `keda.cooldownPeriod`
- `keda.kafka.lagThreshold` / `activationLagThreshold` /
  `topic` (override; defaults to first topic from `config.kafka.topics`)
  / `consumerGroup` (override; defaults to `config.kafka.group_id`)
- `keda.cpu.enabled` / `keda.cpu.threshold`

---

## Triggers

| Trigger | Wired by default | Notes |
|---|---|---|
| `kafka` | yes | Consumer-group lag. SASL SCRAM-SHA-512, TLS disabled (cluster-internal) |
| `cpu` | optional, defaults on | `metricType: Utilization`. Secondary; Kafka lag is primary |
| `prometheus` | not wired | Add via `extra_ignore_differences` / hand-template if you need it |
| `memory` | not wired | Same |

The Kafka trigger pulls `bootstrapServers` from
`.Values.config.kafka.brokers` -- which means your `default_config`
needs a `kafka.brokers` key for `helm template` to render. The Tier A
test (see [TEST-SUPPORT.md](TEST-SUPPORT.md)) sets this via
`--set config.kafka.brokers=localhost:9092`.

The CPU trigger only renders when `.Values.keda.cpu.enabled` is true
in the rendered `values.yaml`. Disabling it at deploy time is a
values override.

---

## Fallback HPA

`templates/hpa.yaml` is always generated. The render gate is
`{{- if and .Values.autoscaling.enabled (not .Values.keda.enabled) }}`,
so the HPA only materialises when:

- `autoscaling.enabled=true` AND
- `keda.enabled=false` (or the chart was generated without
  `contract.keda`)

KEDA's `ScaledObject` creates its own HPA internally; the two are
mutually exclusive on purpose to avoid duelling controllers.

Default HPA `values.yaml` shape:

```yaml
autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
```

---

## Replicas precedence

`deployment.yaml` gates `spec.replicas` on
`{{- if not (or .Values.keda.enabled .Values.autoscaling.enabled) }}`,
so:

| `keda.enabled` | `autoscaling.enabled` | `replicas` source |
|---|---|---|
| true | any | KEDA `ScaledObject` (replicas removed from Deployment) |
| false | true | HPA (replicas removed from Deployment) |
| false | false | `.Values.replicaCount` (default `1`) |

The `Deployment` is in `ignoreDifferences` for `/spec/replicas` in
every generated ArgoCD `Application` so ArgoCD doesn't fight either
controller.

---

## Runtime signal feed

The runtime side of scaling is `hyperi_pylib.scaling.ScalingPressure`
-- a composite consumer-lag + buffer-pressure + CPU pressure score the
service exports as a single gauge. KEDA's external/prometheus trigger
can scrape that gauge for finer-grained signals than raw consumer lag.
See [../api/SCALING.md](../api/SCALING.md).

---

## Related

- [CONTRACT.md](CONTRACT.md)
- [ARTEFACTS.md](ARTEFACTS.md)
- [../api/SCALING.md](../api/SCALING.md)
- [IDENTITY.md](IDENTITY.md)
- [TEST-SUPPORT.md](TEST-SUPPORT.md)
- [../INTEGRATION.md](../INTEGRATION.md)
