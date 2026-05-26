# Kafka

`hyperi_pylib.kafka` wraps the `confluent-kafka` Python client (librdkafka
under the hood) with corporate defaults, a simplified API, optional async
wrappers, schema-sampling helpers, and a consumer-lag health probe that
does not require JMX. Defaults are at-least-once
(`acks=all`, `retries=5`, manual commit); librdkafka idempotence is
**not** enabled by default, and application-level retry is layered with
`stamina` at the call site rather than via librdkafka transactions.

What you get over raw librdkafka:

- Sensible production defaults (durability, batching, manual commit)
- One-arg construction from a bootstrap string
- JSON / str / bytes serialisation in `producer.send()`
- A `Message` dataclass with `value_as_json()` / `value_as_str()` helpers
- `subscribe(str)` accepts a single topic (librdkafka requires a list)
- `KafkaAdmin` for the ops admins do (partition resize, retention,
  cleanup policy, offset reset)
- `AsyncKafka*` wrappers for asyncio call sites
- `SchemaAnalyser` + sampling utilities for "what's in this topic?"
- `KafkaConsumerHealth` watching lag / rebalances / broker state via
  `stats_cb`

---

## Sync clients

### KafkaProducer

```python
from hyperi_pylib.kafka import KafkaProducer

with KafkaProducer("localhost:9092") as producer:
    producer.send("events", value={"event": "user_created", "user_id": 123})
    producer.send("events", value="plain text", key="user-123")
    producer.send(
        "events",
        value=b"already-bytes",
        partition=2,
        headers={"trace-id": "abc-123"},
    )
# context-manager exit calls .flush() with no timeout (blocks until drained)
```

API surface (the whole thing):

- `send(topic, value, key=None, partition=None, headers=None, on_delivery=None)` -- single message. `value` is `str`/`bytes`/`dict`/`list`; dict/list get `json.dumps`'d. Calls `produce()` then `poll(0)` to drain callbacks.
- `flush(timeout=None)` -- block until queue drains; returns messages still queued.
- `poll(timeout=0)` -- trigger delivery callbacks.

No `send_batch()` -- librdkafka already batches via `linger.ms` and
`batch.size`. Send many by calling `send()` in a loop then `flush()`
once at the end. `on_delivery=(err, msg)` callback fires from `poll()`
-- ignore for fire-and-forget, inspect `err` for at-least-once logic.

### KafkaConsumer

Two ways to drive it -- subscribe (consumer-group rebalance) or
assign (manual partitions). Auto-commit is **off**, you commit
explicitly.

```python
from hyperi_pylib.kafka import KafkaConsumer

with KafkaConsumer("localhost:9092", group_id="my-service") as consumer:
    consumer.subscribe("events")           # or ["events", "audit"]
    for msg in consumer:                   # iterator calls .poll(1.0) forever
        process(msg.value_as_json())
        consumer.commit()                  # commits ALL current offsets
```

| Group | Methods |
|-------|---------|
| Polling | `poll(timeout=1.0) -> Message\|None` (single message; `None` on timeout or partition EOF; raises `KafkaConsumerError` on fatal). `consume(num_messages=1, timeout=1.0) -> list[Message]` (batch; skips EOF silently). `__iter__` / `__next__` blocks indefinitely with 1s polls until `close()` or `break`. |
| Subscription | `subscribe(str\|list[str])`, `unsubscribe()`, `assign(topic, partitions)`, `assignment()`. |
| Offsets | `commit(asynchronous=False)` commits **all** current offsets -- no `commit_message(msg)`. `committed(topic, partitions)`, `seek(topic, partition, offset)`, `seek_to_beginning/end(topic, partition)`, `position(topic, partition)`. |

For seek-by-timestamp use `KafkaAdmin.reset_offsets_to_timestamp()` or
`KafkaAdmin.reset_offsets_to_time()` -- there is no `seek_to_timestamp()`
on the consumer. `KafkaConsumerError` carries `.error_code` from
librdkafka when fatal.

### KafkaClient and KafkaAdmin

Two admin classes with different scopes:

- **`KafkaClient`** -- read-mostly: list/describe topics, watermarks,
  consumer-group lag, offsets-for-times.
- **`KafkaAdmin`** -- mutating ops: increase partitions, retention,
  cleanup policy, alter config, reset consumer-group offsets
  (earliest / latest / timestamp / datetime).

```python
from hyperi_pylib.kafka import KafkaAdmin
from datetime import datetime, timezone

admin = KafkaAdmin("localhost:9092")
admin.increase_partitions("events", new_total_count=12)
admin.set_retention("events", days=7)
admin.set_cleanup_policy("events", "compact,delete")

admin.reset_offsets_to_earliest("my-group", "events")
admin.reset_offsets_to_time(
    "my-group", "events",
    datetime(2026, 1, 1, tzinfo=timezone.utc),
)
```

