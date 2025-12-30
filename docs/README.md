# hs-pylib Documentation

Production-ready infrastructure for Python applications.

## Application Types

hs-pylib provides 5 application types with container-native patterns:

- **[API](APP-API.md)** - FastAPI applications with auto-metrics and health checks
- **[Daemon](APP-DAEMON.md)** - Long-running background services with scheduled tasks
- **[CLI](APP-CLI.md)** - Command-line tools using Typer (mandatory standard)
- **[Oneshot](APP-ONESHOT.md)** - Single-run jobs for k8s Jobs/CronJobs
- **[MCP](APP-MCP.md)** - Model Context Protocol servers for AI tool integration

## Core Features

- **[Logging](LOGGING.md)** - Structured logging with auto-configuration and sensitive data masking
- **[Metrics](METRICS.md)** - Prometheus and OpenTelemetry metrics with automatic collection
- **[Configuration](CONFIG.md)** - 7-layer configuration cascade (ENV → .env → config files → defaults)
- **[Anonymizer](ANONYMIZER.md)** - PII detection and anonymization using Microsoft Presidio

> Heads-up: the bundled `Application.*` framework referenced below is currently removed from the codebase (see TODO/STATE for context). Use the modular APIs directly or restore the legacy application package from history if you still depend on it.

## Standards

- **[CLI Standards](CLI-STANDARDS.md)** - Typer framework standards (mandatory)
- **[Testing](TESTING.md)** - Testing patterns and best practices

## Quick Start

```bash
pip install hs-pylib
```

### API Application

```python
from hs_pylib import Application

app = Application.api(name="my-api", profile="prod")

@app.get("/")
def root():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run()  # python -m myapp serve --profile prod
```

### Daemon Application

```python
from hs_pylib import Application

app = Application.daemon(name="worker", profile="prod")

@app.task(interval=60)
def process_queue():
    # Runs every 60 seconds
    pass

if __name__ == "__main__":
    app.run()  # python -m worker start --profile prod
```

### CLI Application

```python
from hs_pylib import Application

app = Application.cli(name="my-tool", version="1.0.0")

@app.command()
def sync(source: str, dest: str):
    """Sync files."""
    print(f"Syncing {source} -> {dest}")

app.run()  # my-tool sync /src /dest
```

## Profiles

All applications support 3 profiles:

- **dev** - Local development (debug logging, no metrics)
- **docker** - CI/CD containers (JSON logs, health checks, metrics)
- **prod** - Kubernetes (optimized, health checks, metrics, JSON logs)

Configure via:

- CLI flag: `--profile prod`
- ENV var: `HS_LIB_PROFILE=prod`
- Code: `Application.api(profile="prod")`

## Container Deployment

All applications are container-ready with built-in health checks and metrics.

**Complete guides:**

- **[Docker Deployment](CONTAINER_DEPLOYMENT.md)** - Docker Compose and standalone deployments
- **[Kubernetes](KUBERNETES.md)** - Production k8s with HELM + ArgoCD + KEDA
- **[Profiles](PROFILES.md)** - Environment configuration (dev/docker/prod)

### Quick Examples

**Multi-stage Dockerfile:**

```dockerfile
# Build stage
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY src/ ./src/

# Runtime stage
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl netcat-openbsd iputils-ping && \
    rm -rf /var/lib/apt/lists/*
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src /app/src
ENV PATH="/app/.venv/bin:$PATH"
USER nobody
CMD ["python", "-m", "myapp", "serve", "--profile", "prod"]
```

**Kubernetes Deployment:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: myapp
        image: myapp:1.0.0
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 8080
          name: health
        - containerPort: 9090
          name: metrics
        env:
        - name: HS_LIB_PROFILE
          value: "prod"
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 1000m
            memory: 512Mi
```

**KEDA Autoscaling:**

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: myapp-scaler
spec:
  scaleTargetRef:
    name: myapp
  minReplicaCount: 2
  maxReplicaCount: 10
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      query: rate(http_requests_total{app="myapp"}[1m])
      threshold: "100"
```

