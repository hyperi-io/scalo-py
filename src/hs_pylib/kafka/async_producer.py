# Project:   hs-pylib
# File:      src/hs_pylib/kafka/async_producer.py
# Purpose:   Async Kafka producer wrapper
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Async Kafka producer wrapper.

Uses ThreadPoolExecutor to provide async interface to
the synchronous confluent-kafka Producer.
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from confluent_kafka import Producer

from .config import PRODUCER_DEFAULTS, merge_config


class AsyncKafkaProducer:
    """
    Async Kafka producer.

    Wraps confluent-kafka Producer with async methods.

    Args:
        config: Either bootstrap.servers string or full config dict
        verify_ssl: If False, disable SSL certificate verification
        executor: Optional ThreadPoolExecutor

    Example:
        async with AsyncKafkaProducer("localhost:9092") as producer:
            await producer.send("my-topic", {"event": "created"})
            await producer.flush()
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        verify_ssl: bool = True,
        executor: ThreadPoolExecutor | None = None,
    ):
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        self._config = merge_config(config, PRODUCER_DEFAULTS, verify_ssl=verify_ssl)
        self._producer = Producer(self._config)
        self._executor = executor or ThreadPoolExecutor(max_workers=4)
        self._owns_executor = executor is None

    async def __aenter__(self) -> AsyncKafkaProducer:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.flush()
        if self._owns_executor:
            self._executor.shutdown(wait=False)

    async def send(
        self,
        topic: str,
        value: str | bytes | dict | list,
        key: str | bytes | None = None,
        partition: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Send a message to Kafka."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            self._send_sync,
            topic,
            value,
            key,
            partition,
            headers,
        )

    def _send_sync(
        self,
        topic: str,
        value: str | bytes | dict | list,
        key: str | bytes | None,
        partition: int | None,
        headers: dict[str, str] | None,
    ) -> None:
        """Sync send implementation."""
        # Serialize value
        if isinstance(value, (dict, list)):
            value_bytes = json.dumps(value).encode("utf-8")
        elif isinstance(value, str):
            value_bytes = value.encode("utf-8")
        else:
            value_bytes = value

        # Serialize key
        key_bytes = None
        if key is not None:
            if isinstance(key, str):
                key_bytes = key.encode("utf-8")
            else:
                key_bytes = key

        # Convert headers
        headers_list = None
        if headers:
            headers_list = [(k, v.encode("utf-8") if isinstance(v, str) else v) for k, v in headers.items()]

        # Build produce kwargs
        kwargs: dict[str, Any] = {
            "topic": topic,
            "value": value_bytes,
        }
        if key_bytes is not None:
            kwargs["key"] = key_bytes
        if partition is not None:
            kwargs["partition"] = partition
        if headers_list is not None:
            kwargs["headers"] = headers_list

        self._producer.produce(**kwargs)
        self._producer.poll(0)

    async def flush(self, timeout: float | None = None) -> int:
        """Wait for all messages to be delivered."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._flush_sync,
            timeout,
        )

    def _flush_sync(self, timeout: float | None) -> int:
        """Sync flush implementation."""
        if timeout is not None:
            return self._producer.flush(timeout)
        return self._producer.flush()

    async def poll(self, timeout: float = 0) -> int:
        """Poll for delivery callbacks."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._producer.poll,
            timeout,
        )
