# Kafka Producer/Consumer Example

Demonstrates hyperi-pylib's Kafka client library with corporate defaults.

## Features

- Sync and async producer/consumer interfaces
- Corporate defaults for reliability and performance
- Consumer group lag monitoring (no JMX required)
- Schema analysis for JSON messages
- Health monitoring

## Quick Start

```bash
# Start Kafka
docker compose up -d

# Install dependencies
uv sync

# Run the producer
uv run python producer.py

# Run the consumer (in another terminal)
uv run python consumer.py

# Run tests
uv run pytest

# Clean up
docker compose down -v
```

## Components

### Producer (`producer.py`)

```python
from hyperi_pylib.kafka import KafkaProducer

producer = KafkaProducer({"bootstrap.servers": "localhost:9092"})
producer.produce("my-topic", key="key1", value={"event": "created"})
producer.flush()
```

### Consumer (`consumer.py`)

```python
from hyperi_pylib.kafka import KafkaConsumer

consumer = KafkaConsumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "my-consumer-group",
})
consumer.subscribe(["my-topic"])

for message in consumer:
    print(f"Received: {message.value}")
```

### Admin Client

```python
from hyperi_pylib.kafka import KafkaClient

client = KafkaClient({"bootstrap.servers": "localhost:9092"})
topics = client.list_topics()
```

## Corporate Defaults

The hyperi-pylib Kafka clients include production-ready defaults:

**Producer:**
- `acks=all` - Wait for all replicas
- `retries=5` - Automatic retry on failure
- `linger.ms=5` - Batch for efficiency

**Consumer:**
- `auto.offset.reset=earliest` - Start from beginning
- `enable.auto.commit=false` - Manual commit for reliability

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | localhost:9092 |
| `KAFKA_SECURITY_PROTOCOL` | Security protocol | PLAINTEXT |

## Docker Compose

The included `docker-compose.yml` starts Kafka in KRaft mode (no Zookeeper):

```yaml
services:
  kafka:
    image: apache/kafka:3.9.0
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      # ... KRaft configuration
    ports:
      - "9092:9092"
```

## See Also

- [hyperi-pylib Kafka Documentation](../../src/hyperi_pylib/kafka/__init__.py)
- [Kafka Client Tests](../../tests/integration/test_kafka_*.py)
