#  Project:   hyperi-pylib
#  File:      tests/unit/test_kafka_buffer_full_real.py
#  Purpose:   Trigger real librdkafka BufferError without a broker
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""T10: exercise the AsyncKafkaProducer BufferError-retry path against
a REAL confluent_kafka.Producer instance. No mocks of producer
internals -- librdkafka's local message queue fills regardless of
whether the broker is reachable, so a low ``queue.buffering.max.messages``
makes the second produce() call raise BufferError naturally.

Replaces the synthetic mock-based BufferError tests in
test_kafka_async_producer_delivery.py for higher confidence that the
code path matches the real library behaviour."""

from __future__ import annotations

import asyncio

import pytest

from hyperi_pylib.kafka.async_producer import AsyncKafkaProducer


def _producer_config() -> dict:
    # Unreachable broker -- librdkafka still accepts the queue
    # operation locally. queue.buffering.max.messages=1 means the
    # second produce() raises BufferError immediately, no broker
    # interaction needed.
    # message.timeout.ms must exceed linger.ms; both kept small for
    # fast test teardown.
    return {
        "bootstrap.servers": "127.0.0.1:1",
        "queue.buffering.max.messages": 1,
        "linger.ms": 0,
        "message.timeout.ms": 1000,
    }


@pytest.mark.asyncio
async def test_real_librdkafka_buffer_error_propagates_when_unrecoverable():
    """First produce queues (fills cap=1), second hits BufferError.
    Our _send_sync polls + retries once -- but without a broker
    available to drain the queue, the retry also hits BufferError.
    Contract: that second BufferError must propagate cleanly to the
    caller rather than be swallowed.

    Validates that the BufferError handling in
    src/hyperi_pylib/kafka/async_producer.py:_send_sync matches what
    real librdkafka actually raises (KafkaError code _MSG_TIMED_OUT
    eventually, but BufferError synchronously at produce() call when
    the local queue is full)."""
    producer = AsyncKafkaProducer(_producer_config())
    try:
        await producer.send("test-topic", b"first-message-payload")
        with pytest.raises(BufferError, match="Queue full"):
            await producer.send("test-topic", b"second-message-payload")
    finally:
        try:
            await asyncio.wait_for(producer.flush(timeout=0.1), timeout=0.5)
        except (TimeoutError, Exception):
            pass


@pytest.mark.asyncio
async def test_real_librdkafka_send_and_wait_times_out_no_broker():
    """send_and_wait against an unreachable broker times out at the
    user-supplied deadline -- the delivery report never fires. Confirms
    the timeout primitive integrates with the real producer, not just
    a mock."""
    producer = AsyncKafkaProducer({"bootstrap.servers": "127.0.0.1:1"})
    try:
        with pytest.raises(asyncio.TimeoutError):
            await producer.send_and_wait("test-topic", b"x", timeout=0.3)
    finally:
        try:
            await asyncio.wait_for(producer.flush(timeout=0.1), timeout=0.5)
        except (TimeoutError, Exception):
            pass
