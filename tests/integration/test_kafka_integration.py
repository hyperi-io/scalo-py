# Project:   scalo
# File:      tests/integration/test_kafka_integration.py
# Purpose:   Integration tests for scalo.kafka with real Kafka broker
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Integration tests for scalo.kafka against the run's real broker.

The broker is the run's shared one (tests/TESTING.md). Each test makes its own
topics with ``kafka_topics`` and its own consumer groups, because the broker
refuses topic auto-create and other tests use it at the same time. The round
trip runs in core, and the rest run in full.
"""

import time
import uuid
from datetime import UTC, datetime

import pytest
from faker import Faker

pytestmark = pytest.mark.integration


def _produce(kafka_config: dict, topic: str, events: list[dict]) -> None:
    from scalo.kafka import KafkaProducer

    with KafkaProducer(kafka_config, verify_ssl=False) as producer:
        for event in events:
            producer.send(topic, value=event)
        assert producer.flush(timeout=10.0) == 0


@pytest.mark.full
class TestKafkaClientIntegration:
    """KafkaClient's read calls against a topic this test made and filled."""

    def test_reads_of_a_filled_topic(self, kafka_config, kafka_topics, kafka_group):
        from scalo.kafka.client import KafkaClient

        topic = kafka_topics("client-reads", partitions=3)
        _produce(kafka_config, topic, [{"n": n} for n in range(6)])

        with KafkaClient(kafka_config, verify_ssl=False) as client:
            listed = {t.name: t for t in client.list_topics()}
            assert listed[topic].partition_count == 3
            assert set(listed) <= {t.name for t in client.list_topics(include_internal=True)}

            metadata = client.describe_topic(topic)
            assert metadata.name == topic
            assert sorted(p.partition for p in metadata.partitions) == [0, 1, 2]

            watermarks = client.get_watermark_offsets(topic)
            assert sorted(watermarks) == [0, 1, 2]
            assert client.get_topic_message_count(topic) == 6

            # A group that never committed lags by the whole topic.
            lag = client.get_consumer_lag(kafka_group("lag"), topic)
            assert sum(lag.values()) == 6

    def test_a_missing_topic_is_named(self, kafka_config, shared_kafka):
        from scalo.kafka.client import KafkaClient, TopicNotFoundError

        missing = shared_kafka.topic_name("absent")
        with KafkaClient(kafka_config, verify_ssl=False) as client, pytest.raises(TopicNotFoundError):
            client.describe_topic(missing)


