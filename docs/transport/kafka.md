# Kafka

`scalo.kafka` wraps the `confluent-kafka` Python client, which runs librdkafka, with corporate defaults, a simplified API, optional async wrappers, schema-sampling helpers, and a consumer-lag health probe that does not require JMX. Defaults are at-least-once (`acks=all`, `retries=5`, manual commit). librdkafka idempotence is **not** on by default, and the module adds no retry beyond librdkafka's `retries`.

What you get over raw librdkafka:

- Production defaults for durability, batching and manual commit
- One-arg construction from a bootstrap string, and `subscribe(str)` for a single topic (librdkafka needs a list)
- JSON / str / bytes serialisation in `producer.send()`
- A `Message` dataclass with `value_as_json()` / `value_as_str()` helpers
- `KafkaAdmin` for the ops admins do (partition resize, retention,
  cleanup policy, offset reset)
- `AsyncKafka*` wrappers for asyncio call sites
- `SchemaAnalyser` + sampling utilities for "what's in this topic?"
- `KafkaConsumerHealth` watching lag / rebalances / broker state via
  `stats_cb`

## Sync clients

### KafkaProducer

```python
from scalo.kafka import KafkaProducer

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

- `send(topic, value, key=None, partition=None, headers=None, on_delivery=None)` -- single message. `value` is `str`/`bytes`/`dict`/`list`, and a dict or list goes through `json.dumps`. Calls `produce()` then `poll(0)` to drain callbacks.
- `flush(timeout=None)` -- block until the queue drains, and return the count of messages still queued.
- `poll(timeout=0)` -- trigger delivery callbacks.

No `send_batch()` -- librdkafka batches via `linger.ms` and
`batch.size`. Send many by calling `send()` in a loop then `flush()`
once at the end. `on_delivery=(err, msg)` callback fires from `poll()`
-- ignore for fire-and-forget, inspect `err` for at-least-once logic.

### KafkaConsumer

Two ways to drive it -- subscribe (consumer-group rebalance) or
assign (manual partitions). Auto-commit is **off**, you commit
explicitly.

```python
from scalo.kafka import KafkaConsumer

with KafkaConsumer("localhost:9092", group_id="my-service") as consumer:
    consumer.subscribe("events")           # or ["events", "audit"]
    for msg in consumer:                   # iterator calls .poll(1.0) forever
        process(msg.value_as_json())
        consumer.commit()                  # commits ALL current offsets
```

| Group | Methods |
|-------|---------|
| Polling | `poll(timeout=1.0) -> Message\|None` returns one message, or `None` on timeout or partition EOF, and raises `KafkaConsumerError` on any other error. `consume(num_messages=1, timeout=1.0) -> list[Message]` returns a batch and skips EOF silently. `__iter__` / `__next__` blocks indefinitely with 1s polls until `close()` or `break`. |
| Subscription | `subscribe(str\|list[str])`, `unsubscribe()`, `assign(topic, partitions)`, `assignment()`. |
| Offsets | `commit(asynchronous=False)` commits **all** current offsets -- no `commit_message(msg)`. `committed(topic, partitions)`, `seek(topic, partition, offset)`, `seek_to_beginning/end(topic, partition)`, `position(topic, partition)`. |

`commit()` covers the messages `poll` and `consume` have handed over and no others: the consumer sets `enable.auto.offset.store` false and stores each partition's next offset itself as it returns messages. A `consume` batch with an error raises `KafkaConsumerError` and returns none of its messages, and each partition it read is sought back to its first message in the batch, so the next read returns them again.

A seek that fails raises `KafkaConsumerError` saying the rewind failed, and the partitions it did not reach are left past the batch. Close that consumer and start another, which resumes from the committed offsets, before anything commits again. A config that sets `enable.auto.offset.store` keeps librdkafka's store, which stores every message librdkafka returns, and then a commit after a batch error skips that batch. `AsyncKafkaConsumer` behaves the same.

For seek-by-timestamp use `KafkaAdmin.reset_offsets_to_timestamp()` or `KafkaAdmin.reset_offsets_to_time()` -- there is no `seek_to_timestamp()` on the consumer. `KafkaConsumerError` has librdkafka's `.error_code`.

### KafkaClient and KafkaAdmin

Two admin classes with different scopes. `KafkaClient` reads: it lists and describes topics, and reads watermarks, consumer-group lag and offsets for times. `KafkaAdmin` changes things: it increases partitions, sets retention and cleanup policy, alters config, and resets consumer-group offsets to the earliest, the latest, a timestamp or a datetime.

```python
from scalo.kafka import KafkaAdmin
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
`KafkaAdminError` wraps the exception of a failed admin future.

