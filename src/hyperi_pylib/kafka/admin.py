# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/admin.py
# Purpose:   Kafka admin operations for topic configuration changes
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka admin operations for topic configuration changes.

Provides high-level methods for common admin operations:
- Increase partition count
- Set retention policy (retention.ms)
- Set cleanup policy (delete, compact, compact,delete)
- Alter arbitrary topic configuration
- Reset consumer group offsets (by timestamp, earliest, latest)

Uses confluent-kafka AdminClient with incremental_alter_configs
to avoid resetting unspecified configs to defaults.

Reference:
https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from confluent_kafka import Consumer, ConsumerGroupTopicPartitions, TopicPartition
from confluent_kafka.admin import (
    AdminClient,
    ConfigResource,
    NewPartitions,
    ResourceType,
)

from .config import ADMIN_DEFAULTS, merge_config


class KafkaAdminError(Exception):
    """Kafka admin operation error."""


CleanupPolicy = Literal["delete", "compact", "compact,delete"]


class KafkaAdmin:
    """
    Kafka admin client for topic configuration changes.

    Provides high-level methods for common admin operations.

    Args:
        config: Either bootstrap.servers string or full config dict
        verify_ssl: If False, disable SSL certificate verification

    Example:
        admin = KafkaAdmin("localhost:9092")

        # Increase partitions
        admin.increase_partitions("my-topic", 12)

        # Set retention to 7 days
        admin.set_retention("my-topic", days=7)

        # Set cleanup policy to compact
        admin.set_cleanup_policy("my-topic", "compact")

        # Get current config
        config = admin.get_topic_config("my-topic")
        print(f"Retention: {config['retention.ms']}ms")
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        verify_ssl: bool = True,
    ):
        # Normalize config to dict
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        self._config = merge_config(config, ADMIN_DEFAULTS, verify_ssl=verify_ssl)
        self._admin = AdminClient(self._config)

    def __repr__(self) -> str:
        from .config import mask_credentials

        return f"KafkaAdmin(config={mask_credentials(self._config)!r})"

    def __enter__(self) -> KafkaAdmin:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def close(self) -> None:
        """Close the admin client (no-op for AdminClient)."""

    # =========================================================================
    # Partition Operations
    # =========================================================================

    def increase_partitions(
        self,
        topic: str,
        new_total_count: int,
        timeout: float = 30.0,
    ) -> None:
        """
        Increase the number of partitions for a topic.

        Note: Partitions can only be increased, not decreased.
        Note: This may cause message reordering for keyed messages.

        Args:
            topic: Topic name
            new_total_count: New total partition count (must be > current)
            timeout: Operation timeout in seconds

        Raises:
            KafkaAdminError: If operation fails
        """
        new_partitions = [NewPartitions(topic, new_total_count)]
        futures = self._admin.create_partitions(new_partitions, request_timeout=timeout)

        for topic_name, future in futures.items():
            try:
                future.result()
            except Exception as e:
                raise KafkaAdminError(f"Failed to increase partitions for {topic_name}: {e}") from e

    # =========================================================================
    # Retention Operations
    # =========================================================================

    def set_retention(
        self,
        topic: str,
        *,
        ms: int | None = None,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        days: int | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Set retention.ms for a topic.

        Only one time unit should be specified.

        Args:
            topic: Topic name
            ms: Retention in milliseconds
            seconds: Retention in seconds
            minutes: Retention in minutes
            hours: Retention in hours
            days: Retention in days
            timeout: Operation timeout in seconds

        Raises:
            KafkaAdminError: If operation fails
            ValueError: If no time unit or multiple units specified

        Example:
            admin.set_retention("my-topic", days=7)
            admin.set_retention("my-topic", hours=24)
            admin.set_retention("my-topic", ms=604800000)
        """
        # Calculate retention in ms
        retention_ms = None
        specified = 0

        if ms is not None:
            retention_ms = ms
            specified += 1
        if seconds is not None:
            retention_ms = seconds * 1000
            specified += 1
        if minutes is not None:
            retention_ms = minutes * 60 * 1000
            specified += 1
        if hours is not None:
            retention_ms = hours * 60 * 60 * 1000
            specified += 1
        if days is not None:
            retention_ms = days * 24 * 60 * 60 * 1000
            specified += 1

        if specified == 0:
            raise ValueError("Must specify one of: ms, seconds, minutes, hours, days")
        if specified > 1:
            raise ValueError("Only one time unit should be specified")

        self.alter_config(topic, {"retention.ms": str(retention_ms)}, timeout=timeout)

    def set_cleanup_policy(
        self,
        topic: str,
        policy: CleanupPolicy,
        timeout: float = 30.0,
    ) -> None:
        """
        Set cleanup.policy for a topic.

        Args:
            topic: Topic name
            policy: "delete", "compact", or "compact,delete"
            timeout: Operation timeout in seconds

        Raises:
            KafkaAdminError: If operation fails

        Example:
            # Delete old messages based on retention
            admin.set_cleanup_policy("my-topic", "delete")

            # Compact by key (keep latest per key)
            admin.set_cleanup_policy("my-topic", "compact")

            # Both (compact first, then delete old)
            admin.set_cleanup_policy("my-topic", "compact,delete")
        """
        self.alter_config(topic, {"cleanup.policy": policy}, timeout=timeout)

    # =========================================================================
    # Generic Config Operations
    # =========================================================================

    def get_topic_config(
        self,
        topic: str,
        timeout: float = 30.0,
    ) -> dict[str, str]:
        """
        Get current configuration for a topic.

        Args:
            topic: Topic name
            timeout: Operation timeout in seconds

        Returns:
            Dict of config_name -> value

        Raises:
            KafkaAdminError: If operation fails
        """
        resource = ConfigResource(ResourceType.TOPIC, topic)
        futures = self._admin.describe_configs([resource], request_timeout=timeout)

        for res, future in futures.items():
            try:
                result = future.result()
                # result is dict[str, ConfigEntry] - iterate values to get entries
                return {entry.name: entry.value for entry in result.values()}
            except Exception as e:
                raise KafkaAdminError(f"Failed to get config for {topic}: {e}") from e

        return {}

    def alter_config(
        self,
        topic: str,
        config: dict[str, str],
        timeout: float = 30.0,
    ) -> None:
        """
        Alter topic configuration.

        Note: Uses incremental alter to avoid resetting unspecified
        configs to their defaults.

        Args:
            topic: Topic name
            config: Dict of config_name -> value to set
            timeout: Operation timeout in seconds

        Raises:
            KafkaAdminError: If operation fails

        Example:
            admin.alter_config("my-topic", {
                "retention.ms": "604800000",
                "max.message.bytes": "1048576",
            })
        """
        # incremental_alter_configs preserves unspecified keys; the
        # legacy alter_configs reset everything not in the request to
        # defaults, which silently wiped customised retention / cleanup
        # policy / etc. set_config supplies the upserts.
        resource = ConfigResource(ResourceType.TOPIC, topic, set_config=config)
        futures = self._admin.incremental_alter_configs([resource], request_timeout=timeout)

        for res, future in futures.items():
            try:
                future.result()
            except Exception as e:
                raise KafkaAdminError(f"Failed to alter config for {topic}: {e}") from e

    # =========================================================================
    # Consumer Group Offset Operations
    # =========================================================================

    def _get_partition_count(self, topic: str) -> int:
        """Get the number of partitions for a topic."""
        metadata = self._admin.list_topics(topic)
        if topic not in metadata.topics:
            raise KafkaAdminError(f"Topic {topic} not found")
        return len(metadata.topics[topic].partitions)

    def reset_offsets_to_timestamp(
        self,
        group_id: str,
        topic: str,
        timestamp_ms: int,
        timeout: float = 30.0,
    ) -> dict[int, int]:
        """
        Reset consumer group offsets to a specific timestamp.

        Finds the offset of the first message with timestamp >= timestamp_ms
        for each partition and commits those offsets.

        Args:
            group_id: Consumer group ID
            topic: Topic name
            timestamp_ms: Unix timestamp in milliseconds
            timeout: Operation timeout in seconds

        Returns:
            Dict of partition -> new offset

        Raises:
            KafkaAdminError: If operation fails

        Example:
            # Reset to messages from Jan 1, 2024 00:00 UTC
            admin.reset_offsets_to_timestamp(
                "my-group",
                "my-topic",
                timestamp_ms=1704067200000,
            )
        """
        partition_count = self._get_partition_count(topic)

        # Create a temporary consumer to use offsets_for_times
        consumer_config = self._config.copy()
        consumer_config["group.id"] = group_id
        consumer_config["enable.auto.commit"] = False
        consumer = Consumer(consumer_config)

        try:
            # Create TopicPartitions with target timestamp
            partitions = [TopicPartition(topic, p, timestamp_ms) for p in range(partition_count)]

            # Get offsets for the timestamps
            result_partitions = consumer.offsets_for_times(partitions, timeout=timeout)

            # Build new offsets
            new_offsets = {}
            commit_partitions = []
            for tp in result_partitions:
                if tp.offset >= 0:
                    new_offsets[tp.partition] = tp.offset
                    commit_partitions.append(TopicPartition(topic, tp.partition, tp.offset))

            if not commit_partitions:
                raise KafkaAdminError(f"No valid offsets found for timestamp {timestamp_ms} on {topic}")

            # Commit the new offsets via AdminClient
            group_partitions = ConsumerGroupTopicPartitions(group_id, commit_partitions)
            futures = self._admin.alter_consumer_group_offsets([group_partitions], request_timeout=timeout)

            for group, future in futures.items():
                try:
                    future.result()
                except Exception as e:
                    raise KafkaAdminError(f"Failed to reset offsets for {group_id}: {e}") from e

            return new_offsets

        finally:
            consumer.close()

    def reset_offsets_to_time(
        self,
        group_id: str,
        topic: str,
        time: datetime,
        timeout: float = 30.0,
    ) -> dict[int, int]:
        """
        Reset consumer group offsets to a specific datetime.

        Convenience wrapper around reset_offsets_to_timestamp.

        Args:
            group_id: Consumer group ID
            topic: Topic name
            time: Datetime object (should be timezone-aware)
            timeout: Operation timeout in seconds

        Returns:
            Dict of partition -> new offset

        Raises:
            KafkaAdminError: If operation fails

        Example:
            from datetime import datetime, timezone

            target = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            admin.reset_offsets_to_time("my-group", "my-topic", target)
        """
        timestamp_ms = int(time.timestamp() * 1000)
        return self.reset_offsets_to_timestamp(group_id, topic, timestamp_ms, timeout=timeout)

    def reset_offsets_to_earliest(
        self,
        group_id: str,
        topic: str,
        timeout: float = 30.0,
    ) -> dict[int, int]:
        """
        Reset consumer group offsets to earliest (beginning).

        Args:
            group_id: Consumer group ID
            topic: Topic name
            timeout: Operation timeout in seconds

        Returns:
            Dict of partition -> new offset (low watermark)

        Raises:
            KafkaAdminError: If operation fails

        Example:
            # Reprocess all messages from the beginning
            admin.reset_offsets_to_earliest("my-group", "my-topic")
        """
        partition_count = self._get_partition_count(topic)

        # Create a temporary consumer to get watermarks
        consumer_config = self._config.copy()
        consumer_config["group.id"] = group_id
        consumer_config["enable.auto.commit"] = False
        consumer = Consumer(consumer_config)

        try:
            new_offsets = {}
            commit_partitions = []

            for p in range(partition_count):
                low, high = consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=timeout)
                new_offsets[p] = low
                commit_partitions.append(TopicPartition(topic, p, low))

            # Commit the new offsets via AdminClient
            group_partitions = ConsumerGroupTopicPartitions(group_id, commit_partitions)
            futures = self._admin.alter_consumer_group_offsets([group_partitions], request_timeout=timeout)

            for group, future in futures.items():
                try:
                    future.result()
                except Exception as e:
                    raise KafkaAdminError(f"Failed to reset offsets for {group_id}: {e}") from e

            return new_offsets

        finally:
            consumer.close()

    def reset_offsets_to_latest(
        self,
        group_id: str,
        topic: str,
        timeout: float = 30.0,
    ) -> dict[int, int]:
        """
        Reset consumer group offsets to latest (end).

        Args:
            group_id: Consumer group ID
            topic: Topic name
            timeout: Operation timeout in seconds

        Returns:
            Dict of partition -> new offset (high watermark)

        Raises:
            KafkaAdminError: If operation fails

        Example:
            # Skip all existing messages
            admin.reset_offsets_to_latest("my-group", "my-topic")
        """
        partition_count = self._get_partition_count(topic)

        # Create a temporary consumer to get watermarks
        consumer_config = self._config.copy()
        consumer_config["group.id"] = group_id
        consumer_config["enable.auto.commit"] = False
        consumer = Consumer(consumer_config)

        try:
            new_offsets = {}
            commit_partitions = []

            for p in range(partition_count):
                low, high = consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=timeout)
                new_offsets[p] = high
                commit_partitions.append(TopicPartition(topic, p, high))

            # Commit the new offsets via AdminClient
            group_partitions = ConsumerGroupTopicPartitions(group_id, commit_partitions)
            futures = self._admin.alter_consumer_group_offsets([group_partitions], request_timeout=timeout)

            for group, future in futures.items():
                try:
                    future.result()
                except Exception as e:
                    raise KafkaAdminError(f"Failed to reset offsets for {group_id}: {e}") from e

            return new_offsets

        finally:
            consumer.close()


# =============================================================================
# BACKLOG: JSON Key-Value Offset Seek
# =============================================================================
#
# Future feature: seek_to_json_match()
#
# Seek to first message where a nested JSON field matches a value.
# Unlike timestamp-based seek (which uses Kafka's built-in index),
# this requires reading and parsing actual message content.
#
# Proposed API:
#     def seek_to_json_match(
#         self,
#         group_id: str,
#         topic: str,
#         json_path: str,           # e.g., "user.id" or "event.type"
#         value: Any,               # Match value
#         *,
#         timeout: float = 60.0,    # Max search time
#         max_messages: int = 100_000,  # Safety limit
#         cancel_event: threading.Event | None = None,
#     ) -> dict[int, int] | None:
#
# Implementation considerations:
# - No index: Worst case is full topic scan
# - Parallel partition search for performance
# - Cancellation support via threading.Event
# - Timeout handling to prevent hangs
# - Graceful handling of non-JSON messages
#
# Estimated effort: 1-2 days for production-ready implementation
