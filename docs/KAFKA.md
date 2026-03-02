# Kafka Module Specification

HyperI Kafka client library specification for high-volume, batch-oriented message processing with at-least-once delivery guarantees.

## Design Principles

### 1. Batch-First Architecture

All consumption and production operations are batch-oriented. No single-message iteration patterns.

**Why batch?**

- Amortizes network round-trip latency across many messages
- Enables efficient compression (LZ4 on batches)
- Matches our 10K+ messages/batch, PB/day scale
- Reduces commit overhead (one commit per batch, not per message)
- Better memory efficiency with pre-allocated buffers

**Anti-pattern (DO NOT USE):**

```python
# WRONG - single message iteration
for msg in consumer:
    process(msg)
    consumer.commit()
```

**Correct pattern:**

```python
# RIGHT - batch processing
while True:
    messages = consumer.poll_batch(max_messages=10000, timeout_ms=1000)
    if messages:
        process_batch(messages)
        consumer.commit()
```

### 2. At-Least-Once Delivery

Messages may be delivered more than once but never lost. This requires:

**Producer side:**

- `acks=all` - Wait for all in-sync replicas to acknowledge
- `retries=5` - Retry on transient failures
- `enable.idempotence=false` - We accept duplicates for simplicity

**Consumer side:**

- `enable.auto.commit=false` - Manual commit only
- Commit AFTER successful processing
- On failure, messages will be redelivered

**Implication:** Consumers must be idempotent or handle duplicates.

### 3. Consumer Group Scaling

Design for horizontal scaling via consumer groups:

- Partitions = max parallelism
- One consumer per partition (ideal)
- Rebalancing handled automatically
- Session timeout = 45s (allow for slow processing)

---

## API Specification

### KafkaProducer

```python
class KafkaProducer:
    """Batch-oriented Kafka producer with at-least-once delivery."""

    def __init__(
        self,
        brokers: str | list[str],
        *,
        client_id: str = "hyperi-pylib",
        compression: str = "lz4",
        batch_size: int = 16384,
        linger_ms: int = 5,
        acks: str = "all",
        retries: int = 5,
        **extra_config
    ): ...

    def send(
        self,
        topic: str,
        value: bytes | str | dict,
        *,
        key: bytes | str | None = None,
        headers: dict[str, bytes] | None = None,
        partition: int | None = None,
    ) -> None:
        """Queue message for sending. Does not block."""
        ...

    def send_batch(
        self,
        topic: str,
        messages: list[dict],
    ) -> None:
        """Queue batch of messages. Each dict has 'value', optional 'key', 'headers'."""
        ...

    def flush(self, timeout_ms: int = 30000) -> int:
        """
        Block until all queued messages are delivered.
        Returns number of messages still in queue (0 = success).
        """
        ...

    def poll(self, timeout_ms: int = 0) -> None:
        """Trigger delivery callbacks. Call periodically for async sends."""
        ...
```

### KafkaConsumer

```python
class KafkaConsumer:
    """Batch-oriented Kafka consumer with manual commit."""

    def __init__(
        self,
        brokers: str | list[str],
        group_id: str,
        topics: list[str],
        *,
        auto_offset_reset: str = "earliest",
        session_timeout_ms: int = 45000,
        max_poll_interval_ms: int = 300000,
        fetch_max_bytes: int = 52428800,  # 50MB
        **extra_config
    ): ...

    def poll_batch(
        self,
        max_messages: int = 10000,
        timeout_ms: int = 1000,
    ) -> list[KafkaMessage]:
        """
        Poll for up to max_messages.
        Returns immediately if messages available, or after timeout_ms.
        """
        ...

    def commit(self, asynchronous: bool = False) -> None:
        """Commit offsets for all consumed messages."""
        ...

    def commit_message(self, message: KafkaMessage, asynchronous: bool = False) -> None:
        """Commit offset for specific message (and all before it in partition)."""
        ...

    def seek_to_beginning(self, topic: str, partition: int) -> None:
        """Seek to beginning of partition."""
        ...

    def seek_to_end(self, topic: str, partition: int) -> None:
        """Seek to end of partition."""
        ...

    def seek_to_timestamp(self, topic: str, partition: int, timestamp_ms: int) -> None:
        """Seek to first message at or after timestamp."""
        ...

    def assignment(self) -> list[tuple[str, int]]:
        """Get current partition assignments as (topic, partition) tuples."""
        ...

    def close(self) -> None:
        """Close consumer, commit offsets, leave group."""
        ...
```

### KafkaAdmin