**Working Examples:**

- [examples/api-container/](../examples/api-container/) - Complete FastAPI REST API with k8s deployment
- [examples/daemon-container/](../examples/daemon-container/) - Background worker with KEDA scaling

## Architecture

### Application Inheritance

```text
APIApplication(CLIExecutableMixin, SignalHandlerMixin, ProfileMixin, HealthCheckMixin, MetricsMixin)
DaemonApplication(CLIExecutableMixin, SignalHandlerMixin, ProfileMixin, MetricsMixin)
MCPApplication(CLIExecutableMixin, SignalHandlerMixin, ProfileMixin, MetricsMixin)
OneshotApplication(CLIExecutableMixin, SignalHandlerMixin, ProfileMixin)
CLIApplication(SignalHandlerMixin, ProfileMixin)
```

### Mixins

- **ProfileMixin** - Profile-based configuration (dev/docker/prod)
- **SignalHandlerMixin** - Graceful shutdown (SIGTERM/SIGINT)
- **CLIExecutableMixin** - Typer CLI integration
- **HealthCheckMixin** - Health and readiness endpoints
- **MetricsMixin** - Metrics tracking (Prometheus/OTEL)

## Use Cases

### Microservices

```python
# FastAPI service with auto-metrics
app = Application.api(name="user-service", profile="prod")

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}
```

### Background Workers

```python
# Daemon with scheduled tasks
app = Application.daemon(name="email-worker", profile="prod")

@app.task(interval=60)
def send_pending_emails():
    emails = get_pending_emails()
    for email in emails:
        send_email(email)
```

### Data Pipelines

```python
# Oneshot job for ETL
app = Application.oneshot(name="daily-etl", profile="prod")

@app.task
def run_etl():
    extract_data()
    transform_data()
    load_data()
```

### CLI Tools

```python
# Command-line tool
app = Application.cli(name="data-tool", version="1.0.0")

@app.command()
def extract(source: str, output: str):
    """Extract data from source."""
    data = load_data(source)
    save_data(output, data)
```

### AI Tool Integration

```python
# MCP server for/Continue
app = Application.mcp(name="db-tools", version="1.0.0")

@app.tool(name="query", description="Query database")
def query_db(sql: str) -> list:
    return execute_query(sql)
```

## Integration Examples

### Logging

```python
from hs_pylib import logger

logger.info("Application started")
logger.error("Failed to connect", database="prod-db", retry=3)
```

### Metrics

```python
from hs_pylib.metrics import create_metrics

metrics = create_metrics("myapp")
metrics.counter("requests", "Total requests").inc()
metrics.gauge("queue_size", "Queue size").set(42)
```

### Configuration

```python
from hs_pylib.config import get_config

config = get_config()
db_url = config["database"]["url"]
```

### Anonymization

```python
from hs_pylib.anonymizer import anonymize_text

text = "My SSN is 123-45-6789"
clean = anonymize_text(text, preset="compliance")
# "My SSN is <US_SSN>"
```

## Migration Guide

### From Flask/Django

Replace with FastAPI-based Application.api():

```python
# Before (Flask)
app = Flask(__name__)

@app.route("/users")
def get_users():
    return {"users": []}

# After (hs-pylib)
app = Application.api(name="my-api")

@app.get("/users")
def get_users():
    return {"users": []}
```

### From Click

Replace with Typer-based Application.cli():

```python
# Before (Click)
@click.command()
@click.option("--source")
def sync(source):
    pass

# After (hs-pylib)
app = Application.cli(name="my-tool")

@app.command()
def sync(source: str):
    pass
```

## Repository

- **GitHub**: <https://github.com/hypersec-io/hs-pylib>
- **Issues**: <https://github.com/hypersec-io/hs-pylib/issues>

## License

See LICENSE file in repository.
