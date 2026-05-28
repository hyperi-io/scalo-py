#  Project:   hyperi-pylib
#  File:      tests/unit/test_kafka_buffer_full_real.py
#  Purpose:   Trigger real librdkafka BufferError without a broker
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Real librdkafka BufferError + send_and_wait timeout, no broker."""

from __future__ import annotations

import asyncio

import pytest

from hyperi_pylib.kafka.async_producer import AsyncKafkaProducer


def _producer_config() -> dict:
    # Unreachable broker + cap=1: second produce raises BufferError locally.
    return {
        "bootstrap.servers": "127.0.0.1:1",
        "queue.buffering.max.messages": 1,
        "linger.ms": 0,
        "message.timeout.ms": 1000,
    }


@pytest.mark.asyncio
async def test_real_librdkafka_buffer_error_propagates_when_unrecoverable():
    """Cap=1 + no broker: 2nd send raises BufferError after retry fails."""
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
    """send_and_wait against unreachable broker raises asyncio.TimeoutError."""
    producer = AsyncKafkaProducer({"bootstrap.servers": "127.0.0.1:1"})
    try:
        with pytest.raises(asyncio.TimeoutError):
            await producer.send_and_wait("test-topic", b"x", timeout=0.3)
    finally:
        try:
            await asyncio.wait_for(producer.flush(timeout=0.1), timeout=0.5)
        except (TimeoutError, Exception):
            pass
