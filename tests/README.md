# scalo Test Suite

Test organisation for scalo following standard testing patterns.

## Directory Structure

```
tests/
+-- conftest.py           # Shared pytest fixtures and configuration
+-- unit/                 # Unit tests (fast, isolated)
|   +-- test_config*.py   # Configuration tests
|   +-- test_kafka*.py    # Kafka tests
|   +-- test_logger*.py   # Logger tests
|   +-- test_*.py         # Other module tests
+-- integration/          # Integration tests (require services)
|   +-- test_kafka*.py    # Kafka integration (requires Docker)
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
- **Example**: Testing Kafka producer/consumer, secrets backends

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
pytest tests/ --cov=scalo --cov-report=html
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
from scalo.config import settings


def test_settings_get_with_default():
    """Test settings.get returns default for missing key."""
    result = settings.get("nonexistent.key", "default_value")
    assert result == "default_value"
```

### Integration Test Example

```python
# tests/integration/test_kafka.py
import pytest
from scalo.kafka import KafkaConsumer, KafkaProducer


@pytest.mark.integration
async def test_kafka_round_trip(kafka_brokers: str):
    """Produce a message and read it back via a real broker."""
    producer = KafkaProducer(brokers=kafka_brokers)
    await producer.send("test-topic", {"data": "value"})
    await producer.flush()

    consumer = KafkaConsumer(brokers=kafka_brokers, topics=["test-topic"])
    message = await consumer.poll(timeout=5.0)
    assert message.value == {"data": "value"}
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
