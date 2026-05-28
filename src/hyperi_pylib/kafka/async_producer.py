# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/async_producer.py
# Purpose:   Async Kafka producer wrapper
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Async wrapper around confluent-kafka Producer via run_blocking.

Delivery semantics:

- ``send_and_wait()`` returns an ``asyncio.Future[DeliveryReport]``
  that resolves when librdkafka's delivery-report callback fires.
  Awaiting the future surfaces broker failures to the caller; ignoring
  it is equivalent to fire-and-forget.
- ``send()`` is the fire-and-forget variant (no awaitable result). On
  ``BufferError`` from librdkafka (queue full) it polls briefly then
  retries once before raising.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from confluent_kafka import KafkaError, Message, Producer

from ..concurrency import run_blocking
from .config import PRODUCER_DEFAULTS, merge_config


@dataclass(slots=True, frozen=True)
class DeliveryReport:
    """Outcome of a single produce() call resolved via the dr_cb."""

    topic: str
    partition: int
    offset: int
    error: str | None  # None on success; str(KafkaError) on failure


class AsyncKafkaProducer:
    """
    Async Kafka producer.

    Wraps confluent-kafka Producer with async methods via
    :func:`hyperi_pylib.concurrency.run_blocking` so producer calls
    don't block the event loop.

    Args:
        config: Either bootstrap.servers string or full config dict
        verify_ssl: If False, disable SSL certificate verification

    Example:
        async with AsyncKafkaProducer("localhost:9092") as producer:
            report = await producer.send_and_wait("my-topic", {"event": "created"})
            assert report.error is None
            await producer.flush()
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        verify_ssl: bool = True,
    ):
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        self._config = merge_config(config, PRODUCER_DEFAULTS, verify_ssl=verify_ssl)
        self._producer = Producer(self._config)

    def __repr__(self) -> str:
        from .config import mask_credentials

        return f"AsyncKafkaProducer(config={mask_credentials(self._config)!r})"

    async def __aenter__(self) -> AsyncKafkaProducer:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.flush()

    async def send(
        self,
        topic: str,
        value: str | bytes | dict | list,
        key: str | bytes | None = None,
        partition: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Fire-and-forget send. Delivery failures are NOT surfaced.

        For at-least-once semantics use :meth:`send_and_wait`.
        """
        await run_blocking(self._send_sync, topic, value, key, partition, headers, None)

    async def send_and_wait(
        self,
        topic: str,
        value: str | bytes | dict | list,
        key: str | bytes | None = None,
        partition: int | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> DeliveryReport:
        """Send + await the broker's delivery acknowledgement.

        Raises:
            asyncio.TimeoutError: if ``timeout`` elapses before the
                delivery report fires.
            RuntimeError: if the broker reports a delivery failure.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[DeliveryReport] = loop.create_future()

        def _on_delivery(err: KafkaError | None, msg: Message) -> None:
            # Runs on librdkafka's poll() thread. Hop to the event loop.
            if future.done():
                return
            report = DeliveryReport(
                topic=msg.topic() if msg else topic,
                partition=msg.partition() if msg else -1,
                offset=msg.offset() if msg else -1,
                error=str(err) if err else None,
            )
            loop.call_soon_threadsafe(future.set_result, report)

        await run_blocking(self._send_sync, topic, value, key, partition, headers, _on_delivery)

        if timeout is not None:
            report = await asyncio.wait_for(future, timeout)
        else:
            report = await future

        if report.error is not None:
            raise RuntimeError(f"Kafka delivery failed: {report.error}")
        return report

    def _send_sync(
        self,
        topic: str,
        value: str | bytes | dict | list,
        key: str | bytes | None,
        partition: int | None,
        headers: dict[str, str] | None,
        on_delivery: Any | None,
    ) -> None:
        """Sync send. Retries once on BufferError after a brief poll."""
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
        if on_delivery is not None:
            kwargs["on_delivery"] = on_delivery

        try:
            self._producer.produce(**kwargs)
        except BufferError:
            # librdkafka queue full. Poll to drain delivery reports,
            # then retry once. Caller still gets a clean exception on
            # second failure rather than a silent backlog.
            self._producer.poll(0.5)
            self._producer.produce(**kwargs)
        self._producer.poll(0)

    async def flush(self, timeout: float | None = None) -> int:
        """Wait for all messages to be delivered."""
        return await run_blocking(self._flush_sync, timeout)

    def _flush_sync(self, timeout: float | None) -> int:
        if timeout is not None:
            return self._producer.flush(timeout)
        return self._producer.flush()

    async def poll(self, timeout: float = 0) -> int:
        """Poll for delivery callbacks."""
        return await run_blocking(self._producer.poll, timeout)
