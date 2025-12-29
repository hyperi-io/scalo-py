# hs-pylib

<!-- BADGES:START -->
[![Build Status](https://github.com/hypersec-io/hs-pylib/workflows/CI%20Publish/badge.svg)](https://github.com/hypersec-io/hs-pylib/actions)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
<!-- BADGES:END -->

Enterprise Python infrastructure for HyperSec projects.

hs-pylib provides container-native application patterns, metrics, logging, and infrastructure utilities for all HyperSec Python projects.

## Features

### Core Infrastructure (Stable)

- **Logging**: Structured JSON logging with sensitive data masking
- **PII Anonymization**: ML-based anonymization with Presidio integration
- **Database Utilities**: ClickHouse, PostgreSQL, MySQL, Redis connection helpers
- **Configuration**: Multi-layer cascade with environment variable support
- **Runtime**: Application metadata and environment detection

### Application Framework (Experimental)

- **Application Types**: API (FastAPI), Daemon, CLI (Typer), MCP, and Oneshot
- **Profile-Based Configuration**: `dev`, `docker`, and `prod` profiles
- **Health Checks**: Kubernetes-ready liveness/readiness probes
- **Metrics**: Prometheus and OpenTelemetry backends

> **Note:** The Application framework is experimental and may change. Use the stable core modules (logging, config, runtime, database, metrics) directly for production code.

## Installation

> **Package naming:** `hs-pylib` on PyPI, `hs_pylib` for Python imports.

### pyproject.toml Configuration (Recommended)

For projects using uv with both JFrog (hs-pylib) and PyPI packages, add this to your `pyproject.toml`:

```toml
[tool.uv]
index-strategy = "unsafe-best-match"

[[tool.uv.index]]
name = "hypersec-jfrog"
url = "https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi/simple"
explicit = true

[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple"
default = true

[tool.uv.sources]
hs-pylib = { index = "hypersec-jfrog" }
```

**Key settings:**

- `index-strategy = "unsafe-best-match"` - Allows mixing packages from JFrog and PyPI
- `explicit = true` on JFrog - Only use JFrog for explicitly mapped packages
- `default = true` on PyPI - Use PyPI for everything else
- `[tool.uv.sources]` - Explicitly route `hs-pylib` to JFrog

Then set credentials via environment variables and install:

```bash
# uv looks for UV_INDEX_{NAME}_USERNAME and UV_INDEX_{NAME}_PASSWORD
# where {NAME} is the uppercase index name with non-alphanumeric chars replaced by underscores
export UV_INDEX_HYPERSEC_JFROG_USERNAME="your-email@hypersec.io"
export UV_INDEX_HYPERSEC_JFROG_PASSWORD="your-jfrog-api-key"

uv sync
```

### Command-Line Installation

```bash
# Set credentials (same env vars work for CLI)
export UV_INDEX_HYPERSEC_JFROG_USERNAME="your-email@hypersec.io"
export UV_INDEX_HYPERSEC_JFROG_PASSWORD="your-jfrog-api-key"

# Using uv with extra-index-url
uv pip install hs-pylib \
  --extra-index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi/simple

# With optional dependencies
uv pip install hs-pylib[presidio,opentelemetry] \
  --extra-index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi/simple
```

### Optional Dependencies

- `hs-pylib[presidio]` - PII anonymization
- `hs-pylib[opentelemetry]` - OpenTelemetry metrics
- `hs-pylib[api]` - FastAPI support
- `hs-pylib[metrics]` - Prometheus metrics

## Quick Start

### API Application (FastAPI)

```python
from hs_pylib import Application

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
from hs_pylib import Application

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
from hs_pylib import Application

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

1. Environment variable: `HS_LIB_PROFILE` or `APP_PROFILE`
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
helm install my-app ./templates/helm/hs-pylib-app \
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
# Quality checks
ruff check src/ tests/
ruff format src/ tests/

# Tests
pytest tests/

# Build
uv build
```

## License

Proprietary - HyperSec Internal Use Only
