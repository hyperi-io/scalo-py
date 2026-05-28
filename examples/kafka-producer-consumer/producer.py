# Project:   hyperi-pylib
# File:      examples/kafka-producer-consumer/producer.py
# Purpose:   Demonstrate hyperi-pylib Kafka producer
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka Producer Example.

Demonstrates hyperi-pylib's Kafka producer with corporate defaults.
Run with: uv run python producer.py

Requires Kafka running (use docker compose up -d).
"""

import json
import os
import time
from datetime import datetime

from hyperi_pylib.kafka import KafkaProducer
from hyperi_pylib.logger import error, info, success

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = "example-events"


def delivery_callback(err, msg) -> None:
    """Callback for message delivery confirmation."""
    if err:
        error("Message delivery failed", error=str(err), topic=msg.topic())
    else:
        info(
            "Message delivered",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )


def produce_messages(count: int = 10) -> None:
    """Produce sample messages to Kafka."""
    info("Starting producer", bootstrap_servers=BOOTSTRAP_SERVERS, topic=TOPIC)

    # Create producer with corporate defaults
    producer = KafkaProducer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            # Corporate defaults are applied automatically:
            # - acks=all
            # - retries=5
            # - linger.ms=5
        }
    )

    try:
        for i in range(count):
            # Create event payload
            event = {
                "event_type": "user_action",
                "user_id": f"user_{i % 3}",
                "action": "page_view" if i % 2 == 0 else "click",
                "timestamp": datetime.now().isoformat(),
                "sequence": i,
            }

            # Produce message
            key = event["user_id"]
            value = json.dumps(event).encode("utf-8")

            producer.produce(
                topic=TOPIC,
                key=key.encode("utf-8"),
                value=value,
                callback=delivery_callback,
            )

            info("Produced message", sequence=i, user_id=event["user_id"])

            # Flush periodically (or poll to trigger callbacks)
            producer.poll(0)

        # Final flush to ensure all messages are sent
        remaining = producer.flush(timeout=10)
        if remaining > 0:
            error("Some messages not delivered", remaining=remaining)
        else:
            success("All messages delivered", count=count)

    finally:
        info("Producer finished")


def main() -> None:
    """Run the producer demonstration."""
    print("=== hyperi-pylib Kafka Producer Demo ===\n")

    try:
        produce_messages(10)
        print("\n=== Producer completed successfully ===")
    except Exception as e:
        error("Producer failed", error=str(e))
        print(f"\nError: {e}")
        print("\nMake sure Kafka is running:")
        print("  docker compose up -d")
        raise


if __name__ == "__main__":
    main()
