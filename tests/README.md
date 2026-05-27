# hyperi-pylib Test Suite

Test organisation for hyperi-pylib following standard testing patterns.

## Directory Structure

```
tests/
+-- conftest.py           # Shared pytest fixtures and configuration
+-- unit/                 # Unit tests (fast, isolated)
|   +-- test_config*.py   # Configuration tests
|   +-- test_cache*.py    # Cache tests
|   +-- test_kafka*.py    # Kafka tests
|   +-- test_logger*.py   # Logger tests
|   +-- test_*.py         # Other module tests
+-- integration/          # Integration tests (require services)
|   +-- test_kafka*.py    # Kafka integration (requires Docker)
|   +-- test_cache*.py    # PostgreSQL cache (requires Docker)
|   +-- test_config*.py   # PostgreSQL config (requires Docker)
+-- e2e/                  # End-to-end tests
    +-- (future tests)
```

## Test Types

### Unit Tests (`tests/unit/`)

Fast, isolated tests that verify individual components without external dependencies.

- **Scope**: Single functions, classes, or modules
- **Speed**: < 1s per test
- **Dependencies**: None (mocked if needed)
- **Example**: Testing configuration parsing, key generation

**Run unit tests only:**

```bash
pytest tests/unit/ -v
```

### Integration Tests (`tests/integration/`)

Tests that verify components work together correctly with real services.

- **Scope**: Multiple components interacting
- **Speed**: 1-10s per test
- **Dependencies**: Real services via Docker
- **Example**: Testing PostgreSQL cache, Kafka producer/consumer

**Run integration tests only:**

```bash
pytest tests/integration/ -v
```

**Note**: Integration tests auto-start Docker containers if needed.

### E2E Tests (`tests/e2e/`)

Full application behaviour tests.

- **Scope**: Complete user workflows
- **Speed**: 1-10s per test
- **Dependencies**: Full stack
- **Example**: Testing complete API flows

**Run e2e tests only:**

```bash
pytest tests/e2e/ -v
```

## Running Tests

**All tests:**

```bash
pytest tests/ -v
```

**Fast tests only (unit):**

```bash
pytest tests/unit/ -v
```

**With coverage:**

```bash
pytest tests/ --cov=hyperi_pylib --cov-report=html
```

**Specific test file:**

```bash
pytest tests/unit/test_config.py -v
```

**Specific test function:**

```bash
pytest tests/unit/test_config.py::TestSettings::test_get_setting -v
```

## Writing Tests

### Unit Test Example

```python
# tests/unit/test_mymodule.py
from hyperi_pylib.config import settings


def test_settings_get_with_default():
    """Test settings.get returns default for missing key."""
    result = settings.get("nonexistent.key", "default_value")
    assert result == "default_value"
```

### Integration Test Example

```python
# tests/integration/test_cache.py
import pytest
from hyperi_pylib.cache import PostgresCache


@pytest.mark.asyncio
async def test_cache_round_trip(postgres_dsn: str):
    """Test cache set and get with PostgreSQL."""
    cache = PostgresCache(dsn=postgres_dsn)
    await cache.init()

    try:
        await cache.set("test:key", {"data": "value"}, ttl_seconds=60)
        result = await cache.get("test:key")
        assert result == {"data": "value"}
    finally:
        await cache.close()
```

## CI Integration

Tests run automatically via CI script:

```bash
ci/scripts/local/build-local.sh
```

This runs the full validation pipeline including:

- ruff (lint + format check)
- pyright (type checking)
- pytest (all tests with coverage)

## Docker Services

Integration tests use Docker for external services:

| Service | Docker Compose File | Port |
|---------|---------------------|------|
| PostgreSQL | `docker-compose.postgres.yml` | 5432 |
| Kafka | `docker-compose.kafka.yml` | 9092 |

Fixtures in `conftest.py` auto-start containers when needed.
