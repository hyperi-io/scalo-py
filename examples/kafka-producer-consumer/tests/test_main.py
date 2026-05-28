# Project:   hyperi-pylib
# File:      examples/kafka-producer-consumer/tests/test_main.py
# Purpose:   Tests for kafka-producer-consumer example
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for kafka-producer-consumer example.

These tests verify the example code structure and imports.
Integration tests require Kafka (skipped if not available).
"""

import pytest


class TestImports:
    """Tests for module imports."""

    def test_kafka_producer_import(self) -> None:
        """Should be able to import KafkaProducer."""
        from hyperi_pylib.kafka import KafkaProducer

        assert KafkaProducer is not None

    def test_kafka_consumer_import(self) -> None:
        """Should be able to import KafkaConsumer."""
        from hyperi_pylib.kafka import KafkaConsumer

        assert KafkaConsumer is not None

    def test_kafka_client_import(self) -> None:
        """Should be able to import KafkaClient."""
        from hyperi_pylib.kafka import KafkaClient

        assert KafkaClient is not None

    def test_producer_module_import(self) -> None:
        """Should be able to import producer module."""
        import producer

        assert hasattr(producer, "main")
        assert hasattr(producer, "produce_messages")

    def test_consumer_module_import(self) -> None:
        """Should be able to import consumer module."""
        import consumer

        assert hasattr(consumer, "main")
        assert hasattr(consumer, "consume_messages")
        assert hasattr(consumer, "process_event")


class TestProcessEvent:
    """Tests for event processing."""

    def test_process_event_handles_valid_event(self) -> None:
        """Should process a valid event without error."""
        import consumer

        event = {
            "event_type": "user_action",
            "user_id": "user_1",
            "action": "click",
        }

        # Should not raise
        consumer.process_event(event)

    def test_process_event_handles_missing_fields(self) -> None:
        """Should handle events with missing fields."""
        import consumer

        # Should not raise even with empty event
        consumer.process_event({})


class TestDeliveryCallback:
    """Tests for producer delivery callback."""

    def test_delivery_callback_exists(self) -> None:
        """Should have delivery callback function."""
        import producer

        assert hasattr(producer, "delivery_callback")
        assert callable(producer.delivery_callback)


@pytest.mark.skipif(
    True,  # Skip by default - requires Kafka
    reason="Integration tests require Kafka (run with docker compose up -d)",
)
class TestIntegration:
    """Integration tests requiring Kafka.

    Run with: docker compose up -d && uv run pytest -k Integration
    """

    def test_producer_creates_successfully(self) -> None:
        """Should be able to create a producer."""
        from hyperi_pylib.kafka import KafkaProducer

        producer = KafkaProducer(
            {
                "bootstrap.servers": "localhost:9092",
            }
        )
        assert producer is not None

    def test_consumer_creates_successfully(self) -> None:
        """Should be able to create a consumer."""
        from hyperi_pylib.kafka import KafkaConsumer

        consumer = KafkaConsumer(
            {
                "bootstrap.servers": "localhost:9092",
                "group.id": "test-group",
            }
        )
        assert consumer is not None
        consumer.close()
