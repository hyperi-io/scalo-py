# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/readonly.py
# Purpose:   Read-only Kafka client (no produce capability)
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Read-only Kafka client.

Provides a restricted Kafka client that can only perform read operations
(list topics, get offsets, check lag) but cannot produce messages.

This is useful for:
- Metrics collection with admin credentials
- Discovery/monitoring without risk of data modification
- Enforcing read-only access even with admin credentials
"""

from __future__ import annotations

from typing import Any

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient

from .config import ADMIN_DEFAULTS, CONSUMER_DEFAULTS, merge_config
from .types import PartitionInfo, TopicInfo, TopicMetadata


class TopicNotFoundError(Exception):
    """Topic does not exist."""

    def __init__(self, topic: str):
        self.topic = topic
        super().__init__(f"Topic not found: {topic}")


class ReadOnlyKafkaClient:
    """
    Read-only Kafka client.

    Provides only read operations - no ability to produce messages.
    Use this when you need to monitor/discover Kafka topics without
    any risk of modifying data, even if credentials have write access.

    Args:
        config: Either bootstrap.servers string or full config dict
        verify_ssl: If False, disable SSL certificate verification

    Example:
        # Safe metrics collection loop
        client = ReadOnlyKafkaClient(config_from_env())
        while True:
            for topic in client.list_topics():
                count = client.get_topic_message_count(topic.name)
                print(f"{topic.name}: {count} messages")
            time.sleep(60)
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        verify_ssl: bool = True,
    ):
        # Normalize config to dict
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        self._user_config = config.copy()
        self._config = merge_config(config, ADMIN_DEFAULTS, verify_ssl=verify_ssl)
        self._verify_ssl = verify_ssl
        self._admin = AdminClient(self._config)

    def __enter__(self) -> ReadOnlyKafkaClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def close(self) -> None:
        """Close the client (no-op for AdminClient)."""

    # =========================================================================
    # Topic Operations (READ ONLY)
    # =========================================================================

    def list_topics(self, include_internal: bool = False) -> list[TopicInfo]:
        """
        List all topics in the cluster.

        Args:
            include_internal: Include internal topics (e.g., __consumer_offsets)

        Returns:
            List of TopicInfo objects
        """
        metadata = self._admin.list_topics()

        topics = []
        for name, topic_meta in metadata.topics.items():
            is_internal = name.startswith("_")

            if not include_internal and is_internal:
                continue

            topics.append(
                TopicInfo(
                    name=name,
                    partition_count=len(topic_meta.partitions),
                    is_internal=is_internal,
                )
            )

        return topics

    def describe_topic(self, topic: str) -> TopicMetadata:
        """
        Get detailed metadata for a topic.

        Args:
            topic: Topic name

        Returns:
            TopicMetadata with partition details and watermarks

        Raises:
            TopicNotFoundError: If topic doesn't exist
        """
        metadata = self._admin.list_topics(topic)

        if topic not in metadata.topics:
            raise TopicNotFoundError(topic)

        topic_meta = metadata.topics[topic]

        # Get watermarks
        watermarks = self._get_watermarks_internal(topic, list(topic_meta.partitions.keys()))

        partitions = []
        for partition_id, partition_meta in topic_meta.partitions.items():
            low, high = watermarks.get(partition_id, (0, 0))
            partitions.append(
                PartitionInfo(
                    partition=partition_id,
                    leader=partition_meta.leader,
                    replicas=list(partition_meta.replicas),
                    isrs=list(partition_meta.isrs),
                    low_watermark=low,
                    high_watermark=high,
                )
            )

        return TopicMetadata(
            name=topic,
            partitions=partitions,
            config={},
        )

    # =========================================================================
    # Offset Operations (READ ONLY)
    # =========================================================================

    def get_watermark_offsets(self, topic: str) -> dict[int, tuple[int, int]]:
        """
        Get low and high watermarks for all partitions.

        Args:
            topic: Topic name

        Returns:
            Dict of partition -> (low_watermark, high_watermark)
        """
        metadata = self._admin.list_topics(topic)
        if topic not in metadata.topics:
            raise TopicNotFoundError(topic)

        partition_ids = list(metadata.topics[topic].partitions.keys())
        return self._get_watermarks_internal(topic, partition_ids)

    def get_topic_message_count(self, topic: str) -> int:
        """
        Get estimated total message count for a topic.

        Args:
            topic: Topic name

        Returns:
            Estimated total message count
        """
        watermarks = self.get_watermark_offsets(topic)
        return sum(high - low for low, high in watermarks.values())

    def get_consumer_lag(
        self,
        group_id: str,
        topic: str,
    ) -> dict[int, int]:
        """
        Get consumer group lag per partition.

        Args:
            group_id: Consumer group ID
            topic: Topic name

        Returns:
            Dict of partition -> lag (messages behind)
        """
        metadata = self._admin.list_topics(topic)
        if topic not in metadata.topics:
            raise TopicNotFoundError(topic)

        partition_ids = list(metadata.topics[topic].partitions.keys())

        # Create read-only consumer just for offset lookup
        base_config = self._user_config.copy()
        base_config["group.id"] = group_id

        consumer_config = merge_config(
            base_config,
            CONSUMER_DEFAULTS,
            verify_ssl=self._verify_ssl,
        )

        consumer = Consumer(consumer_config)
        try:
            tps = [TopicPartition(topic, p) for p in partition_ids]
            committed = consumer.committed(tps)
            committed_map = {tp.partition: tp.offset for tp in committed}

            watermarks = {}
            for partition_id in partition_ids:
                tp = TopicPartition(topic, partition_id)
                low, high = consumer.get_watermark_offsets(tp)
                watermarks[partition_id] = (low, high)

            lag = {}
            for partition_id in partition_ids:
                committed_offset = committed_map.get(partition_id, -1)
                _, high_watermark = watermarks[partition_id]

                if committed_offset < 0:
                    lag[partition_id] = high_watermark
                else:
                    lag[partition_id] = high_watermark - committed_offset

            return lag
        finally:
            consumer.close()

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _get_watermarks_internal(
        self,
        topic: str,
        partition_ids: list[int],
    ) -> dict[int, tuple[int, int]]:
        """Get watermarks using a temporary consumer."""
        base_config = self._user_config.copy()
        base_config["group.id"] = f"hyperi-pylib-readonly-{id(self)}"

        consumer_config = merge_config(
            base_config,
            CONSUMER_DEFAULTS,
            verify_ssl=self._verify_ssl,
        )

        consumer = Consumer(consumer_config)
        try:
            watermarks = {}
            for partition_id in partition_ids:
                tp = TopicPartition(topic, partition_id)
                low, high = consumer.get_watermark_offsets(tp)
                watermarks[partition_id] = (low, high)
            return watermarks
        finally:
            consumer.close()
