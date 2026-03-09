# hyperi-pylib Examples

Standalone example projects demonstrating hyperi-pylib features.

Each example is a complete, runnable project with its own `pyproject.toml`, tests, and documentation.

## Examples

| Example | Description | Key Features |
|---------|-------------|--------------|
| [basic-logging](basic-logging/) | Structured logging | RFC 3339 timestamps, log levels, structured context |
| [config-cascade](config-cascade/) | Configuration system | 8-layer cascade, YAML/ENV, environment detection |
| [postgres-cache](postgres-cache/) | PostgreSQL cache | Multi-pod cache, TTL expiration, bulk invalidation |
| [kafka-producer-consumer](kafka-producer-consumer/) | Kafka client | Producer/consumer, corporate defaults, health monitoring |
| [fastapi-metrics](fastapi-metrics/) | Prometheus metrics | Counters, gauges, histograms, `/metrics` endpoint |

## Quick Start

Each example follows the same pattern:

```bash
cd examples/<example-name>

# Install dependencies
uv sync

# Run the example
uv run python main.py

# Run tests
uv run pytest
```

## Example Structure

All examples follow this structure:

```
<example-name>/
├── pyproject.toml      # Project config with hyperi-pylib dependency
├── README.md           # Documentation
├── main.py             # Main example code
├── tests/
│   ├── __init__.py
│   └── test_main.py    # Tests for the example
└── [optional files]    # docker-compose.yml, settings.yaml, etc.
```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager (recommended)
- Docker (for postgres-cache and kafka examples)

## Installing hyperi-pylib

Examples install hyperi-pylib from PyPI. For local development against the library source:

```bash
# From the example directory
uv add --editable ../..
```

## Running Tests

Run tests for a single example:

```bash
cd examples/basic-logging
uv run pytest
```

Run tests for all examples:

```bash
for dir in examples/*/; do
    echo "Testing $dir"
    (cd "$dir" && uv sync && uv run pytest)
done
```

## Docker Dependencies

Some examples require external services:

| Example | Service | Start Command |
|---------|---------|---------------|
| postgres-cache | PostgreSQL | `docker compose up -d` |
| kafka-producer-consumer | Kafka | `docker compose up -d` |

## Contributing

When adding new examples:

1. Create a new directory under `examples/`
2. Include `pyproject.toml` with hyperi-pylib dependency
3. Include `README.md` with quick start and explanation
4. Include `main.py` as the entry point
5. Include `tests/test_main.py` with basic tests
6. Add the example to this README

## See Also

- [hyperi-pylib Documentation](../docs/)
- [hyperi-pylib API Reference](../src/hyperi_pylib/)
