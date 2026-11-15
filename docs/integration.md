# Integration

Wiring `scalo` into a new Python service from an empty `pyproject.toml` to a running app. Details per subsystem live in the subsystem docs (core-pillars/, runtime/, transport/, deployment/, api/).

---

## 1. Pick your extras

Two questions:

- **Service or tool?** A long-running service (FastAPI, Kafka consumer,
  scheduled worker) versus a one-shot CLI / data-pipeline run.
- **Which integrations?** Kafka? AWS / GCP /
  Azure / Vault secrets?

For a typical data-pipeline service that talks to Kafka, exports Prometheus +
OTel metrics, uses Vault secrets, and ships container artefacts:

```toml
[project]
dependencies = [
    "scalo[kafka,metrics,secrets-vault,deployment,resilience,http]",
]
```

For a tooling CLI that just reads config and writes logs:

```toml
dependencies = ["scalo"]
```

`config` and `logger` ship in the base package, so nothing extra is needed. Pin the floor to the release you test against.

See [extras-flags.md](extras-flags.md) for the full extras tree and
recommended bundles.

---

## 2. Config

`scalo.config` exposes a `settings` object built from a 7-layer cascade: your CLI flags, env, `.env`, `settings.<env>.yaml`, `settings.yaml`, `defaults.yaml`, then the fallback in your code. Read it like a dict with dotted keys.

```python
from scalo.config import settings

brokers = settings.get("kafka.brokers", "localhost:9092")
batch_size = settings.get("processor.batch_size", 100)
```

Importing reads no `.env`. The `.env` layer loads when the app calls `get_config()` or runs under `ServiceApp.cli()`, so an app that reads `settings` directly calls `get_config()` once at startup.

An env key nests with a double underscore: `KAFKA__BROKERS=...` maps to `settings.kafka.brokers`, and `KAFKA_BROKERS` would set a top-level `kafka_brokers`. Cross-cutting envs (`LOG_LEVEL`, `DOTENV_CASCADE`, `CONTAINER_BASE_PATH`) override defaults without needing a settings file.

See [core-pillars/config.md](core-pillars/config.md) for the full
cascade and sensitive masking.

---

## 3. Logger

```python
from scalo.logger import error, info, logger, setup

setup()  # ServiceApp calls this for you; importing scalo.logger installs nothing
info("Service starting", version="1.4.0")
logger.bind(component="kafka_consumer").info("subscribed", topic="events")

try:
    process()
except Exception:
    logger.exception("processing failed", retries=3)   # logs the traceback too
```

