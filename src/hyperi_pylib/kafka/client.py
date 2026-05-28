# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/client.py
# Purpose:   Kafka admin client with corporate defaults
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka admin client for topic and consumer group operations.

Provides admin operations without requiring JMX:
- List and describe topics
- Get watermark offsets and message counts
- Monitor consumer group lag
"""

from __future__ import annotations

from typing import Any

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient

from .config import ADMIN_DEFAULTS, CONSUMER_DEFAULTS, merge_config
from .types import (
    ConsumerGroupInfo,
    PartitionInfo,
    TopicInfo,
    TopicMetadata,
)


class TopicNotFoundError(Exception):
    """Topic does not exist."""

    def __init__(self, topic: str):
        self.topic = topic
        super().__init__(f"Topic not found: {topic}")


class ConsumerGroupNotFoundError(Exception):
    """Consumer group does not exist."""

    def __init__(self, group_id: str):
        self.group_id = group_id
        super().__init__(f"Consumer group not found: {group_id}")


class KafkaClient:
    """
    Kafka admin client with corporate defaults.

    Provides admin operations for topics and consumer groups.
    Uses librdkafka AdminClient internally.

    Args:
        config: Either bootstrap.servers string or full config dict
        verify_ssl: If False, disable SSL certificate verification

    Example:
        client = KafkaClient("localhost:9092")
        topics = client.list_topics()
        for topic in topics:
            print(f"{topic.name}: {topic.partition_count} partitions")
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        verify_ssl: bool = True,
    ):
        # Normalize config to dict
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        # Store original user config for creating consumers with same auth
        self._user_config = config.copy()

        # Merge with defaults
        self._config = merge_config(config, ADMIN_DEFAULTS, verify_ssl=verify_ssl)
        self._verify_ssl = verify_ssl

        # Create admin client
        self._admin = AdminClient(self._config)

    def __repr__(self) -> str:
        from .config import mask_credentials

        return f"KafkaClient(config={mask_credentials(self._config)!r})"

    def __enter__(self) -> KafkaClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass  # AdminClient doesn't need explicit cleanup

    def close(self) -> None:
        """Close the client (no-op for AdminClient)."""

    # =========================================================================
    # Topic Operations
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

        # Get watermarks for each partition
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
            config={},  # TODO: Fetch config via describe_configs if needed
        )

    # =========================================================================
    # Offset and Watermark Operations
    # =========================================================================

    def get_watermark_offsets(self, topic: str) -> dict[int, tuple[int, int]]:
        """
        Get low and high watermarks for all partitions.

        Args:
            topic: Topic name

        Returns:
            Dict of partition -> (low_watermark, high_watermark)
        """
        # Get partition list
        metadata = self._admin.list_topics(topic)
        if topic not in metadata.topics:
            raise TopicNotFoundError(topic)

        partition_ids = list(metadata.topics[topic].partitions.keys())
        return self._get_watermarks_internal(topic, partition_ids)

    def get_topic_message_count(self, topic: str) -> int:
        """
        Get estimated total message count for a topic.

        This is the sum of (high_watermark - low_watermark) for all partitions.
        Note: This may include messages that have been compacted/deleted.

        Args:
            topic: Topic name

        Returns:
            Estimated total message count
        """
        watermarks = self.get_watermark_offsets(topic)
        return sum(high - low for low, high in watermarks.values())

    def get_offsets_for_times(
        self,
        topic: str,
        timestamps: dict[int, int],
    ) -> dict[int, int]:
        """
        Get offsets for given timestamps per partition.

        Args:
            topic: Topic name
            timestamps: Dict of partition -> timestamp (milliseconds)

        Returns:
            Dict of partition -> offset
        """
        # Create consumer just for offset lookup (inherit SASL/SSL from user config)
        base_config = self._user_config.copy()
        base_config["group.id"] = f"hyperi-pylib-offset-lookup-{id(self)}"

        consumer_config = merge_config(
            base_config,
            CONSUMER_DEFAULTS,
            verify_ssl=self._verify_ssl,
        )

        consumer = Consumer(consumer_config)
        try:
            # Create TopicPartition list with timestamps
            tps = [TopicPartition(topic, partition, timestamp) for partition, timestamp in timestamps.items()]

            # Get offsets
            result = consumer.offsets_for_times(tps)

            return {tp.partition: tp.offset for tp in result}
        finally:
            consumer.close()

    # =========================================================================
    # Consumer Group Operations
    # =========================================================================

    def get_consumer_lag(
        self,
        group_id: str,
        topic: str,
    ) -> dict[int, int]:
        """
        Get consumer group lag per partition.

        Lag = high_watermark - committed_offset

        Args:
            group_id: Consumer group ID
            topic: Topic name

        Returns:
            Dict of partition -> lag (messages behind)
        """
        # Get partition list
        metadata = self._admin.list_topics(topic)
        if topic not in metadata.topics:
            raise TopicNotFoundError(topic)

        partition_ids = list(metadata.topics[topic].partitions.keys())

        # Create consumer to get committed offsets (inherit SASL/SSL from user config)
        base_config = self._user_config.copy()
        base_config["group.id"] = group_id

        consumer_config = merge_config(
            base_config,
            CONSUMER_DEFAULTS,
            verify_ssl=self._verify_ssl,
        )

        consumer = Consumer(consumer_config)
        try:
            # Create TopicPartition list
            tps = [TopicPartition(topic, p) for p in partition_ids]

            # Get committed offsets
            committed = consumer.committed(tps)
            committed_map = {tp.partition: tp.offset for tp in committed}

            # Get watermarks
            watermarks = {}
            for partition_id in partition_ids:
                tp = TopicPartition(topic, partition_id)
                low, high = consumer.get_watermark_offsets(tp)
                watermarks[partition_id] = (low, high)

            # Calculate lag
            lag = {}
            for partition_id in partition_ids:
                committed_offset = committed_map.get(partition_id, -1)
                _, high_watermark = watermarks[partition_id]

                if committed_offset < 0:
                    # No committed offset, full lag
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
        # Start with user config (includes SASL/SSL settings)
        base_config = self._user_config.copy()
        base_config["group.id"] = f"hyperi-pylib-watermark-{id(self)}"

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
