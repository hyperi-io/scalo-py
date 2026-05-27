#  Project:   hyperi-pylib
#  File:      tests/unit/test_kafka_async_producer_delivery.py
#  Purpose:   Verify AsyncKafkaProducer.send_and_wait + BufferError retry
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""B7 regression tests: send_and_wait surfaces delivery acks/failures,
and produce() retries once on librdkafka BufferError before raising."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from hyperi_pylib.kafka.async_producer import AsyncKafkaProducer, DeliveryReport


@pytest.fixture
def mock_producer():
    """Patched confluent_kafka.Producer that returns a controllable mock."""
    with patch("hyperi_pylib.kafka.async_producer.Producer") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


@pytest.mark.asyncio
async def test_send_and_wait_returns_delivery_report_on_success(mock_producer):
    """produce(on_delivery=cb); when cb fires with no error, future resolves
    to a DeliveryReport with error=None and the message coordinates."""
    captured_cb = {}

    def _capture(**kwargs):
        captured_cb["on_delivery"] = kwargs["on_delivery"]
        # Simulate librdkafka invoking the cb from its poll thread.
        msg = MagicMock()
        msg.topic.return_value = "topic-a"
        msg.partition.return_value = 3
        msg.offset.return_value = 42
        # Fire the cb on a background thread to mimic librdkafka.
        import threading

        threading.Thread(target=lambda: captured_cb["on_delivery"](None, msg)).start()

    mock_producer.produce.side_effect = _capture

    async with AsyncKafkaProducer("localhost:9092") as producer:
        report = await producer.send_and_wait("topic-a", {"event": "hi"}, timeout=2.0)

    assert isinstance(report, DeliveryReport)
    assert report.error is None
    assert report.topic == "topic-a"
    assert report.partition == 3
    assert report.offset == 42


@pytest.mark.asyncio
async def test_send_and_wait_raises_on_broker_error(mock_producer):
    """If librdkafka's delivery cb reports an error, send_and_wait raises."""

    def _capture(**kwargs):
        cb = kwargs["on_delivery"]
        msg = MagicMock()
        msg.topic.return_value = "topic-a"
        msg.partition.return_value = 0
        msg.offset.return_value = -1
        err = MagicMock()
        err.__str__ = lambda _: "TopicAuthorizationFailed"
        import threading

        threading.Thread(target=lambda: cb(err, msg)).start()

    mock_producer.produce.side_effect = _capture

    async with AsyncKafkaProducer("localhost:9092") as producer:
        with pytest.raises(RuntimeError, match="TopicAuthorizationFailed"):
            await producer.send_and_wait("topic-a", b"x", timeout=2.0)


@pytest.mark.asyncio
async def test_send_and_wait_timeout(mock_producer):
    """If the broker never acks within timeout, asyncio.TimeoutError surfaces."""
    # produce() doesn't fire the cb at all
    mock_producer.produce.return_value = None

    async with AsyncKafkaProducer("localhost:9092") as producer:
        with pytest.raises(asyncio.TimeoutError):
            await producer.send_and_wait("topic-a", b"x", timeout=0.1)


@pytest.mark.asyncio
async def test_buffer_full_retries_once_then_succeeds(mock_producer):
    """First produce raises BufferError; after a brief poll, retry succeeds."""
    calls = []

    def _produce(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise BufferError("Queue full")
        # second call succeeds (no return value needed)

    mock_producer.produce.side_effect = _produce

    async with AsyncKafkaProducer("localhost:9092") as producer:
        await producer.send("topic-a", b"payload")

    assert len(calls) == 2  # one BufferError, one retry that lands


@pytest.mark.asyncio
async def test_buffer_full_twice_raises(mock_producer):
    """If the queue stays full after a poll, raise BufferError to the caller."""

    def _produce(**kwargs):
        raise BufferError("Queue still full")

    mock_producer.produce.side_effect = _produce

    async with AsyncKafkaProducer("localhost:9092") as producer:
        with pytest.raises(BufferError):
            await producer.send("topic-a", b"payload")
