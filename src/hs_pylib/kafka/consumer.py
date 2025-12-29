# Project:   hs-pylib
# File:      src/hs_pylib/kafka/consumer.py
# Purpose:   Kafka consumer with corporate defaults
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Kafka consumer with corporate defaults.

Provides a high-level consumer that wraps confluent-kafka
with sensible defaults for enterprise use.
"""

from __future__ import annotations

from typing import Any, Iterator

from confluent_kafka import Consumer, KafkaError, TopicPartition

from .config import CONSUMER_DEFAULTS, merge_config
from .types import Message


class KafkaConsumerError(Exception):
    """Kafka consumer error."""

    def __init__(self, message: str, error_code: int | None = None):
        self.error_code = error_code
        super().__init__(message)


class KafkaConsumer:
    """
    Kafka consumer with corporate defaults.

    Wraps confluent-kafka Consumer with sensible defaults
    and a simplified API.

    Args:
        config: Either bootstrap.servers string or full config dict
        group_id: Consumer group ID (required)
        verify_ssl: If False, disable SSL certificate verification

    Example:
        with KafkaConsumer("localhost:9092", "my-group") as consumer:
            consumer.subscribe("my-topic")
            for msg in consumer:
                print(msg.value_as_json())
                consumer.commit()
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        group_id: str,
        verify_ssl: bool = True,
    ):
        # Normalize config to dict
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        # Add group.id
        config = config.copy()
        config["group.id"] = group_id

        # Merge with defaults
        self._config = merge_config(config, CONSUMER_DEFAULTS, verify_ssl=verify_ssl)

        # Create consumer
        self._consumer = Consumer(self._config)
        self._closed = False

    def __enter__(self) -> "KafkaConsumer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        """Close the consumer."""
        if not self._closed:
            self._consumer.close()
            self._closed = True

    # =========================================================================
    # Subscription
    # =========================================================================

    def subscribe(self, topics: str | list[str]) -> None:
        """
        Subscribe to topics.

        Args:
            topics: Single topic name or list of topic names
        """
        if isinstance(topics, str):
            topics = [topics]
        self._consumer.subscribe(topics)

    def unsubscribe(self) -> None:
        """Unsubscribe from all topics."""
        self._consumer.unsubscribe()

    # =========================================================================
    # Manual Assignment
    # =========================================================================

    def assign(self, topic: str, partitions: list[int]) -> None:
        """
        Manually assign partitions.

        Args:
            topic: Topic name
            partitions: List of partition numbers to assign
        """
        tps = [TopicPartition(topic, p) for p in partitions]
        self._consumer.assign(tps)

    def assignment(self) -> list[tuple[str, int]]:
        """
        Get current partition assignment.

        Returns:
            List of (topic, partition) tuples
        """
        tps = self._consumer.assignment()
        return [(tp.topic, tp.partition) for tp in tps]

    # =========================================================================
    # Polling
    # =========================================================================

    def poll(self, timeout: float = 1.0) -> Message | None:
        """
        Poll for a single message.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Message object, or None if timeout/partition EOF

        Raises:
            KafkaConsumerError: On fatal Kafka error
        """
        msg = self._consumer.poll(timeout)

        if msg is None:
            return None

        error = msg.error()
        if error:
            if error.code() == KafkaError._PARTITION_EOF:
                return None
            raise KafkaConsumerError(
                f"Kafka error: {error.str()}",
                error_code=error.code(),
            )

        return self._to_message(msg)

    def consume(
        self,
        num_messages: int = 1,
        timeout: float = 1.0,
    ) -> list[Message]:
        """
        Consume a batch of messages.

        Args:
            num_messages: Maximum number of messages to return
            timeout: Maximum time to wait in seconds

        Returns:
            List of Message objects (may be empty)

        Raises:
            KafkaConsumerError: On fatal Kafka error
        """
        msgs = self._consumer.consume(num_messages, timeout)

        messages = []
        for msg in msgs:
            error = msg.error()
            if error:
                if error.code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaConsumerError(
                    f"Kafka error: {error.str()}",
                    error_code=error.code(),
                )
            messages.append(self._to_message(msg))

        return messages

    # =========================================================================
    # Seek Operations
    # =========================================================================

    def seek(self, topic: str, partition: int, offset: int) -> None:
        """
        Seek to specific offset.

        Args:
            topic: Topic name
            partition: Partition number
            offset: Offset to seek to
        """
        tp = TopicPartition(topic, partition, offset)
        self._consumer.seek(tp)

    def seek_to_beginning(self, topic: str, partition: int) -> None:
        """
        Seek to beginning of partition.

        Args:
            topic: Topic name
            partition: Partition number
        """
        tp = TopicPartition(topic, partition)
        low, _ = self._consumer.get_watermark_offsets(tp)
        self.seek(topic, partition, low)

    def seek_to_end(self, topic: str, partition: int) -> None:
        """
        Seek to end of partition.

        Args:
            topic: Topic name
            partition: Partition number
        """
        tp = TopicPartition(topic, partition)
        _, high = self._consumer.get_watermark_offsets(tp)
        self.seek(topic, partition, high)

    def position(self, topic: str, partition: int) -> int:
        """
        Get current position (next offset to read).

        Args:
            topic: Topic name
            partition: Partition number

        Returns:
            Current offset position
        """
        tp = TopicPartition(topic, partition)
        result = self._consumer.position([tp])
        return result[0].offset

    # =========================================================================
    # Commit Operations
    # =========================================================================

    def commit(self, asynchronous: bool = False) -> None:
        """
        Commit current offsets.

        Args:
            asynchronous: If True, commit asynchronously
        """
        self._consumer.commit(asynchronous=asynchronous)

    def committed(self, topic: str, partitions: list[int]) -> dict[int, int]:
        """
        Get committed offsets.

        Args:
            topic: Topic name
            partitions: List of partition numbers

        Returns:
            Dict of partition -> committed offset
        """
        tps = [TopicPartition(topic, p) for p in partitions]
        result = self._consumer.committed(tps)
        return {tp.partition: tp.offset for tp in result}

    # =========================================================================
    # Iterator Interface
    # =========================================================================

    def __iter__(self) -> Iterator[Message]:
        return self

    def __next__(self) -> Message:
        """Get next message from consumer."""
        while not self._closed:
            msg = self.poll(timeout=1.0)
            if msg is not None:
                return msg
        raise StopIteration

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _to_message(self, msg) -> Message:
        """Convert confluent-kafka message to Message type."""
        _, timestamp = msg.timestamp()
        return Message(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=msg.key(),
            value=msg.value(),
            timestamp=timestamp,
            headers=msg.headers(),
        )