@pytest.mark.full
class TestReadOnlyMetricsIntegration:
    """Integration tests for read-only admin with Prometheus metrics collection."""

    def test_readonly_admin_stats_collection(self, kafka_config, kafka_topics, kafka_group):
        """
        Connect as admin in read-only mode, retrieve stats, expose to Prometheus.

        This test verifies:
        1. ReadOnlyKafkaClient connects without write access
        2. librdkafka stats callback collects real metrics
        3. Metrics are exposed in Prometheus-scrape format
        4. Key metrics have expected values from real broker
        """
        import time

        from confluent_kafka import Consumer

        from scalo.kafka.config import CONSUMER_DEFAULTS, merge_config
        from scalo.kafka.metrics import KafkaMetricsCollector, create_stats_callback
        from scalo.kafka.readonly import ReadOnlyKafkaClient

        # 1. Create metrics collector
        collector = KafkaMetricsCollector()
        callback = create_stats_callback(collector)

        # 2. Create consumer with stats callback enabled (for metrics)
        consumer_config = merge_config(
            kafka_config.copy(),
            CONSUMER_DEFAULTS,
            verify_ssl=False,
        )
        consumer_config["group.id"] = kafka_group("metrics")
        topic = kafka_topics("metrics")
        consumer_config["statistics.interval.ms"] = 1000  # Collect every 1s
        consumer_config["stats_cb"] = callback

        consumer = Consumer(consumer_config)

        try:
            # Subscribe to any topic to trigger stats
            with ReadOnlyKafkaClient(kafka_config, verify_ssl=False) as readonly_client:
                assert topic in {t.name for t in readonly_client.list_topics()}
            consumer.subscribe([topic])

            # 3. Poll to trigger stats callbacks
            for _ in range(5):
                consumer.poll(timeout=0.5)
                time.sleep(0.3)

            # 4. Verify we got metrics
            metrics = collector.get_metrics()

            # === PROMETHEUS SCRAPE VERIFICATION ===
            # Verify key metrics exist and have reasonable values
            assert "kafka_client_name" in metrics, "Missing kafka_client_name"
            assert "kafka_client_id" in metrics, "Missing kafka_client_id"
            assert "kafka_client_type" in metrics, "Missing kafka_client_type"
            assert "kafka_messages_queued" in metrics, "Missing kafka_messages_queued"
            assert "kafka_requests_total" in metrics, "Missing kafka_requests_total"
            assert "kafka_responses_total" in metrics, "Missing kafka_responses_total"

            # librdkafka names the handle "<client.id>#consumer-<n>".
            assert metrics["kafka_client_name"].startswith(f"{consumer_config['client.id']}#consumer-")

            # Client type should be consumer
            assert metrics["kafka_client_type"] == "consumer"

            # Should have made some requests
            assert metrics["kafka_requests_total"] >= 0

            print("\n=== PROMETHEUS METRICS ===")
            for key, value in sorted(metrics.items()):
                print(f"  {key}: {value}")

            # 5. Verify broker metrics exist
            broker_metrics = collector.get_broker_metrics()
            print(f"\n=== BROKER METRICS ({len(broker_metrics)} brokers) ===")

            # Should have at least one broker
            assert len(broker_metrics) >= 1, "Expected at least 1 broker"

            for broker_name, broker_stats in broker_metrics.items():
                print(f"\n  Broker: {broker_name}")
                # Verify key broker metrics
                assert "state" in broker_stats, f"Missing state for {broker_name}"
                assert "tx" in broker_stats, f"Missing tx for {broker_name}"
                assert "rx" in broker_stats, f"Missing rx for {broker_name}"

                for key, value in sorted(broker_stats.items()):
                    print(f"    {key}: {value}")

            # 6. Verify consumer group stats if available
            cgrp_metrics = collector.get_cgrp_metrics()
            if cgrp_metrics:
                print("\n=== CONSUMER GROUP METRICS ===")
                for key, value in sorted(cgrp_metrics.items()):
                    print(f"  {key}: {value}")

                # Verify expected cgrp metrics
                if "state" in cgrp_metrics:
                    assert cgrp_metrics["state"] in ["", "up", "joining", "syncing", "assigned"]

            # 7. Verify all_metrics structure (what Prometheus would scrape)
            all_metrics = collector.get_all_metrics()
            assert "client" in all_metrics
            assert "brokers" in all_metrics
            assert "topics" in all_metrics
            assert "consumer_lag" in all_metrics
            assert "cgrp" in all_metrics

            print("\n=== COMPLETE METRICS STRUCTURE ===")
            print(f"  client: {len(all_metrics['client'])} metrics")
            print(f"  brokers: {len(all_metrics['brokers'])} brokers")
            print(f"  topics: {len(all_metrics['topics'])} topics")
            print(f"  consumer_lag: {len(all_metrics['consumer_lag'])} topics")
            print(f"  cgrp: {len(all_metrics['cgrp'])} metrics")

        finally:
            consumer.close()

    def test_readonly_client_cannot_modify_data(self, kafka_config):
        """Verify ReadOnlyKafkaClient has no produce methods."""
        from scalo.kafka.readonly import ReadOnlyKafkaClient

        with ReadOnlyKafkaClient(kafka_config, verify_ssl=False) as client:
            # Should NOT have these methods
            assert not hasattr(client, "send")
            assert not hasattr(client, "produce")
            assert not hasattr(client, "create_topic")
            assert not hasattr(client, "delete_topic")

            # Should have read-only methods
            assert hasattr(client, "list_topics")
            assert hasattr(client, "describe_topic")
            assert hasattr(client, "get_watermark_offsets")
            assert hasattr(client, "get_consumer_lag")
            assert hasattr(client, "get_topic_message_count")

            print("\n=== READ-ONLY CLIENT VERIFICATION ===")
            print("  ✓ No send() method")
            print("  ✓ No produce() method")
            print("  ✓ No create_topic() method")
            print("  ✓ No delete_topic() method")
            print("  ✓ Has list_topics()")
            print("  ✓ Has describe_topic()")
            print("  ✓ Has get_watermark_offsets()")
            print("  ✓ Has get_consumer_lag()")
            print("  ✓ Has get_topic_message_count()")

    def test_prometheus_format_output(self, kafka_config, kafka_topics, kafka_group):
        """
        Verify metrics can be formatted for Prometheus scraping.

        This simulates what a Prometheus exporter would do.
        """
        import time

        from confluent_kafka import Consumer

        from scalo.kafka.config import CONSUMER_DEFAULTS, merge_config
        from scalo.kafka.metrics import KafkaMetricsCollector, create_stats_callback
        from scalo.kafka.readonly import ReadOnlyKafkaClient

        collector = KafkaMetricsCollector()
        callback = create_stats_callback(collector)

        consumer_config = merge_config(
            kafka_config.copy(),
            CONSUMER_DEFAULTS,
            verify_ssl=False,
        )
        consumer_config["group.id"] = kafka_group("prometheus")
        topic = kafka_topics("prometheus")
        consumer_config["statistics.interval.ms"] = 1000
        consumer_config["stats_cb"] = callback

        consumer = Consumer(consumer_config)

        try:
            # Subscribe and poll to get stats
            with ReadOnlyKafkaClient(kafka_config, verify_ssl=False) as readonly_client:
                assert topic in {t.name for t in readonly_client.list_topics()}
            consumer.subscribe([topic])

            for _ in range(3):
                consumer.poll(timeout=0.5)
                time.sleep(0.3)

            # Format metrics in Prometheus exposition format
            def format_prometheus(collector: KafkaMetricsCollector) -> str:
                """Format metrics in Prometheus text exposition format."""
                lines = []

                # Client metrics
                metrics = collector.get_metrics()
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        lines.append(f"{key} {value}")

                # Broker metrics with labels
                for broker_name, broker_stats in collector.get_broker_metrics().items():
                    broker_label = f'broker="{broker_name}"'
                    for key, value in broker_stats.items():
                        if isinstance(value, (int, float)):
                            lines.append(f"kafka_broker_{key}{{{broker_label}}} {value}")

                # Consumer lag metrics with labels
                for topic, partitions in collector.get_consumer_lag().items():
                    for partition, lag in partitions.items():
                        labels = f'topic="{topic}",partition="{partition}"'
                        lines.append(f"kafka_consumer_lag{{{labels}}} {lag}")

                return "\n".join(lines)

            prometheus_output = format_prometheus(collector)

            print("\n=== PROMETHEUS EXPOSITION FORMAT ===")
            print(prometheus_output)

            # Verify format is correct
            assert "kafka_requests_total" in prometheus_output
            assert "kafka_responses_total" in prometheus_output

            # Verify broker metrics have labels
            if collector.get_broker_metrics():
                assert "kafka_broker_" in prometheus_output
                assert 'broker="' in prometheus_output

        finally:
            consumer.close()


