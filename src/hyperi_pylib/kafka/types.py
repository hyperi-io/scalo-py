# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/types.py
# Purpose:   Kafka type definitions
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka type definitions.

Provides dataclasses for Kafka messages, topic metadata, and consumer groups.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """
    Kafka message.

    Wraps a Kafka message with convenient accessor methods.
    """

    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes | None
    timestamp: int
    headers: list[tuple[str, bytes]] | None

    def value_as_json(self) -> dict[str, Any] | list | None:
        """
        Parse message value as JSON.

        Returns:
            Parsed JSON data, or None if parsing fails or value is None.
        """
        if self.value is None:
            return None
        try:
            return json.loads(self.value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def value_as_str(self, encoding: str = "utf-8") -> str | None:
        """
        Decode message value as string.

        Args:
            encoding: Character encoding to use (default: utf-8)

        Returns:
            Decoded string, or None if value is None.
        """
        if self.value is None:
            return None
        return self.value.decode(encoding)

    def key_as_str(self, encoding: str = "utf-8") -> str | None:
        """
        Decode message key as string.

        Args:
            encoding: Character encoding to use (default: utf-8)

        Returns:
            Decoded string, or None if key is None.
        """
        if self.key is None:
            return None
        return self.key.decode(encoding)


@dataclass
class TopicInfo:
    """
    Basic topic information.

    Lightweight info from list_topics().
    """

    name: str
    partition_count: int
    is_internal: bool = False


@dataclass
class PartitionInfo:
    """
    Partition information with watermarks.

    Includes replica info and offset watermarks.
    """

    partition: int
    leader: int
    replicas: list[int]
    isrs: list[int]  # In-sync replicas
    low_watermark: int = 0
    high_watermark: int = 0


@dataclass
class TopicMetadata:
    """
    Full topic metadata.

    Includes partition details and topic configuration.
    """

    name: str
    partitions: list[PartitionInfo]
    config: dict[str, str] = field(default_factory=dict)

    @property
    def partition_count(self) -> int:
        """Number of partitions."""
        return len(self.partitions)

    @property
    def total_messages(self) -> int:
        """Estimated total messages (sum of partition sizes)."""
        return sum(p.high_watermark - p.low_watermark for p in self.partitions)


@dataclass
class ConsumerGroupInfo:
    """
    Consumer group information.

    Basic info from list_consumer_groups().
    """

    group_id: str
    state: str  # Empty, Dead, PreparingRebalance, CompletingRebalance, Stable
    protocol_type: str  # Usually "consumer"
    members_count: int = 0


@dataclass
class ConsumerGroupMember:
    """
    Consumer group member information.
    """

    member_id: str
    client_id: str
    client_host: str
    assignments: list[tuple[str, list[int]]]  # List of (topic, partitions)


@dataclass
class ConsumerGroupMetadata:
    """
    Full consumer group metadata.

    Includes member details and assignments.
    """

    group_id: str
    state: str
    protocol_type: str
    protocol: str  # e.g., "range", "roundrobin"
    members: list[ConsumerGroupMember]
    coordinator: int  # Broker ID


@dataclass
class PartitionLag:
    """
    Consumer group lag for a single partition.
    """

    topic: str
    partition: int
    committed_offset: int
    high_watermark: int

    @property
    def lag(self) -> int:
        """Messages behind (high_watermark - committed_offset)."""
        if self.committed_offset < 0:
            # No committed offset, full lag
            return self.high_watermark
        return self.high_watermark - self.committed_offset