`setup()` autodetects the format: JSON when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, else human-readable text in CI or on a TTY, and JSON otherwise, as in a container (see [Format selection](core-pillars/logging.md#format-selection)). Secrets, credential field names and PII values are scrubbed from every message and field at every level but TRACE. Timestamps are RFC 3339.

See [core-pillars/logging.md](core-pillars/logging.md) for scrub, rate
limiting, CI mode, and the emoji-to-text conversion.

---

## 4. Metrics

```python
from scalo.metrics import create_metrics

m = create_metrics("my_service")
requests = m.counter("requests_total", "Total requests", ["method", "status"])
requests.labels(method="POST", status="200").inc()
```

The default backend is OpenTelemetry, which pushes over OTLP and serves a Prometheus body for `/metrics`. Nothing caps label cardinality unless you wire `CardinalityTracker` in.

For Kafka consumers and processing services, `scalo.metrics.groups` has the standard groups -- `AppMetrics`, `ConsumerMetrics`, `BufferMetrics`, `SinkMetrics`, `BackpressureMetrics`, `CircuitBreakerMetrics` -- each registering fixed metric names and labels when you construct it.

See [core-pillars/metrics.md](core-pillars/metrics.md).

---

## 5. Health probes

```python
from fastapi import FastAPI
from scalo.health import HealthManager, create_health_router

health = HealthManager()
# fastapi 0.142+ otherwise reads OTEL_EXPORTER_OTLP_ENDPOINT and adds http/protobuf exporters, which fail against a gRPC collector.
app = FastAPI(telemetry={"auto_configure": False})
app.include_router(create_health_router(health))

# At startup, after dependencies are connected:
health.set_ready()

# Register downstream checks:
async def db_ok() -> bool:
    return await db.execute("SELECT 1") is not None

health.register_ready_check("postgres", db_ok)
```

That gives you `/livez` and `/readyz`, answering 200 or 503 with a JSON body.
Aim a `startupProbe` at `/livez` -- there is no separate startup path.

See [core-pillars/health.md](core-pillars/health.md).

---

## 6. Runtime context

```python
from scalo.runtime import get_runtime_paths

paths = get_runtime_paths("my-service")
config_file = paths.config_dir / "app.yaml"   # /app/config in a container, ~/.my-service/config locally
data_file = paths.data_dir / "state.db"       # /app/data in a container, ~/.my-service/data locally
cache_file = paths.cache_dir / "warmup.json"  # /app/cache in a container, ~/.my-service/cache locally
```

Same code in K8s, Docker, and bare metal. Each call walks 7 indicators (`/var/run/secrets`, env vars, `/.dockerenv`, cgroups v1/v2, mountinfo, PID 1) and creates the directories.

See [runtime/runtime-context.md](runtime/runtime-context.md).

---

## 7. Secrets

```python
from scalo.secrets import SecretsManager

sm = SecretsManager.from_config(settings.get("secrets"))
api_key = await sm.get_string("third-party/api-key")
```

One interface over every backend. `from_config` builds a provider for each backend key in the dict (`openbao` or `vault`, `aws`, `gcp`, `azure`, `kubernetes`) plus `file`, and each named source picks its provider. Each backend needs its extra (`secrets-vault`, `secrets-aws`, etc.).

See [api/secrets.md](api/secrets.md).

---

## 8. Kafka (if you need it)

```python
from scalo.kafka import KafkaProducer, KafkaConsumer

producer = KafkaProducer({"bootstrap.servers": settings.get("kafka.brokers")})
producer.send("events", key=b"k", value=b'{"event":"x"}')
producer.flush()

consumer = KafkaConsumer(
    {"bootstrap.servers": settings.get("kafka.brokers")},
    group_id="my-service",
)
consumer.subscribe(["events"])
while True:
    msg = consumer.poll(timeout=1.0)
    if msg is None:
        continue
    handle(msg.value)
```

At-least-once producer defaults, schema sampling, a consumer-lag health probe and async wrappers (`AsyncKafkaProducer`, `AsyncKafkaConsumer`) are all available.

See [transport/kafka.md](transport/kafka.md).

---

## 9. Deployment contract

Define the contract once, generate the image artefacts from it:

```python
from scalo.deployment import (
    DeploymentContract, HealthContract, OciLabels,
    generate_dockerfile, generate_container_manifest,
    ContractIdentity,
)

contract = DeploymentContract(
    app_name="my-service",
    metrics_port=9090,
    health=HealthContract(),
    env_prefix="MY_SERVICE",
    metric_prefix="my_service",
    config_mount_path="/etc/my-service.yaml",
    image_registry="registry.example.com/team",
)

# Contract Identity v1 labels stamp the image:
identity = ContractIdentity.detect(image_ref="registry.example.com/team/my-service:v1.0.0")

dockerfile = generate_dockerfile(contract, identity=identity)
manifest = generate_container_manifest(contract, identity=identity)
```

That gives you a Dockerfile and a container manifest, both carrying the three `io.scalo.contract.*` identity keys (version, source-commit, image-ref). The contract names no distributor, licence or copyright until you set `OciLabels(vendor=..., licenses=..., copyright=...)`, and `OciLabels(label_namespace=...)` moves scalo's own keys under your reverse-DNS name.

The Kubernetes objects come from the scalo-service library chart, which renders the `deployment-contract.json` that `generate-artefacts` writes. To preview a service's chart locally, run `hyperi-ci chart assemble` -- see [deployment/artefacts.md](deployment/artefacts.md#kubernetes-objects).

See [deployment/contract.md](deployment/contract.md),
[deployment/artefacts.md](deployment/artefacts.md), and
[deployment/identity.md](deployment/identity.md).

---

## 10. Testing the service

For the deployment contract, an e2e TEMPLATE lives at [`tests/e2e/test_contract_artefacts.py`](../tests/e2e/test_contract_artefacts.py). Copy it into your own `tests/e2e/` and point it at your entrypoint. It runs Tier A (cluster-less: docker build and run) locally when docker is present, and every skip it takes prints a `HYPERCI-SKIP[contract-e2e][...]:` line. See [deployment/test-support.md](deployment/test-support.md) for that and the shared test services.

On a hyperi-ci project, `hyperi-ci check` runs quality and tests before a push, `--quick` runs quality only, and `--full` adds the build.

---

## Checklist for a new service

- [ ] `pyproject.toml` lists `scalo` with the right extras
- [ ] `settings.yaml` in the repo for static config, env vars for per-environment override
- [ ] Logger imported at the top of `main`
- [ ] `create_metrics(<app_name>)` called once, served on `/metrics`
- [ ] `HealthManager` created, `set_ready()` called after dependencies connect, downstream checks registered
- [ ] If Kafka: producer flushed in shutdown, consumer commits on `SIGTERM`
- [ ] `DeploymentContract` returned from `deployment_contract()`, so `generate-artefacts` writes its files
- [ ] e2e test template copied into `tests/e2e/` and adapted for the service's actual entrypoint

---

## Related

- [README.md](README.md)
- [architecture.md](architecture.md)
- [auto-wiring.md](auto-wiring.md)
- [extras-flags.md](extras-flags.md)
- [deployment/contract.md](deployment/contract.md)
