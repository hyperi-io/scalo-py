# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/async_consumer.py
# Purpose:   Async Kafka consumer wrapper
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Async wrapper around confluent-kafka Consumer via run_blocking."""

from __future__ import annotations

from typing import Any, AsyncIterator

from confluent_kafka import Consumer, KafkaError, TopicPartition

from ..concurrency import run_blocking
from .config import CONSUMER_DEFAULTS, merge_config
from .consumer import KafkaConsumerError
from .types import Message


class AsyncKafkaConsumer:
    """
    Async Kafka consumer.

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

    async def consume(
        self,
        num_messages: int = 1,
        timeout: float = 1.0,
    ) -> list[Message]:
        """Consume a batch of messages."""
        return await run_blocking(self._consume_sync, num_messages, timeout)

    def _consume_sync(self, num_messages: int, timeout: float) -> list[Message]:
        """Sync consume implementation."""
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

    async def seek(self, topic: str, partition: int, offset: int) -> None:
        """Seek to specific offset."""
        tp = TopicPartition(topic, partition, offset)
        self._consumer.seek(tp)

    async def commit(self, asynchronous: bool = False) -> None:
        """Commit current offsets."""
        if asynchronous:
            self._consumer.commit(asynchronous=True)
        else:
            await run_blocking(self._consumer.commit, asynchronous=False)

    def __aiter__(self) -> AsyncIterator[Message]:
        return self

    async def __anext__(self) -> Message:
        """Get next message from consumer."""
        while not self._closed:
            msg = await self.poll(timeout=1.0)
            if msg is not None:
                return msg
        raise StopAsyncIteration

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