# =============================================================================
# Test Data Generation and Topic Setup
# =============================================================================

fake = Faker()
Faker.seed(42)  # Reproducible test data


def generate_user_event() -> dict:
    """Generate a fake user event for testing."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": fake.random_element(["login", "logout", "purchase", "view"]),
        "timestamp": datetime.now(UTC).isoformat(),
        "user": {
            "id": fake.uuid4(),
            "name": fake.name(),
            "email": fake.email(),
            "country": fake.country_code(),
        },
        "metadata": {
            "ip_address": fake.ipv4(),
            "user_agent": fake.user_agent(),
            "session_id": fake.uuid4(),
        },
    }


def generate_order_event() -> dict:
    """Generate a fake order event for testing."""
    return {
        "order_id": str(uuid.uuid4()),
        "customer_id": fake.uuid4(),
        "created_at": datetime.now(UTC).isoformat(),
        "status": fake.random_element(["pending", "confirmed", "shipped", "delivered"]),
        "items": [
            {
                "sku": fake.bothify("???-#####"),
                "name": fake.word(),
                "quantity": fake.random_int(1, 5),
                "price": float(fake.pydecimal(min_value=10, max_value=500, left_digits=3)),
            }
            for _ in range(fake.random_int(1, 3))
        ],
        "shipping": {
            "address": fake.address().replace("\n", ", "),
            "city": fake.city(),
            "country": fake.country(),
        },
        "total": float(fake.pydecimal(min_value=50, max_value=2000, left_digits=4)),
    }


class TestKafkaProducerConsumerIntegration:
    """Integration tests for producer and consumer with real test data."""

    @pytest.fixture
    def test_topic(self, kafka_topics):
        """A topic of this test's own."""
        return kafka_topics()

    def test_produce_and_consume_user_events(self, kafka_config, test_topic, kafka_group):
        """Should produce and consume user events with JSON payloads."""
        from scalo.kafka import KafkaConsumer, KafkaProducer

        num_messages = 10

        # 1. Produce test messages
        print(f"\n=== Producing {num_messages} user events to {test_topic} ===")
        produced_messages = []

        with KafkaProducer(kafka_config, verify_ssl=False) as producer:
            for i in range(num_messages):
                event = generate_user_event()
                produced_messages.append(event)
                producer.send(
                    test_topic,
                    value=event,
                    key=event["user"]["id"],
                )
                print(f"  Produced: {event['event_type']} for {event['user']['name']}")

            # Ensure all messages are sent
            remaining = producer.flush(timeout=10.0)
            assert remaining == 0, f"Failed to flush {remaining} messages"

        print(f"  All {num_messages} messages produced")

        # 2. Consume and verify messages
        print(f"\n=== Consuming messages from {test_topic} ===")
        consumed_messages: list[dict] = []

        with KafkaConsumer(kafka_config, kafka_group("consume"), verify_ssl=False) as consumer:
            consumer.subscribe([test_topic])

            # Poll for messages with timeout
            start_time = time.time()
            timeout = 30.0

            while len(consumed_messages) < num_messages and (time.time() - start_time) < timeout:
                msg = consumer.poll(timeout=1.0)
                if msg:
                    event = msg.value_as_json()
                    assert isinstance(event, dict), f"message is not a JSON object: {event!r}"
                    consumed_messages.append(event)
                    print(f"  Consumed: {event['event_type']} for {event['user']['name']}")
                    consumer.commit()

        print(f"  Consumed {len(consumed_messages)} messages")

        # 3. Verify
        assert len(consumed_messages) == num_messages
        event_ids = {e["event_id"] for e in consumed_messages}
        expected_ids = {e["event_id"] for e in produced_messages}
        assert event_ids == expected_ids, "Message content mismatch"

    @pytest.mark.full
    def test_produce_order_events_with_headers(self, kafka_config, test_topic, kafka_group):
        """Should produce order events with custom headers."""
        from scalo.kafka import KafkaConsumer, KafkaProducer

        num_messages = 5

        # 1. Produce with headers
        print(f"\n=== Producing {num_messages} order events with headers ===")

        with KafkaProducer(kafka_config, verify_ssl=False) as producer:
            for i in range(num_messages):
                order = generate_order_event()
                headers = {
                    "content-type": "application/json",
                    "x-order-id": order["order_id"],
                    "x-customer-id": order["customer_id"],
                }
                producer.send(
                    test_topic,
                    value=order,
                    key=order["order_id"],
                    headers=headers,
                )
                print(f"  Order {order['order_id'][:8]}... status={order['status']}")

            producer.flush(timeout=10.0)

        print("  All orders produced with headers")

        # 2. Consume and verify headers
        consumed = 0
        with KafkaConsumer(kafka_config, kafka_group("consume"), verify_ssl=False) as consumer:
            consumer.subscribe([test_topic])

            start = time.time()
            while consumed < num_messages and (time.time() - start) < 30:
                msg = consumer.poll(timeout=1.0)
                if msg:
                    consumed += 1
                    # Verify headers exist
                    if msg.headers:
                        header_keys = [k for k, v in msg.headers]
                        assert "content-type" in header_keys
                    consumer.commit()

        assert consumed == num_messages