```python
class KafkaAdmin:
    """Administrative operations for Kafka topics and consumer groups."""

    def __init__(
        self,
        brokers: str | list[str],
        **extra_config
    ): ...

    # --- Consumer Group Offset Management ---

    def reset_offsets_to_earliest(
        self,
        group_id: str,
        topic: str,
        partitions: list[int] | None = None,
    ) -> None:
        """Reset consumer group offsets to earliest (reprocess all)."""
        ...

    def reset_offsets_to_latest(
        self,
        group_id: str,
        topic: str,
        partitions: list[int] | None = None,
    ) -> None:
        """Reset consumer group offsets to latest (skip to end)."""
        ...

    def reset_offsets_to_timestamp(
        self,
        group_id: str,
        topic: str,
        timestamp_ms: int,
        partitions: list[int] | None = None,
    ) -> None:
        """Reset consumer group offsets to timestamp."""
        ...

    def get_consumer_lag(
        self,
        group_id: str,
        topic: str,
    ) -> dict[int, int]:
        """Get consumer lag per partition. Returns {partition: lag}."""
        ...

    # --- Topic Management ---

    def increase_partitions(
        self,
        topic: str,
        new_total: int,
    ) -> None:
        """Increase partition count (cannot decrease)."""
        ...

    def set_retention(
        self,
        topic: str,
        retention_ms: int,
    ) -> None:
        """Set message retention period."""
        ...

    def get_topic_config(
        self,
        topic: str,
    ) -> dict[str, str]:
        """Get topic configuration."""
        ...

    def list_topics(self) -> list[str]:
        """List all topics."""
        ...

    def describe_topic(
        self,
        topic: str,
    ) -> TopicInfo:
        """Get topic metadata including partition count, replication factor."""
        ...
```

### KafkaMetricsCollector

```python
class KafkaMetricsCollector:
    """Collect librdkafka statistics for observability."""

    def __init__(self, stats_interval_ms: int = 5000): ...

    def get_stats_callback(self) -> Callable[[str], None]:
        """Get callback function to pass to Kafka client config."""
        ...

    def get_metrics(self) -> KafkaMetrics:
        """Get current metrics snapshot."""
        ...

@dataclass
class KafkaMetrics:
    # Client-level
    messages_sent: int
    messages_received: int
    bytes_sent: int
    bytes_received: int

    # Per-broker
    brokers: dict[str, BrokerMetrics]

    # Per-partition (consumer)
    partitions: dict[tuple[str, int], PartitionMetrics]

    # Consumer group
    consumer_group_state: str | None
    rebalance_count: int

@dataclass
class BrokerMetrics:
    state: str  # "UP", "DOWN", "INIT"
    rtt_avg_ms: float
    rtt_p99_ms: float
    throttle_time_ms: int
    outbuf_cnt: int
    outbuf_msg_cnt: int

@dataclass
class PartitionMetrics:
    consumer_lag: int
    committed_offset: int
    stored_offset: int
    hi_offset: int  # high watermark
    lo_offset: int  # low watermark
    fetch_state: str  # "active", "stopped", etc.
```

---

## Configuration

### Corporate Defaults

These defaults are embedded and match across Python/Rust/Go:

**Producer:**

```python
PRODUCER_DEFAULTS = {
    "acks": "all",
    "retries": 5,
    "retry.backoff.ms": 100,
    "delivery.timeout.ms": 120000,
    "request.timeout.ms": 30000,
    "linger.ms": 5,
    "compression.type": "lz4",
    "batch.size": 16384,
}
```

**Consumer:**

```python
CONSUMER_DEFAULTS = {
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
    "session.timeout.ms": 45000,
    "heartbeat.interval.ms": 3000,
    "max.poll.interval.ms": 300000,
    "fetch.min.bytes": 1,
    "fetch.max.bytes": 52428800,
}
```

### Environment Variables

Bootstrap configuration from environment:

| Variable | Description |
|----------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | Comma-separated broker list |
| `KAFKA_GROUP_ID` | Consumer group ID |
| `KAFKA_SECURITY_PROTOCOL` | `plaintext`, `ssl`, `sasl_plaintext`, `sasl_ssl` |
| `KAFKA_SASL_MECHANISM` | `PLAIN`, `SCRAM-SHA-256`, `SCRAM-SHA-512` |
| `KAFKA_SASL_USERNAME` | SASL username |
| `KAFKA_SASL_PASSWORD` | SASL password |
| `KAFKA_SSL_CA_LOCATION` | CA certificate path |

---

## Usage Patterns

### High-Volume Consumer (DFE Pattern)

