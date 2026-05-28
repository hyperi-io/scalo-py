# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/sampling.py
# Purpose:   Kafka message sampling utilities
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka message sampling utilities.

Provides functions for sampling messages from Kafka topics:
- Reservoir sampling for uniform random samples
- Time-bounded consumption for specific time ranges
- Per-partition sampling for representative samples
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .consumer import KafkaConsumer
    from .types import Message


def reservoir_sample(
    messages: Iterator[Message],
    k: int,
    seed: int | None = None,
) -> list[Message]:
    """
    Reservoir sampling for uniform random sample from stream.

    Uses Algorithm R (Vitter, 1985) to select k items uniformly
    at random from a stream of unknown length.

    Args:
        messages: Iterator of messages
        k: Number of messages to sample
        seed: Optional random seed for reproducibility

    Returns:
        List of k randomly sampled messages (or fewer if stream < k)
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    reservoir: list[Message] = []

    for i, msg in enumerate(messages):
        if i < k:
            # Fill reservoir
            reservoir.append(msg)
        else:
            # Replace with decreasing probability
            j = rng.randint(0, i)
            if j < k:
                reservoir[j] = msg

    return reservoir


def time_bounded_consume(
    consumer: KafkaConsumer,
    start_time: int,
    end_time: int,
    limit: int | None = None,
    timeout: float = 1.0,
) -> list[Message]:
    """
    Consume messages within a time range.

    Polls the consumer and collects messages with timestamps
    between start_time and end_time (inclusive).

    Args:
        consumer: KafkaConsumer instance (should already be subscribed)
        start_time: Start timestamp in milliseconds (inclusive)
        end_time: End timestamp in milliseconds (inclusive)
        limit: Maximum number of messages to return (None = no limit)
        timeout: Poll timeout in seconds

    Returns:
        List of messages within the time range
    """
    messages: list[Message] = []
    consecutive_nulls = 0
    max_consecutive_nulls = 3  # Stop after 3 consecutive empty polls

    while True:
        msg = consumer.poll(timeout=timeout)

        if msg is None:
            consecutive_nulls += 1
            if consecutive_nulls >= max_consecutive_nulls:
                break
            continue

        consecutive_nulls = 0

        # Check timestamp bounds
        if msg.timestamp < start_time:
            # Before start, skip
            continue

        if msg.timestamp > end_time:
            # Past end, stop
            break

        messages.append(msg)

        # Check limit
        if limit is not None and len(messages) >= limit:
            break

    return messages


def partition_sample(
    messages: Iterator[Message],
    n_per_partition: int,
    seed: int | None = None,
) -> dict[int, list[Message]]:
    """
    Sample n messages per partition using reservoir sampling.

    Collects messages and applies reservoir sampling independently
    to each partition for representative samples.

    Args:
        messages: Iterator of messages from multiple partitions
        n_per_partition: Number of messages to sample per partition
        seed: Optional random seed for reproducibility

    Returns:
        Dict of partition -> list of sampled messages
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    # Group messages by partition with reservoir sampling
    reservoirs: dict[int, list[Message]] = defaultdict(list)
    counts: dict[int, int] = defaultdict(int)

    for msg in messages:
        partition = msg.partition
        i = counts[partition]
        counts[partition] += 1

        if i < n_per_partition:
            reservoirs[partition].append(msg)
        else:
            j = rng.randint(0, i)
            if j < n_per_partition:
                reservoirs[partition][j] = msg

    return dict(reservoirs)