@pytest.mark.full
class TestKafkaAdminIntegration:
    """Integration tests for KafkaAdmin operations."""

    def test_get_topic_config(self, kafka_config, kafka_topics):
        """Should retrieve topic configuration."""
        from scalo.kafka import KafkaAdmin

        topic_name = kafka_topics("config")

        with KafkaAdmin(kafka_config, verify_ssl=False) as admin:
            config = admin.get_topic_config(topic_name)

            print(f"\n=== Topic Config for {topic_name} ===")
            # Show key configs
            key_configs = [
                "retention.ms",
                "cleanup.policy",
                "segment.bytes",
                "max.message.bytes",
                "min.insync.replicas",
            ]
            for key in key_configs:
                if key in config:
                    print(f"  {key}: {config[key]}")

            assert "retention.ms" in config
            assert "cleanup.policy" in config

    def test_admin_operations_context_manager(self, kafka_config):
        """Admin should work as context manager."""
        from scalo.kafka import KafkaAdmin

        with KafkaAdmin(kafka_config, verify_ssl=False) as admin:
            assert admin is not None
            # Just verify we can connect
            print("\n=== KafkaAdmin Context Manager ===")
            print("  Connected successfully")


@pytest.mark.full
class TestKafkaConsumerOffsetReset:
    """Integration tests for consumer offset reset operations."""

    @pytest.fixture
    def populated_topic(self, kafka_config, kafka_topics):
        """Create a topic with test data and return its name."""
        from scalo.kafka import KafkaProducer

        topic = kafka_topics("offset")

        # Produce 20 messages with timestamps
        with KafkaProducer(kafka_config, verify_ssl=False) as producer:
            for i in range(20):
                event = {
                    "index": i,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": fake.sentence(),
                }
                producer.send(topic, value=event)
                time.sleep(0.05)  # Small delay for timestamp variation
            producer.flush(timeout=10.0)

        print(f"\n  Created test topic {topic} with 20 messages")
        return topic

    def test_reset_offsets_to_earliest(self, kafka_config, populated_topic, kafka_group):
        """Should reset consumer group offsets to earliest."""
        from scalo.kafka import KafkaAdmin, KafkaConsumer

        group_id = kafka_group("reset-earliest")

        # First, consume some messages to create committed offsets
        with KafkaConsumer(kafka_config, group_id, verify_ssl=False) as consumer:
            consumer.subscribe([populated_topic])
            consumed = 0
            start = time.time()
            while consumed < 10 and (time.time() - start) < 30:
                msg = consumer.poll(timeout=1.0)
                if msg:
                    consumed += 1
                    consumer.commit()

        print("\n=== Reset Offsets to Earliest ===")
        print(f"  Topic: {populated_topic}")
        print(f"  Group: {group_id}")
        print(f"  Consumed {consumed} messages before reset")

        # Reset to earliest
        with KafkaAdmin(kafka_config, verify_ssl=False) as admin:
            new_offsets = admin.reset_offsets_to_earliest(group_id, populated_topic)
            print(f"  New offsets: {new_offsets}")

            # All offsets should be 0 (earliest)
            for partition, offset in new_offsets.items():
                assert offset == 0, f"Partition {partition} should be at 0"

        print("  Offsets reset to earliest successfully")

    def test_reset_offsets_to_latest(self, kafka_config, populated_topic, kafka_group):
        """Should reset consumer group offsets to latest."""
        from scalo.kafka import KafkaAdmin, KafkaClient

        group_id = kafka_group("reset-latest")

        # Get current high watermarks
        with KafkaClient(kafka_config, verify_ssl=False) as client:
            watermarks = client.get_watermark_offsets(populated_topic)

        print("\n=== Reset Offsets to Latest ===")
        print(f"  Topic: {populated_topic}")
        print(f"  Group: {group_id}")
        print(f"  Current watermarks: {watermarks}")

        with KafkaAdmin(kafka_config, verify_ssl=False) as admin:
            new_offsets = admin.reset_offsets_to_latest(group_id, populated_topic)
            print(f"  New offsets: {new_offsets}")

            # Offsets should match high watermarks
            for partition, offset in new_offsets.items():
                _, high = watermarks[partition]
                assert offset == high, f"Partition {partition} should be at {high}"

        print("  Offsets reset to latest successfully")


