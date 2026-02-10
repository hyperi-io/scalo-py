# hyperi-pylib

<!-- BADGES:START -->
[![Build Status](https://github.com/hyperi-io/hyperi-pylib/workflows/CI%20Publish/badge.svg)](https://github.com/hyperi-io/hyperi-pylib/actions)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
<!-- BADGES:END -->

Enterprise Python infrastructure for HyperI projects.

hyperi-pylib provides metrics, logging, and infrastructure utilities for all HyperI Python projects.

> Note: The previous `Application.*` framework (API/Daemon/CLI/Oneshot/MCP) was removed in 2.13.x. Use the individual modules (`logger`, `metrics`, `config`, `kafka`, `http`, `cache`) directly or restore the legacy package from history if you need it.

## Features

- **Logging**: Structured JSON logging with sensitive data masking
- **PII Anonymization**: ML-based anonymization with Presidio integration
- **Database Utilities**: ClickHouse, PostgreSQL, MySQL, Redis connection helpers
- **Configuration**: Multi-layer cascade with environment variable support
- **Runtime**: Application metadata and environment detection
- **Metrics**: Prometheus and OpenTelemetry backends
- **Kafka**: Complete Kafka client library with admin, consumer, producer, and schema analysis
- **Harness**: Smart timeout monitors and container registry utilities
- **CLI**: Typer-based CLI utilities

## Installation

> **Package naming:** `hyperi-pylib` on PyPI, `hyperi_pylib` for Python imports.

### pyproject.toml Configuration (Recommended)

For projects using uv with both JFrog (hyperi-pylib) and PyPI packages, add this to your `pyproject.toml`:

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
hyperi-pylib = { index = "hypersec-jfrog" }
```

**Key settings:**

- `index-strategy = "unsafe-best-match"` - Allows mixing packages from JFrog and PyPI
- `explicit = true` on JFrog - Only use JFrog for explicitly mapped packages
- `default = true` on PyPI - Use PyPI for everything else
- `[tool.uv.sources]` - Explicitly route `hyperi-pylib` to JFrog

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
uv pip install hyperi-pylib \
  --extra-index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi/simple

# With optional dependencies
uv pip install hyperi-pylib[presidio,opentelemetry] \
  --extra-index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi/simple
```

### Optional Dependencies

- `hyperi-pylib[presidio]` - PII anonymization
- `hyperi-pylib[opentelemetry]` - OpenTelemetry metrics
- `hyperi-pylib[api]` - FastAPI support
- `hyperi-pylib[metrics]` - Prometheus metrics

## Quick Start

### Logging

```python
from hyperi_pylib import logger

logger.setup(app_name="my-app", json_output=True)
logger.info("Application started")
logger.error("Something went wrong", exc_info=True)
```

### Configuration

```python
from hyperi_pylib import config

# Initialize configuration
config.setup(app_name="my-app")

# Access settings
settings = config.get_settings()
db_config = config.get_database_config()
```

### Database Connections

```python
from hyperi_pylib import database

# Get database URLs from environment
postgres_url = database.get_postgresql_url()
redis_url = database.get_redis_url()

# Build custom connection URL
url = database.build_database_url(
    driver="postgresql",
    host="localhost",
    port=5432,
    database="mydb",
    username="user",
    password="pass"
)
```

### Kafka

```python
from hyperi_pylib.kafka import KafkaClient

# Create client with configuration
client = KafkaClient.from_config(config_file="kafka.properties")

# Produce messages
await client.produce("my-topic", {"key": "value"})

# Consume messages
async for message in client.consume("my-topic", group_id="my-group"):
    process(message)
```

### Metrics

```python
from hyperi_pylib.metrics import create_metrics_backend

# Prometheus backend
metrics = create_metrics_backend("prometheus")
counter = metrics.counter("requests_total", "Total requests")
counter.inc()
```

## Documentation

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

FSL-1.1-ALv2 - See LICENSE