`alter_config()` uses `incremental_alter_configs` so unspecified keys
keep their current values rather than reverting to broker defaults.
`KafkaAdminError` wraps the underlying futures. `seek_to_json_match()`
(offset seek by JSON field value) is on the backlog in `admin.py`, not
implemented.

---

## Async clients

`AsyncKafkaProducer`, `AsyncKafkaConsumer`, `AsyncKafkaClient` are thin
wrappers that push blocking librdkafka calls into a `ThreadPoolExecutor`
(4 workers by default; pass `executor=...` to share). They own the
executor unless one is supplied, shutting it down on `__aexit__`.

```python
from hyperi_pylib.kafka import AsyncKafkaProducer, AsyncKafkaConsumer

async with AsyncKafkaProducer("localhost:9092") as producer:
    await producer.send("events", {"event": "x"})
    await producer.flush()

async with AsyncKafkaConsumer("localhost:9092", "my-group") as consumer:
    consumer.subscribe("events")           # subscribe stays sync (fast)
    async for msg in consumer:
        await handle(msg.value_as_json())
        await consumer.commit()
```

Which one to pick:

| Use sync when | Use async when |
|---------------|----------------|
| CLI, batch job, scheduled worker | FastAPI / Starlette handlers |
| Throughput-bound consumer loop | Event loop already running |
| `confluent-kafka` is your only blocking call | Mixing with `httpx.AsyncClient`, asyncpg, etc. |
| You want one fewer thread | Per-request produce inside an async handler |

Async wrappers are *not* faster than sync -- they exist to let you
call Kafka from an event loop without blocking it. `AsyncKafkaClient`
covers `list_topics`, `describe_topic`, `get_watermark_offsets`,
`get_topic_message_count`. It does **not** expose `get_consumer_lag`
or `get_offsets_for_times`; use the sync `KafkaClient` (or
`run_in_executor`) for those.

---

## Configuration

Two layers stack: corporate defaults from `kafka.config`, then your
user config (user wins). `merge_config(user, defaults)` does the
overlay; `verify_ssl=False` flips
`enable.ssl.certificate.verification` to `"false"`.

### Producer defaults (`PRODUCER_DEFAULTS`)

| Key | Value | Why |
|-----|-------|-----|
| `acks` | `"all"` | Wait for all in-sync replicas -- durability. |
| `retries` | `5` | librdkafka retries transient errors. |
| `retry.backoff.ms` | `100` | Backoff between retries. |
| `delivery.timeout.ms` | `120000` | 2-minute upper bound on delivery. |
| `request.timeout.ms` | `30000` | Per-request timeout. |
| `linger.ms` | `5` | Small wait to batch. |
| `compression.type` | `"lz4"` | Fast compression. |
| `batch.size` | `16384` | 16 KiB batches. |

`enable.idempotence` is **not** set by the defaults. Opt in explicitly
if you need exactly-once produce semantics:

```python
producer = KafkaProducer({
    "bootstrap.servers": "localhost:9092",
    "enable.idempotence": True,
})
```

Application-level retry around Kafka calls is layered with `stamina` at
the call site, not via librdkafka transactions.

### Consumer defaults (`CONSUMER_DEFAULTS`)

| Key | Value | Why |
|-----|-------|-----|
| `auto.offset.reset` | `"earliest"` | New groups start at the beginning. |
| `enable.auto.commit` | `False` | Manual commit -- at-least-once. |
| `session.timeout.ms` | `45000` | Tolerates 45s of pause before kicked out. |
| `heartbeat.interval.ms` | `3000` | 1/3 of session timeout. |
| `max.poll.interval.ms` | `300000` | 5-minute processing budget per batch. |
| `fetch.min.bytes` | `1` | Return immediately with whatever arrives. |
| `fetch.wait.max.ms` | `500` | Cap on the wait. |

### Admin defaults (`ADMIN_DEFAULTS`)

- `request.timeout.ms: 30000`

### Loading from elsewhere

| Helper | Source |
|--------|--------|
| `config_from_env(prefix="KAFKA_")` | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SASL_USERNAME`, etc. Maps to librdkafka keys. |
| `config_from_file(path)` | `.properties` / `.json` / `.yaml` / `.ini` (PyYAML required for YAML). |
| `external_sasl_scram(brokers, user, pw)` | SASL_SSL + SCRAM-SHA-512 (production-facing brokers). |
| `internal_sasl_scram(brokers, user, pw)` | SASL_PLAINTEXT + SCRAM-SHA-512 (in-cluster, TLS-terminated upstream). |
| `get_default_config()` | `config_from_env()` + `ADMIN_DEFAULTS`. |

### Identity propagation

Headers carry whatever you pass to `producer.send(headers=...)`. The
kafka module does **not** inject W3C `traceparent` or any HyperI
identity headers automatically. For cross-service trace context,
populate `headers` from the active OTel span yourself.

---

## Schema sampling

For "what's in this topic?" discovery -- inferring a JSON schema and
field statistics from a sample of messages.

```python
from hyperi_pylib.kafka import (
    KafkaConsumer, SchemaAnalyser,
    partition_sample, time_bounded_consume, reservoir_sample,
)

