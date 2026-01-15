# Project:   hs-pylib
# File:      src/hs_pylib/kafka/async_client.py
# Purpose:   Async Kafka admin client wrapper
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Async Kafka admin client wrapper.

Uses ThreadPoolExecutor to provide async interface to
the synchronous confluent-kafka AdminClient.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from confluent_kafka import TopicPartition
from confluent_kafka.admin import AdminClient

from .config import ADMIN_DEFAULTS, CONSUMER_DEFAULTS, merge_config
from .types import PartitionInfo, TopicInfo, TopicMetadata


class AsyncKafkaClient:
    """
    Async Kafka admin client.

    Wraps KafkaClient with async methods using ThreadPoolExecutor.

    Args:
        config: Either bootstrap.servers string or full config dict
        verify_ssl: If False, disable SSL certificate verification
        executor: Optional ThreadPoolExecutor (uses default if None)

    Example:
        async with AsyncKafkaClient("localhost:9092") as client:
            topics = await client.list_topics()
            for topic in topics:
                print(topic.name)
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        verify_ssl: bool = True,
        executor: ThreadPoolExecutor | None = None,
    ):
        # Normalize config to dict
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        self._user_config = config.copy()
        self._config = merge_config(config, ADMIN_DEFAULTS, verify_ssl=verify_ssl)
        self._verify_ssl = verify_ssl

        self._admin = AdminClient(self._config)
        self._executor = executor or ThreadPoolExecutor(max_workers=4)
        self._owns_executor = executor is None

    async def __aenter__(self) -> AsyncKafkaClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the client."""
        if self._owns_executor:
            self._executor.shutdown(wait=False)

    async def list_topics(self, include_internal: bool = False) -> list[TopicInfo]:
        """List all topics in the cluster."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._list_topics_sync,
            include_internal,
        )

    def _list_topics_sync(self, include_internal: bool) -> list[TopicInfo]:
        """Sync implementation of list_topics."""
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

    async def describe_topic(self, topic: str) -> TopicMetadata:
        """Get detailed metadata for a topic."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._describe_topic_sync,
            topic,
        )

    def _describe_topic_sync(self, topic: str) -> TopicMetadata:
        """Sync implementation of describe_topic."""
        from confluent_kafka import Consumer

        metadata = self._admin.list_topics(topic)

        if topic not in metadata.topics:
            from .client import TopicNotFoundError

            raise TopicNotFoundError(topic)

        topic_meta = metadata.topics[topic]

        # Get watermarks
        base_config = self._user_config.copy()
        base_config["group.id"] = f"hs-pylib-async-{id(self)}"
        consumer_config = merge_config(base_config, CONSUMER_DEFAULTS, verify_ssl=self._verify_ssl)

        consumer = Consumer(consumer_config)
        try:
            partitions = []
            for partition_id, partition_meta in topic_meta.partitions.items():
                tp = TopicPartition(topic, partition_id)
                low, high = consumer.get_watermark_offsets(tp)
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
        finally:
            consumer.close()

        return TopicMetadata(
            name=topic,
            partitions=partitions,
            config={},
        )

    async def get_watermark_offsets(self, topic: str) -> dict[int, tuple[int, int]]:
        """Get low and high watermarks for all partitions."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._get_watermarks_sync,
            topic,
        )

    def _get_watermarks_sync(self, topic: str) -> dict[int, tuple[int, int]]:
        """Sync implementation of get_watermark_offsets."""
        from confluent_kafka import Consumer

        from .client import TopicNotFoundError

        metadata = self._admin.list_topics(topic)
        if topic not in metadata.topics:
            raise TopicNotFoundError(topic)

        partition_ids = list(metadata.topics[topic].partitions.keys())

        base_config = self._user_config.copy()
        base_config["group.id"] = f"hs-pylib-async-wm-{id(self)}"
        consumer_config = merge_config(base_config, CONSUMER_DEFAULTS, verify_ssl=self._verify_ssl)

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

    async def get_topic_message_count(self, topic: str) -> int:
        """Get estimated total message count for a topic."""
        watermarks = await self.get_watermark_offsets(topic)
        return sum(high - low for low, high in watermarks.values())
