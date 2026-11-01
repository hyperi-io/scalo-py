# Project:   scalo
# File:      src/scalo/kafka/async_consumer.py
# Purpose:   Async Kafka consumer wrapper
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Async wrapper around confluent-kafka Consumer via run_blocking."""

from typing import Any, AsyncIterator

from confluent_kafka import Consumer, TopicPartition

from ..concurrency import run_blocking
from .config import CONSUMER_DEFAULTS, merge_config
from .consumer import _hand_over
from .types import Message


class AsyncKafkaConsumer:
    """Async Kafka consumer.

    Wraps confluent-kafka Consumer with async methods via ``run_blocking``.

    Args:
        config: Either bootstrap.servers string or full config dict
        group_id: Consumer group ID
        verify_ssl: If False, disable SSL certificate verification

    Example:
        async with AsyncKafkaConsumer("localhost:9092", "my-group") as consumer:
            consumer.subscribe("my-topic")
            async for msg in consumer:
                print(msg.value_as_json())
                await consumer.commit()
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        group_id: str,
        verify_ssl: bool = True,
    ):
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        config = config.copy()
        config["group.id"] = group_id

        self._config = merge_config(config, CONSUMER_DEFAULTS, verify_ssl=verify_ssl)
        # Offsets are stored as messages are handed over, as KafkaConsumer does.
        self._stores_offsets = "enable.auto.offset.store" not in config
        if self._stores_offsets:
            self._config["enable.auto.offset.store"] = False
        self._consumer = Consumer(self._config)
        self._closed = False

    def __repr__(self) -> str:
        from .config import mask_credentials

        return f"AsyncKafkaConsumer(config={mask_credentials(self._config)!r})"

    async def __aenter__(self) -> AsyncKafkaConsumer:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the consumer."""
        if not self._closed:
            await run_blocking(self._consumer.close)
            self._closed = True

    def subscribe(self, topics: str | list[str]) -> None:
        """Subscribe to topics (sync - fast operation)."""
        if isinstance(topics, str):
            topics = [topics]
        self._consumer.subscribe(topics)

    def unsubscribe(self) -> None:
        """Unsubscribe from all topics."""
        self._consumer.unsubscribe()

    async def poll(self, timeout: float = 1.0) -> Message | None:
        """Poll for a single message."""
        return await run_blocking(self._poll_sync, timeout)

    def _poll_sync(self, timeout: float) -> Message | None:
        """Sync poll implementation."""
        msg = self._consumer.poll(timeout)
        handed = _hand_over(self._consumer, [] if msg is None else [msg], self._stores_offsets)
        return handed[0] if handed else None

    async def consume(
        self,
        num_messages: int = 1,
        timeout: float = 1.0,
    ) -> list[Message]:
        """Consume a batch of messages."""
        return await run_blocking(self._consume_sync, num_messages, timeout)

    def _consume_sync(self, num_messages: int, timeout: float) -> list[Message]:
        """Sync consume implementation, rewinding on a batch error as ``KafkaConsumer.consume`` does."""
        return _hand_over(self._consumer, self._consumer.consume(num_messages, timeout), self._stores_offsets)

    async def seek(self, topic: str, partition: int, offset: int) -> None:
        """Seek to specific offset."""
        tp = TopicPartition(topic, partition, offset)
        await run_blocking(self._consumer.seek, tp)

    async def commit(self, asynchronous: bool = False) -> None:
        """Commit current offsets."""
        # Both paths offload: even an async commit enters librdkafka C code and
        # must not run on the event-loop thread.
        await run_blocking(self._consumer.commit, asynchronous=asynchronous)

    def __aiter__(self) -> AsyncIterator[Message]:
        return self

    async def __anext__(self) -> Message:
        """Get next message from consumer."""
        while not self._closed:
            msg = await self.poll(timeout=1.0)
            if msg is not None:
                return msg
        raise StopAsyncIteration
