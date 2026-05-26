# Integration

Wiring `hyperi-pylib` into a new Python service from empty
`pyproject.toml` to running app. Self-contained recipe; details per subsystem
live in the subsystem docs (core-pillars/, runtime/, transport/, deployment/, api/).

---

## 1. Pick your extras

Two questions:

- **Service or tool?** A long-running service (FastAPI, Kafka consumer,
  scheduled worker) versus a one-shot CLI / data-pipeline run.
- **Which integrations?** Kafka? PostgreSQL config source? AWS / GCP /
  Azure / Vault secrets?

For a typical DFE service that talks to Kafka, exports Prometheus +
OTel metrics, uses Vault secrets, and ships container artefacts:

```toml
[project]
dependencies = [
    "hyperi-pylib[kafka,metrics,opentelemetry,secrets-vault,deployment,resilience,http]>=2.28.3",
]
```

For a tooling CLI that just reads config and writes logs:

```toml
dependencies = ["hyperi-pylib>=2.28.3"]
```

`config` and `logger` ship in the base package — nothing extra needed.

See [EXTRAS-FLAGS.md](EXTRAS-FLAGS.md) for the full extras tree and
recommended bundles.

---

## 2. Config

`hyperi_pylib.config` exposes a `settings` object built from an 8-layer
cascade (CLI > env > .env > settings.<env>.yaml > settings.yaml >
defaults.yaml > pylib defaults > hard-coded). Read it like a dict;
nested keys via dot or `__`.

```python
from hyperi_pylib.config import settings

brokers = settings.get("kafka.brokers", "localhost:9092")
batch_size = settings.get("processor.batch_size", 100)
```

Env-var nesting follows the cascade rule: `KAFKA__BROKERS=...` maps to
`settings.kafka.brokers`. Cross-cutting envs (`LOG_LEVEL`,
`HYPERI_CONFIG_DSN`, `CONTAINER_BASE_PATH`) override defaults without
needing a settings file.

See [core-pillars/CONFIG.md](core-pillars/CONFIG.md) for the full
cascade, hot-reload, sensitive masking, and `/config` admin endpoint.

---

## 3. Logger

```python
from hyperi_pylib.logger import logger, info, error

info("Service starting", version="2.28.3")
logger.bind(component="kafka_consumer").info("subscribed", topic="events")

try:
    process()
except Exception as e:
    error("processing failed", exc_info=True, retries=3)
```

Format autodetects: JSON when stdout is not a TTY (containers, CI),
human-readable on a TTY. Secrets get scrubbed automatically via
gitleaks rules + the national-ID validators in `data/`. RFC 3339
timestamps everywhere.

See [core-pillars/LOGGING.md](core-pillars/LOGGING.md) for scrub, rate
limiting, CI mode, and the emoji-to-text conversion.

---

## 4. Metrics

```python
from hyperi_pylib.metrics import create_metrics

m = create_metrics(namespace="my_service")
requests = m.counter("requests_total", "Total requests", ["method", "status"])
requests.labels(method="POST", status="200").inc()
```

Backend default is OpenTelemetry with a Prometheus exporter on
`/metrics`; cardinality is capped per metric (50 by default) to
prevent label explosions.

For Kafka-shaped or processing-shaped services, use the pre-wired
**DFE metric groups** in `metrics.dfe_groups/` — `AppMetrics`,
`ConsumerMetrics`, `BufferMetrics`, `SinkMetrics`, `BackpressureMetrics`,
`CircuitBreakerMetrics`. They emit the standard HyperI metric names
and labels.

See [core-pillars/METRICS.md](core-pillars/METRICS.md).

---

## 5. Health probes

```python
from fastapi import FastAPI
from hyperi_pylib.health import HealthManager, create_health_router

health = HealthManager()
app = FastAPI()
app.include_router(create_health_router(health))

# At startup, after dependencies are connected:
health.set_ready()

# Register downstream checks:
async def db_ok() -> bool:
    return await db.execute("SELECT 1") is not None

health.register_ready_check("postgres", db_ok)
```

That gives you `/health/live`, `/health/ready`, and `/health/startup`
with K8s-shaped responses (200 / 503).

See [core-pillars/HEALTH.md](core-pillars/HEALTH.md).

---

## 6. Runtime context

```python
from hyperi_pylib.runtime import get_runtime_paths

paths = get_runtime_paths()
config_file = paths.config_dir / "app.yaml"   # /config in K8s, ~/.config locally
data_file = paths.data_dir / "state.db"       # /data in K8s, ~/.local/share locally
cache_file = paths.cache_dir / "warmup.json"  # /cache in K8s, ~/.cache locally
```

Same code in K8s, Docker, and bare metal. The detection walks 7
indicators (`/var/run/secrets`, env vars, `/.dockerenv`, cgroups
v1/v2, mountinfo, PID 1) and caches the verdict.

See [runtime/RUNTIME-CONTEXT.md](runtime/RUNTIME-CONTEXT.md).

