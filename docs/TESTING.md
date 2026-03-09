# hyperi-pylib Testing Guide

## Prerequisites

- Python 3.12+
- `uv` package manager
- `hyperi-ci` CLI: `uv tool install hyperi-ci`
- Docker (for integration tests requiring external services)

## Running Tests

### Via Make (Recommended)

```bash
make test          # Runs the full test suite via hyperi-ci
```

### Directly with pytest

```bash
uv run pytest tests/ -v

# By category
uv run pytest tests/unit/ -v         # Fast, no external dependencies
uv run pytest tests/integration/ -v  # Requires Docker for services
uv run pytest tests/e2e/ -v          # End-to-end scenarios

# By marker
uv run pytest -m unit
uv run pytest -m integration
```

### Specific Test

```bash
uv run pytest tests/unit/test_cli_app.py::TestDfeApp::test_version_command -v
```

## Coverage

```bash
uv run pytest --cov=src/hyperi_pylib --cov-report=term-missing
```

Minimum 80% enforced by CI.

## Test Markers

Defined in `pyproject.toml`:

| Marker | Description |
|--------|-------------|
| `unit` | Fast, no external dependencies |
| `integration` | Requires Docker / external services |
| `e2e` | Full end-to-end scenarios |

## Kafka Integration Tests

Kafka tests use a Docker Compose fixture:

```bash
docker compose -f docker-compose.kafka.yml up -d
uv run pytest tests/integration/ -m integration -v
docker compose -f docker-compose.kafka.yml down
```

## Test Logging

Logs to `tests/logs/pytest/hyperi-pylib.log` (configured in `pyproject.toml`).

## Troubleshooting

Integration tests skip when external services are unavailable. Check the service
is running before assuming a test is broken:

```bash
docker compose -f docker-compose.kafka.yml ps
docker ps | grep postgres
```

Ensure the package is installed in dev mode if you see import errors:

```bash
uv sync
```