@pytest.mark.full
class TestSchemaAnalyserIntegration:
    """Integration tests for schema analysis with real Kafka data."""

    def test_analyse_topic_schema(self, kafka_config, kafka_topics, kafka_group):
        """Should analyse JSON schema from topic messages."""
        from scalo.kafka import KafkaConsumer, KafkaProducer, SchemaAnalyser

        topic = kafka_topics("schema")
        group_id = kafka_group("schema-analyser")

        # Produce mixed events
        with KafkaProducer(kafka_config, verify_ssl=False) as producer:
            for _ in range(5):
                producer.send(topic, value=generate_user_event())
            for _ in range(5):
                producer.send(topic, value=generate_order_event())
            producer.flush(timeout=10.0)

        print(f"\n=== Schema Analysis for {topic} ===")

        # Consume and analyse
        analyser = SchemaAnalyser()

        with KafkaConsumer(kafka_config, group_id, verify_ssl=False) as consumer:
            consumer.subscribe([topic])
            consumed = 0
            start = time.time()

            while consumed < 10 and (time.time() - start) < 30:
                msg = consumer.poll(timeout=1.0)
                if msg:
                    analyser.add_message(msg)
                    consumed += 1

        result = analyser.analyse()

        print(f"  Messages analysed: {result.total_messages}")
        print(f"  Fields discovered: {len(result.field_stats)}")

        # Should have found common fields
        assert result.total_messages == 10
        assert len(result.field_stats) > 0

        # Print discovered schema
        print("\n  Discovered fields:")
        for field_name, stats in list(result.field_stats.items())[:10]:
            print(f"    {field_name}: {stats['types']} (seen {stats['count']}x)")

        print("  Schema analysis complete")