---

## 7. Secrets

```python
from hyperi_pylib.secrets import SecretsManager

sm = SecretsManager.from_config(settings.get("secrets"))
api_key = await sm.get_string("third-party/api-key")
```

One uniform interface; backends pick themselves up from
`settings.secrets.provider`. OpenBao, Vault, AWS Secrets Manager, GCP
Secret Manager, Azure Key Vault, ansible-vault, and file backends are
all supported via their respective extras (`secrets-vault`,
`secrets-aws`, etc.).

See [api/SECRETS.md](api/SECRETS.md).

---

## 8. Kafka (if you need it)

```python
from hyperi_pylib.kafka import KafkaProducer, KafkaConsumer

producer = KafkaProducer({"bootstrap.servers": settings.get("kafka.brokers")})
producer.send("events", key=b"k", value=b'{"event":"x"}')
producer.flush()

consumer = KafkaConsumer({
    "bootstrap.servers": settings.get("kafka.brokers"),
    "group.id": "my-service",
})
consumer.subscribe(["events"])
while True:
    msg = consumer.poll(timeout=1.0)
    if msg is None:
        continue
    handle(msg.value())
```

Idempotent retry, schema sampling, consumer-lag health probe, and
async wrappers (`AsyncKafkaProducer`, `AsyncKafkaConsumer`) are all
available.

See [transport/KAFKA.md](transport/KAFKA.md).

---

## 9. Deployment contract

Define the contract once, generate every artefact:

```python
from hyperi_pylib.deployment import (
    DeploymentContract, HealthContract, OciLabels,
    generate_dockerfile, generate_chart, generate_argocd_application,
    ContractIdentity, ArgocdConfig,
)

contract = DeploymentContract(
    app_name="my-service",
    metrics_port=9090,
    health=HealthContract(),
    env_prefix="MY_SERVICE",
    metric_prefix="my_service",
    config_mount_path="/etc/my-service.yaml",
)

# Contract Identity v1 labels stamp every artefact:
identity = ContractIdentity.detect(image_ref="ghcr.io/hyperi-io/my-service:v1.0.0")

dockerfile = generate_dockerfile(contract, identity=identity)
generate_chart(contract, "charts/my-service", identity=identity)
argo_yaml = generate_argocd_application(
    contract,
    ArgocdConfig(repo_url="https://github.com/hyperi-io/my-service", target_revision="main"),
    identity=identity,
)
```

That gives you a Dockerfile, a complete Helm chart, an ArgoCD
`Application` manifest, all carrying the three `io.hyperi.contract.*`
identity keys (version, source-commit, image-ref).

See [deployment/CONTRACT.md](deployment/CONTRACT.md),
[deployment/ARTEFACTS.md](deployment/ARTEFACTS.md), and
[deployment/IDENTITY.md](deployment/IDENTITY.md).

---

## 10. Running tests

Pylib uses pytest with `asyncio_mode=auto`. Three marker tiers:

```bash
uv run pytest -m unit          # fast, no external deps
uv run pytest -m integration   # docker-compose fixtures (kafka, postgres, openbao)
uv run pytest -m e2e           # full K8s harness (kind) — env-gated
```

For the deployment contract subsystem, an e2e TEMPLATE lives at
[`tests/e2e/test_contract_artefacts.py`](../tests/e2e/test_contract_artefacts.py).
It runs Tier A (cluster-less: docker build, helm template, kubeconform)
locally when those tools are present, and Tier B (kind cluster + helm
install + ArgoCD apply) when `HYPERI_E2E_CLUSTER=1` is set. Skips
emit a canonical `HYPERCI-SKIP[contract-e2e][...]:` prefix; see
[deployment/TEST-SUPPORT.md](deployment/TEST-SUPPORT.md).

Run the full pipeline locally — same code path as CI:

```bash
hyperi-ci check          # quality + tests + build (no publish)
hyperi-ci check --quick  # quality + unit tests only
```

---

## Checklist for a new service

- [ ] `pyproject.toml` lists `hyperi-pylib` with the right extras
- [ ] `settings.yaml` in the repo for static config; env vars for
      per-environment override
- [ ] Logger imported at the top of `main`
- [ ] `create_metrics(namespace=<app>)` called once, registered on
      `/metrics`
- [ ] `HealthManager` created, `set_ready()` called after dependencies
      connect, downstream checks registered
- [ ] If Kafka: producer flushed in shutdown; consumer commits on
      `SIGTERM`
- [ ] `DeploymentContract` defined and `generate_*` artefacts committed
      to the gitops repo
- [ ] e2e test template copied into `tests/e2e/` and adapted for the
      service's actual entrypoint

---

## Related

- [README.md](README.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [AUTO-WIRING.md](AUTO-WIRING.md)
- [EXTRAS-FLAGS.md](EXTRAS-FLAGS.md)
- [deployment/CONTRACT.md](deployment/CONTRACT.md)
