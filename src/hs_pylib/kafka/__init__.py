# Project:   hs-pylib
# File:      src/hs_pylib/kafka/__init__.py
# Purpose:   Kafka client library with corporate defaults
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
hs_pylib.kafka - Kafka client library with corporate defaults.

This module provides Kafka clients (producer, consumer, admin) with:
- Corporate defaults for reliability and performance
- Both sync and async interfaces
- Sampling utilities for data discovery
- Schema analysis for JSON messages
- Consumer group lag monitoring (no JMX required)

Sync usage (CLI, batch jobs):
    from hs_pylib.kafka import KafkaClient, KafkaConsumer, KafkaProducer

    client = KafkaClient({"bootstrap.servers": "localhost:9092"})
    topics = client.list_topics()

Async usage (FastAPI, async apps):
    from hs_pylib.kafka import AsyncKafkaClient, AsyncKafkaConsumer

    async with AsyncKafkaClient({"bootstrap.servers": "localhost:9092"}) as client:
        topics = await client.list_topics()
"""

# Config and defaults
# Admin operations
from .admin import KafkaAdmin, KafkaAdminError

# Async clients
from .async_client import AsyncKafkaClient
from .async_consumer import AsyncKafkaConsumer
from .async_producer import AsyncKafkaProducer

# Sync clients
from .client import (
    ConsumerGroupNotFoundError,
    KafkaClient,
    TopicNotFoundError,
)
from .config import (
    ADMIN_DEFAULTS,
    CONSUMER_DEFAULTS,
    PRODUCER_DEFAULTS,
    config_from_env,
    config_from_file,
    get_default_config,
    merge_config,
)
from .consumer import (
    KafkaConsumer,
    KafkaConsumerError,
)

# Health monitoring
from .health import (
    HealthCheckResult,
    HealthIssue,
    KafkaConsumerHealth,
)

# Metrics collection
from .metrics import (
    KafkaMetricsCollector,
    create_stats_callback,
)
from .producer import KafkaProducer

# Read-only client
from .readonly import ReadOnlyKafkaClient

# Sampling utilities
from .sampling import (
    partition_sample,
    reservoir_sample,
    time_bounded_consume,
)

# Schema analysis
from .schema import (
    AnalysisResult,
    FieldStats,
    SchemaAnalyser,
)

# Types
from .types import (
    ConsumerGroupInfo,
    ConsumerGroupMember,
    ConsumerGroupMetadata,
    Message,
    PartitionInfo,
    PartitionLag,
    TopicInfo,
    TopicMetadata,
)

__all__ = [
    # Config
    "PRODUCER_DEFAULTS",
    "CONSUMER_DEFAULTS",
    "ADMIN_DEFAULTS",
    "merge_config",
    "config_from_env",
    "config_from_file",
    "get_default_config",
    # Types
    "Message",
    "TopicInfo",
    "PartitionInfo",
    "TopicMetadata",
    "ConsumerGroupInfo",
    "ConsumerGroupMember",
    "ConsumerGroupMetadata",
    "PartitionLag",
    # Sync clients
    "KafkaClient",
    "KafkaConsumer",
    "KafkaProducer",
    # Async clients
    "AsyncKafkaClient",
    "AsyncKafkaConsumer",
    "AsyncKafkaProducer",
    # Exceptions
    "TopicNotFoundError",
    "ConsumerGroupNotFoundError",
    "KafkaConsumerError",
    # Sampling
    "reservoir_sample",
    "time_bounded_consume",
    "partition_sample",
    # Schema
    "SchemaAnalyser",
    "AnalysisResult",
    "FieldStats",
    # Metrics
    "KafkaMetricsCollector",
    "create_stats_callback",
    # Health monitoring
    "KafkaConsumerHealth",
    "HealthCheckResult",
    "HealthIssue",
    # Read-only client
    "ReadOnlyKafkaClient",
    # Admin operations
    "KafkaAdmin",
    "KafkaAdminError",
]