```python
from hyperi_pylib.kafka import KafkaConsumer, KafkaMetricsCollector

metrics = KafkaMetricsCollector()

consumer = KafkaConsumer(
    brokers="kafka:9092",
    group_id="dfe-loader",
    topics=["events"],
    stats_cb=metrics.get_stats_callback(),
)

while True:
    # Poll for up to 10K messages or 1 second
    batch = consumer.poll_batch(max_messages=10000, timeout_ms=1000)

    if batch:
        # Process entire batch
        process_batch(batch)

        # Commit AFTER successful processing (at-least-once)
        consumer.commit()

    # Export metrics periodically
    if should_export_metrics():
        stats = metrics.get_metrics()
        prometheus.set_gauge("kafka_consumer_lag", stats.total_lag)
```

### Batch Producer

```python
from hyperi_pylib.kafka import KafkaProducer

producer = KafkaProducer(
    brokers="kafka:9092",
    compression="lz4",
)

# Accumulate batch
batch = []
for event in generate_events():
    batch.append({"value": event, "key": event["id"]})

    if len(batch) >= 10000:
        producer.send_batch("events", batch)
        batch = []

# Send remaining
if batch:
    producer.send_batch("events", batch)

# Wait for delivery confirmation
remaining = producer.flush(timeout_ms=30000)
if remaining > 0:
    raise RuntimeError(f"{remaining} messages failed to deliver")
```

### Offset Reset for Reprocessing

```python
from hyperi_pylib.kafka import KafkaAdmin

admin = KafkaAdmin(brokers="kafka:9092")

# Stop consumers first, then:
admin.reset_offsets_to_timestamp(
    group_id="dfe-loader",
    topic="events",
    timestamp_ms=1704067200000,  # 2024-01-01 00:00:00 UTC
)

# Or reset to beginning:
admin.reset_offsets_to_earliest(
    group_id="dfe-loader",
    topic="events",
)
```

---

## Error Handling

### Producer Errors

```python
class KafkaProducerError(Exception):
    """Base producer error."""

class DeliveryFailedError(KafkaProducerError):
    """Message delivery failed after retries."""

class QueueFullError(KafkaProducerError):
    """Local queue full, apply backpressure."""
```

**Handling:**

```python
try:
    producer.flush()
except DeliveryFailedError as e:
    # Log and alert, messages may be lost
    logger.error(f"Delivery failed: {e}")
except QueueFullError:
    # Slow down production
    time.sleep(1)
```

### Consumer Errors

```python
class KafkaConsumerError(Exception):
    """Base consumer error."""
    error_code: int

class CommitFailedError(KafkaConsumerError):
    """Offset commit failed."""

class RebalanceError(KafkaConsumerError):
    """Consumer group rebalance in progress."""
```

**Handling:**

```python
try:
    batch = consumer.poll_batch()
    process(batch)
    consumer.commit()
except CommitFailedError:
    # Will be reprocessed on next poll (at-least-once)
    logger.warning("Commit failed, messages will be reprocessed")
except RebalanceError:
    # Partitions reassigned, discard batch
    logger.info("Rebalance occurred, discarding partial batch")
```

---

## Implementation Notes

### librdkafka Configuration

Both Python (confluent-kafka) and Rust (rdkafka) wrap librdkafka. Use identical defaults.

### Batch Size Tuning

| Scenario | `batch.size` | `linger.ms` | `max_messages` |
|----------|--------------|-------------|----------------|
| Low latency | 16384 | 0 | 100 |
| Balanced | 16384 | 5 | 1000 |
| High throughput | 65536 | 10 | 10000 |
| Max throughput | 131072 | 50 | 50000 |

### Memory Estimation

Per consumer:

- `fetch.max.bytes` (50MB default) = max memory per poll
- With 10K messages at 5KB each = 50MB buffer

Per producer:

- `queue.buffering.max.messages` (100K default) x avg message size
- With 5KB messages = 500MB max buffer

---

## Comparison: Rust vs Python

| Feature | Rust (transport-kafka) | Python (hyperi-pylib.kafka) |
|---------|------------------------|-------------------------|
| Consumer | `KafkaTransport::recv()` | `KafkaConsumer.poll_batch()` |
| Producer | `KafkaTransport::send()` | `KafkaProducer.send_batch()` |
| Commit | `KafkaTransport::commit()` | `KafkaConsumer.commit()` |
| Admin | `KafkaAdmin` (to add) | `KafkaAdmin` |
| Metrics | Stats callback (to add) | `KafkaMetricsCollector` |
| Defaults | `KafkaConfig::default()` | `PRODUCER_DEFAULTS`, `CONSUMER_DEFAULTS` |

Both implementations share:

- Same librdkafka defaults
- Batch-first design
- Manual commit (at-least-once)
- Same environment variable names