## Async clients

`AsyncKafkaProducer`, `AsyncKafkaConsumer` and `AsyncKafkaClient` are thin wrappers that run each blocking librdkafka call in a worker thread through `scalo.concurrency.run_blocking` (see [../api/concurrency.md](../api/concurrency.md)). `__aexit__` flushes the producer and closes the consumer and the client. `AsyncKafkaProducer.send()` is fire-and-forget, and `send_and_wait()` returns a `DeliveryReport` once the broker acknowledges.

```python
from scalo.kafka import AsyncKafkaProducer, AsyncKafkaConsumer

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
| Throughput-bound consumer loop | Event loop running |
| `confluent-kafka` is your one blocking call | Mixing with `httpx.AsyncClient`, asyncpg, etc. |
| You want one fewer thread | Per-request produce inside an async handler |

Async wrappers are *not* faster than sync -- they exist to let you
call Kafka from an event loop without blocking it. `AsyncKafkaClient`
covers `list_topics`, `describe_topic`, `get_watermark_offsets`,
`get_topic_message_count`. It does **not** expose `get_consumer_lag` or `get_offsets_for_times`. Use the sync `KafkaClient`, through `run_blocking`, for those.

## Configuration

Two layers stack: corporate defaults from `kafka.config`, then your user config (user wins). `merge_config(user, defaults, verify_ssl=True)` does the overlay, and `verify_ssl=False` sets `enable.ssl.certificate.verification` to `"false"`.

librdkafka accepts some settings under two names, and scalo-py knows the same ten pairs as scalo-rs: `bootstrap.servers`/`metadata.broker.list`, `max.in.flight`/`max.in.flight.requests.per.connection`, `sasl.mechanism`/`sasl.mechanisms`, the `sasl.oauthbearer.client.credentials.client.id` and `.client.secret` pairs with their short forms, `max.partition.fetch.bytes`/`fetch.message.max.bytes`, `linger.ms`/`queue.buffering.max.ms`, `retries`/`message.send.max.retries`, `compression.type`/`compression.codec` and `acks`/`request.required.acks`. A user setting under either name replaces the default under the other, so your value alone reaches librdkafka. The codec name is matched without regard to case.

### Producer defaults (`PRODUCER_DEFAULTS`)

| Key | Value | Why |
|-----|-------|-----|
| `acks` | `"all"` | Wait for all in-sync replicas -- durability. |
| `retries` | `5` | librdkafka retries transient errors. |
| `retry.backoff.ms` | `100` | Backoff between retries. |
| `delivery.timeout.ms` | `120000` | 2-minute upper bound on delivery. |
| `request.timeout.ms` | `30000` | Per-request timeout. |
| `linger.ms` | `5` | Small wait to batch. |
| `compression.type` | `"zstd"` | Corporate default codec. |
| `compression.level` | `3` | zstd tuning. `merge_config` drops it when you override the codec without setting a level. |
| `batch.size` | `16384` | 16 KiB batches. |

`enable.idempotence` is **not** set by the defaults. Opt in when a retried send must not write a duplicate:

```python
producer = KafkaProducer({
    "bootstrap.servers": "localhost:9092",
    "enable.idempotence": True,
})
```

A retry around a whole call is yours to add, for example with `stamina`, which the `resilience` extra installs.

### Consumer defaults (`CONSUMER_DEFAULTS`)

| Key | Value | Why |
|-----|-------|-----|
| `auto.offset.reset` | `"earliest"` | A group with no committed offset starts at the beginning. |
| `enable.auto.commit` | `False` | Manual commit -- at-least-once. |
| `session.timeout.ms` | `45000` | Tolerates 45s of pause before kicked out. |
| `heartbeat.interval.ms` | `3000` | Heartbeat every 3s, well inside the session timeout. |
| `max.poll.interval.ms` | `300000` | Up to 5 minutes between polls before the consumer leaves the group. |
| `fetch.min.bytes` | `1` | Return immediately with whatever arrives. |
| `fetch.wait.max.ms` | `500` | Cap on the wait. |

### Admin defaults (`ADMIN_DEFAULTS`)

`ADMIN_DEFAULTS` sets `request.timeout.ms: 30000`. Every blocking metadata, watermark, committed-offset and offsets-for-times call in `KafkaClient`, `AsyncKafkaClient`, `ReadOnlyKafkaClient` and `KafkaConsumer` waits at most the config's `socket.timeout.ms`, or 30 s where it is unset. `KafkaAdmin` bounds the same calls by each method's `timeout` argument. A call that gets no broker answer in time raises `KafkaTimeoutError`, a `TimeoutError` naming the call. A per-partition read makes one call per partition, so `describe_topic` on 12 partitions can wait up to 13 bounds. A `socket.timeout.ms` that is not a positive number fails the client's constructor with `ValueError`.

### Loading from elsewhere

| Helper | Source |
|--------|--------|
| `config_from_env(prefix="KAFKA_")` | `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SASL_USERNAME`, etc. Maps to librdkafka keys. |
| `config_from_file(path)` | `.properties` / `.json` / `.yaml` / `.yml` / `.ini` (the `[kafka]` section). |
| `external_sasl_scram(brokers, user, pw)` | SASL_SSL + SCRAM-SHA-512 (production-facing brokers). |
| `internal_sasl_scram(brokers, user, pw)` | SASL_PLAINTEXT + SCRAM-SHA-512 (in-cluster, TLS-terminated upstream). |
| `get_default_config()` | `config_from_env()` + `ADMIN_DEFAULTS`. |

`scalo.kafka.providers.provider_config(provider, brokers, user, pw)` derives the protocol and mechanism from a provider key, so neither is hand-set:

| Provider | `security.protocol` | `sasl.mechanisms` |
|---|---|---|
| `strimzi`, `redpanda`, `msk`, `redpanda-cloud` | `SASL_SSL` | `SCRAM-SHA-512` |
| `strimzi-no-tls`, `redpanda-no-tls` | `SASL_PLAINTEXT` | `SCRAM-SHA-512` |
| `confluent-cloud` | `SASL_SSL` | `PLAIN` |
| `msk_iam` | `SASL_SSL` | `OAUTHBEARER` |
| `plaintext` | `PLAINTEXT` | none |

A `-no-tls` key names a self-hosted broker's TLS-off listener. SCRAM alone gets one, because its challenge-response never sends the password. `scalo.kafka.contract.DEFAULT_ALLOWED` leaves both out.

Headers hold whatever you pass to `producer.send(headers=...)`. The
kafka module does **not** inject W3C `traceparent` or any identity
headers automatically. For cross-service trace context,
populate `headers` from the active OTel span yourself.

## Internal consumer groups and broker ACLs

librdkafka will not build a consumer without a `group.id`, and a consumer asks the broker for its group's coordinator as soon as it connects, whether or not it ever subscribes. A broker that grants groups by prefix rejects that lookup for any group outside the prefix, and logs it as `GroupAuthorizationFailed`. So the consumer each read client builds for its offset queries takes a group id derived from the config you pass, never a fixed literal:

| Client | Methods that build the offset-query consumer | Group id | Joins or commits |
|---|---|---|---|
| `KafkaClient` | `describe_topic`, `get_watermark_offsets`, `get_topic_message_count`, `get_offsets_for_times` | `<group.id>-admin`, or `<client.id>-admin` when `group.id` is unset or empty | Never |
| `AsyncKafkaClient` | `describe_topic`, `get_watermark_offsets`, `get_topic_message_count` | as above | Never |
| `ReadOnlyKafkaClient` | `describe_topic`, `get_watermark_offsets`, `get_topic_message_count` | as above | Never |

A client given `group.id: orders-api` gets `orders-api-admin`, and one given `client.id: orders-api` alone gets the same, both inside an `orders-` grant. With neither set the anchor is `scalo`, and `scalo-admin` sits outside any app prefix, so set one of the two on a client that talks to a broker enforcing group ACLs. The anchor order and the `-admin` suffix match scalo-rs's `KafkaAdmin`.

The group you pass to `get_consumer_lag` or a `KafkaAdmin` offset reset is used as given, so the grant has to cover it as well. The lag read fetches that group's committed offsets, and the resets commit to it. librdkafka keeps retrying a refused coordinator lookup, so a group outside the grant ends a lag read in `KafkaTimeoutError`. A topic the credentials may not describe raises `KafkaException` carrying `TOPIC_AUTHORIZATION_FAILED`, never an empty answer.

## Schema sampling

For "what's in this topic?" discovery -- inferring a JSON schema and
field statistics from a sample of messages.

```python
from scalo.kafka import (
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
| `time_bounded_consume(consumer, start_time, end_time, limit=None, timeout=1.0)` | Poll until 3 consecutive empty polls, a message past `end_time`, or `limit` messages. Collects the messages with timestamps in `[start_time, end_time]` (both millis since epoch). Consumer must be subscribed or assigned first. |

`time_bounded_consume()` reads messages but does **not** seek -- pair
with `consumer.seek()` or `KafkaAdmin.reset_offsets_to_timestamp()`
first if you want the read to start at a specific point in time.

## Consumer-lag health

`KafkaConsumerHealth` watches librdkafka stats (via `stats_cb`) for
the issues that cause production pain: no partitions assigned,
insufficient partitions, frequent rebalances, lag growing, high lag,
partition imbalance, broker disconnects, fetch errors. Warnings are
rate-limited (default 60s) so a stuck consumer does not flood logs.

```python
from scalo.kafka import (
    KafkaConsumerHealth, KafkaMetricsCollector, create_stats_callback,
)
from scalo.health import HealthManager

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
| `imbalance_ratio` | 3.0 | This consumer's largest per-topic partition count over its smallest, across two or more topics. Imbalance across consumers is not visible from one consumer. |

`get_health_metrics()` returns a dict keyed by Prometheus-style metric names
(`kafka_consumer_healthy`, `kafka_consumer_lag_total`,
`kafka_consumer_rebalance_total`, plus per-`HealthIssue` counters) --
feed into the metrics pillar via a custom collector for `/metrics`.

## Read-only client (for tools)

`ReadOnlyKafkaClient` reads topics, watermarks, message counts and consumer lag, and has no method that writes. Use it for a metrics scraper or monitoring tool that holds credentials with write access.

```python
from scalo.kafka import ReadOnlyKafkaClient, config_from_env

with ReadOnlyKafkaClient(config_from_env()) as client:
    for topic in client.list_topics():
        count = client.get_topic_message_count(topic.name)
        lag = client.get_consumer_lag("my-group", topic.name)
        print(topic.name, count, sum(lag.values()))
```

Methods available: `list_topics`, `describe_topic`,
`get_watermark_offsets`, `get_topic_message_count`,
`get_consumer_lag`. No `send`, no `alter_config`, no offset reset.