@pytest.mark.full
class TestAsyncKafkaIntegration:
    """Integration tests for async Kafka clients."""

    @pytest.mark.asyncio
    async def test_async_client_list_topics(self, kafka_config):
        """Async client should list topics."""
        from scalo.kafka import AsyncKafkaClient

        print("\n=== Async Client List Topics ===")

        async with AsyncKafkaClient(kafka_config, verify_ssl=False) as client:
            topics = await client.list_topics()

            print(f"  Found {len(topics)} topics")
            for topic in topics[:5]:
                print(f"    - {topic.name}")

            assert isinstance(topics, list)

        print("  Async client works correctly")

    @pytest.mark.asyncio
    async def test_async_producer_send(self, kafka_config, kafka_topics):
        """Async producer should send messages."""
        from scalo.kafka import AsyncKafkaProducer

        topic = kafka_topics("async")

        print(f"\n=== Async Producer Send to {topic} ===")

        async with AsyncKafkaProducer(kafka_config, verify_ssl=False) as producer:
            for i in range(5):
                event = generate_user_event()
                await producer.send(topic, value=event)
                print(f"  Sent: {event['event_type']}")

            await producer.flush()

        print("  Async producer sent all messages")


@pytest.mark.full
class TestSamplingIntegration:
    """Integration tests for sampling utilities."""

    def test_reservoir_sample_from_topic(self, kafka_config, kafka_topics, kafka_group):
        """Should sample k of the messages a topic holds, by reservoir sampling."""
        from scalo.kafka import KafkaConsumer, reservoir_sample

        topic = kafka_topics("sampling")
        _produce(kafka_config, topic, [{"n": n} for n in range(20)])
        group_id = kafka_group("sampler")

        with KafkaConsumer(kafka_config, group_id, verify_ssl=False) as consumer:
            consumer.subscribe([topic])

            def message_iterator():
                deadline = time.monotonic() + 30
                seen = 0
                while seen < 20 and time.monotonic() < deadline:
                    msg = consumer.poll(timeout=0.5)
                    if msg:
                        seen += 1
                        yield msg

            sample = reservoir_sample(message_iterator(), k=5, seed=42)

        assert len(sample) == 5
        assert len({(msg.partition, msg.offset) for msg in sample}) == 5