analyser = SchemaAnalyser()

with KafkaConsumer("localhost:9092", "schema-sample") as consumer:
    consumer.subscribe("events")
    for msg in consumer.consume(num_messages=1000, timeout=5.0):
        analyser.add_message(msg)

result = analyser.analyse()
print(result.schema)               # GenSON-merged JSON Schema
print(result.field_stats)          # per-field types, null_count, samples
print(result.total_messages, result.skipped_messages)
```

`SchemaAnalyser` uses GenSON to merge schemas across the sample and
tracks per-field stats (types seen, null count, up to 5 sample values,
occurrence count). Non-JSON messages count as `skipped`, not raised.
Nested objects recurse with dotted field names.

Sampling helpers:

| Function | Use case |
|----------|----------|
| `reservoir_sample(messages, k, seed=None)` | Uniform random `k` from a stream of unknown length (Vitter's Algorithm R). |
| `partition_sample(messages, n_per_partition, seed=None)` | Independent reservoir per partition -- representative across partitions. |
| `time_bounded_consume(consumer, start_ms, end_ms, limit=None, timeout=1.0)` | Poll until 3 consecutive empty polls or `end_ms` passes; only collects messages in `[start_ms, end_ms]`. Consumer must already be subscribed/assigned. |

`time_bounded_consume()` reads messages but does **not** seek -- pair
with `consumer.seek()` or `KafkaAdmin.reset_offsets_to_timestamp()`
first if you want the read to start at a specific point in time.

---

## Consumer-lag health

`KafkaConsumerHealth` watches librdkafka stats (via `stats_cb`) for
the issues that cause production pain: no partitions assigned,
insufficient partitions, frequent rebalances, lag growing, high lag,
partition imbalance, broker disconnects, fetch errors. Warnings are
rate-limited (default 60s) so a stuck consumer does not flood logs.

```python
from hyperi_pylib.kafka import (
    KafkaConsumerHealth, KafkaMetricsCollector, create_stats_callback,
)
from hyperi_pylib.health import HealthManager

collector = KafkaMetricsCollector()
kafka_health = KafkaConsumerHealth.from_config(collector, consumer_count=3)

consumer_config = {
    "bootstrap.servers": "localhost:9092",
    "group.id": "my-service",
    "statistics.interval.ms": 5000,
    "stats_cb": create_stats_callback(collector),
}

# Wire into the pillar HealthManager as a readiness check
health_manager = HealthManager()
async def kafka_ok() -> bool:
    issues = kafka_health.check_health()
    return not any(i.severity == "critical" for i in issues)

health_manager.register_ready_check("kafka", kafka_ok)
```

Thresholds come from the config cascade (`kafka.health.*` in
`settings.yaml`, or `KAFKA_HEALTH_*` env vars):

| Key | Default | Meaning |
|-----|---------|---------|
| `warning_rate_limit_sec` | 60 | Seconds between identical warnings. |
| `lag_threshold` | 10000 | Per-partition lag flagged as `HIGH_LAG`. |
| `lag_growth_threshold` | 1000 | Lag-delta per check flagged as `LAG_GROWING`. |
| `rebalance_threshold` | 3 | Rebalances in window before flagging `FREQUENT_REBALANCES`. |
| `rebalance_window_sec` | 300 | Window for the rebalance count. |
| `imbalance_ratio` | 3.0 | Per-consumer partition load relative to fair share. |

`get_health_metrics()` returns Prometheus-shaped values
(`kafka_consumer_healthy`, `kafka_consumer_lag_total`,
`kafka_consumer_rebalance_total`, plus per-`HealthIssue` counters) --
feed into the metrics pillar via a custom collector for `/metrics`.

---

## Read-only client (for tools)

`ReadOnlyKafkaClient` is `KafkaClient` minus the produce path -- same
admin / lag / watermark methods, no way to write. Useful when a
metrics scraper or monitoring tool runs with admin credentials and you
want a hard guarantee it cannot mutate data.

```python
from hyperi_pylib.kafka import ReadOnlyKafkaClient, config_from_env

with ReadOnlyKafkaClient(config_from_env()) as client:
    for topic in client.list_topics():
        count = client.get_topic_message_count(topic.name)
        lag = client.get_consumer_lag("my-group", topic.name)
        print(topic.name, count, sum(lag.values()))
```

Methods available: `list_topics`, `describe_topic`,
`get_watermark_offsets`, `get_topic_message_count`,
`get_consumer_lag`. No `send`, no `alter_config`, no offset reset.

---

## Related

- [../README.md](../README.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../core-pillars/HEALTH.md](../core-pillars/HEALTH.md)
- [../core-pillars/METRICS.md](../core-pillars/METRICS.md)
- [../api/RESILIENCE.md](../api/RESILIENCE.md)
- [../api/CONCURRENCY.md](../api/CONCURRENCY.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
