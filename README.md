# Hyperlib

**Enterprise Python Infrastructure for HyperSec Projects**

Hyperlib is a production-ready Python library providing container-native application patterns, metrics, logging, and infrastructure utilities for all HyperSec Python projects.

## Features

- **Application Framework**: API (FastAPI), Daemon, CLI (Typer), MCP, and Oneshot application types
- **Profile-Based Configuration**: `dev`, `docker`, and `prod` profiles with automatic environment detection
- **Health Checks**: Kubernetes-ready liveness/readiness probes with custom dependency checks
- **Metrics**: Prometheus and OpenTelemetry backends with automatic collection
- **Logging**: Structured JSON logging with sensitive data masking
- **PII Anonymization**: ML-based anonymization with Presidio integration
- **Database Utilities**: ClickHouse, PostgreSQL, MySQL, Redis connection helpers
- **HELM Charts**: Production-ready Kubernetes deployments with KEDA autoscaling

## Installation

```bash
# From JFrog (HyperSec private registry)
pip install hyperlib --index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple

# With optional dependencies
pip install hyperlib[presidio]  # PII anonymization
pip install hyperlib[opentelemetry]  # OpenTelemetry metrics
```

## Quick Start

### API Application (FastAPI)

```python
from hyperlib import Application

app = Application.api(name="my-api", version="1.0.0", profile="prod")

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.health_check
async def check_database():
    # Custom health check
    return await db.ping()

app.run()
```

### Daemon Application

```python
from hyperlib import Application

app = Application.daemon(name="my-worker", profile="prod")

@app.scheduled(interval=60)
async def process_queue():
    # Runs every 60 seconds
    await process_messages()

@app.startup
async def on_start():
    await initialize_database()

app.run()
```

### CLI Application (Typer)

```python
from hyperlib import Application

app = Application.cli(name="my-tool", version="1.0.0")

@app.command()
def deploy(environment: str, region: str = "us-east-1"):
    """Deploy application to environment."""
    print(f"Deploying to {environment} in {region}")

app.run()
```

## Profiles

- **`dev`**: Development mode (console logs, no health checks)
- **`docker`**: Docker Compose mode (JSON logs, health checks on port 8080)
- **`prod`**: Production mode (JSON logs, health checks, metrics on port 9090)

Profiles are auto-detected from:
1. Environment variable: `HYPERLIB_PROFILE` or `APP_PROFILE`
2. Kubernetes detection (sets `prod`)
3. Docker detection (sets `docker`)
4. Default: `dev`

## Container Deployment

### Docker

```bash
# Build
docker build -t my-app:latest .

# Run with health checks
docker run -p 8000:8000 -p 8080:8080 -e PROFILE=docker my-app:latest
```

### Kubernetes (HELM)

```bash
helm install my-app ./templates/helm/hyperlib-app \
  --set app.type=api \
  --set image.repository=my-app \
  --set image.tag=1.0.0 \
  --set keda.enabled=true
```

## Documentation

- **Application Framework**: `docs/APP-*.md`
- **Profiles**: `docs/PROFILES.md`
- **Kubernetes**: `docs/KUBERNETES.md`
- **Metrics**: `docs/METRICS.md`
- **Logging**: `docs/LOGGING.md`
- **Anonymizer**: `docs/ANONYMIZER.md`

## Development

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup
./ci/bootstrap --install

# Test
./ci/run check

# Build
./ci/run build
```

## License

Proprietary - HyperSec Internal Use Only

## Support

Internal support: #hyperlib on Slack
