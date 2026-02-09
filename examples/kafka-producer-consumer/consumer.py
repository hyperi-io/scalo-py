# Project:   hyperi-pylib
# File:      examples/kafka-producer-consumer/consumer.py
# Purpose:   Demonstrate hyperi-pylib Kafka consumer
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka Consumer Example.

Demonstrates hyperi-pylib's Kafka consumer with corporate defaults.
Run with: uv run python consumer.py

Requires Kafka running (use docker compose up -d).
"""

import json
import os
import signal
import sys

from hyperi_pylib.kafka import KafkaConsumer
from hyperi_pylib.logger import error, info, success, warning


BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = "example-events"
GROUP_ID = "example-consumer-group"

# Graceful shutdown flag
running = True


def signal_handler(signum, frame) -> None:
    """Handle shutdown signals."""
    global running
    info("Shutdown signal received", signal=signum)
    running = False


def consume_messages(max_messages: int = 20, timeout: float = 30.0) -> int:
    """Consume messages from Kafka."""
    global running

    info(
        "Starting consumer",
        bootstrap_servers=BOOTSTRAP_SERVERS,
        topic=TOPIC,
        group_id=GROUP_ID,
    )

    # Create consumer with corporate defaults
    consumer = KafkaConsumer({
        "bootstrap.servers": BOOTSTRAP_SERVERS,
        "group.id": GROUP_ID,
        # Corporate defaults are applied automatically:
        # - auto.offset.reset=earliest
        # - enable.auto.commit=false (manual commit for reliability)
    })

    try:
        # Subscribe to topic
        consumer.subscribe([TOPIC])
        info("Subscribed to topic", topic=TOPIC)

        messages_consumed = 0
        start_time = __import__("time").time()

        while running and messages_consumed < max_messages:
            # Check timeout
            if __import__("time").time() - start_time > timeout:
                warning("Consumer timeout reached", timeout=timeout)
                break

            # Poll for messages
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                error("Consumer error", error=str(msg.error()))
                continue

            # Process message
            try:
                key = msg.key().decode("utf-8") if msg.key() else None
                value = json.loads(msg.value().decode("utf-8"))

                info(
                    "Received message",
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                    key=key,
                )

                # Process the event
                process_event(value)

                # Commit offset (manual commit for reliability)
                consumer.commit(msg)

                messages_consumed += 1

            except json.JSONDecodeError as e:
                error("Failed to decode message", error=str(e))

        success("Consumer finished", messages_consumed=messages_consumed)
        return messages_consumed

    finally:
        consumer.close()
        info("Consumer closed")


def process_event(event: dict) -> None:
    """Process a single event."""
    event_type = event.get("event_type", "unknown")
    user_id = event.get("user_id", "unknown")
    action = event.get("action", "unknown")

    info(
        "Processing event",
        event_type=event_type,
        user_id=user_id,
        action=action,
    )


def main() -> None:
    """Run the consumer demonstration."""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=== hyperi-pylib Kafka Consumer Demo ===\n")
    print("Press Ctrl+C to stop consuming.\n")

    try:
        count = consume_messages(max_messages=20, timeout=30.0)
        print(f"\n=== Consumer completed: {count} messages processed ===")
    except Exception as e:
        error("Consumer failed", error=str(e))
        print(f"\nError: {e}")
        print("\nMake sure Kafka is running and producer has sent messages:")
        print("  docker compose up -d")
        print("  uv run python producer.py")
        raise


if __name__ == "__main__":
    main()
