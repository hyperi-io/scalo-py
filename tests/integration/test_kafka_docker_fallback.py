# Project:   hs-pylib
# File:      tests/integration/test_kafka_docker_fallback.py
# Purpose:   Test Docker Kafka fallback (forces local Docker even if remote available)
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Integration tests for Docker Kafka fallback.

These tests force the use of local Docker Kafka, skipping remote even if available.
This verifies the Docker fallback path works correctly.

Run with: pytest tests/integration/test_kafka_docker_fallback.py -v -s
"""

import uuid

import pytest

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestDockerKafkaFallback:
    """Test that Docker Kafka fallback works correctly."""

    def test_can_connect_to_local_kafka(self, kafka_config_local_only):
        """Should connect to local Docker Kafka."""
        from hs_pylib.kafka.client import KafkaClient

        # Verify we're using localhost
        assert kafka_config_local_only.get("bootstrap.servers") == "localhost:9092"

        with KafkaClient(kafka_config_local_only, verify_ssl=False) as client:
            topics = client.list_topics()
            print("\n  Connected to local Docker Kafka")
            print(f"  Found {len(topics)} topics")
            assert isinstance(topics, list)

    def test_can_produce_and_consume(self, kafka_config_local_only):
        """Should produce and consume messages on local Kafka."""
        from hs_pylib.kafka import KafkaConsumer, KafkaProducer

        topic = f"hs-pylib-docker-test-{uuid.uuid4().hex[:8]}"
        group_id = f"docker-test-{uuid.uuid4().hex[:8]}"
        test_message = {"test": "docker-fallback", "id": str(uuid.uuid4())}

        # Produce
        with KafkaProducer(kafka_config_local_only, verify_ssl=False) as producer:
            producer.send(topic, value=test_message)
            producer.flush(timeout=10.0)
            print(f"\n  Produced message to {topic}")

        # Consume
        with KafkaConsumer(kafka_config_local_only, group_id, verify_ssl=False) as consumer:
            consumer.subscribe([topic])
            msg = None
            for _ in range(30):  # Try for up to 30 polls
                msg = consumer.poll(timeout=1.0)
                if msg:
                    break

            assert msg is not None, "Failed to consume message"
            consumed = msg.value_as_json()
            assert consumed["id"] == test_message["id"]
            print("  Consumed message successfully")
