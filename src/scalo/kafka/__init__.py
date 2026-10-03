# Project:   scalo
# File:      src/scalo/kafka/__init__.py
# Purpose:   Kafka client library with corporate defaults
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
scalo.kafka - Kafka client library with corporate defaults.

This module provides Kafka clients (producer, consumer, admin) with:
- Corporate defaults for reliability and performance
- Both sync and async interfaces
- Sampling utilities for data discovery
- Schema analysis for JSON messages
- Consumer group lag monitoring (no JMX required)

Sync usage (CLI, batch jobs):
    from scalo.kafka import KafkaClient, KafkaConsumer, KafkaProducer

    client = KafkaClient({"bootstrap.servers": "localhost:9092"})
    topics = client.list_topics()

Async usage (FastAPI, async apps):
    from scalo.kafka import AsyncKafkaClient, AsyncKafkaConsumer

    async with AsyncKafkaClient({"bootstrap.servers": "localhost:9092"}) as client:
        topics = await client.list_topics()
"""

# Config and defaults
# Admin operations
# Opt-in STRICT credential profile. Kept namespaced
# (``scalo.kafka.contract.require(...)``) rather than flattened - it is
# POLICY layered on the vanilla facts above, not a fact itself.
from . import contract
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
    external_sasl_scram,
    get_default_config,
    internal_sasl_scram,
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

# Opt-in managed-Kafka provider auth presets (provider -> mechanism derivation)
# plus the full, open KafkaProvider abstraction (facts only - no policy).
from .providers import (
    AuthKind,
    KafkaProvider,
    KafkaProviderError,
    KnownProvider,
    MetadataMode,
    ProviderCapabilities,
    SchemaRegistry,
    provider_config,
)

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

# Tool config emission - "provider X in way Y, here is the config for tool
# Z" (kafbat-ui / kcat / librdkafka .properties).
from .toolconfig import (
    Connection,
    emit_kafbat_cluster,
    emit_kcat,
    emit_librdkafka_properties,
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
    "ADMIN_DEFAULTS",
    "CONSUMER_DEFAULTS",
    # Config
    "PRODUCER_DEFAULTS",
    "AnalysisResult",
    # Async clients
    "AsyncKafkaClient",
    "AsyncKafkaConsumer",
    "AsyncKafkaProducer",
    # Kafka provider abstraction (facts)
    "AuthKind",
    # Tool config emission
    "Connection",
    "ConsumerGroupInfo",
    "ConsumerGroupMember",
    "ConsumerGroupMetadata",
    "ConsumerGroupNotFoundError",
    "FieldStats",
    "HealthCheckResult",
    "HealthIssue",
    # Admin operations
    "KafkaAdmin",
    "KafkaAdminError",
    # Sync clients
    "KafkaClient",
    "KafkaConsumer",
    "KafkaConsumerError",
    # Health monitoring
    "KafkaConsumerHealth",
    # Metrics
    "KafkaMetricsCollector",
    "KafkaProducer",
    "KafkaProvider",
    "KafkaProviderError",
    "KnownProvider",
    # Types
    "Message",
    "MetadataMode",
    "PartitionInfo",
    "PartitionLag",
    "ProviderCapabilities",
    # Read-only client
    "ReadOnlyKafkaClient",
    # Schema
    "SchemaAnalyser",
    "SchemaRegistry",
    "TopicInfo",
    "TopicMetadata",
    # Exceptions
    "TopicNotFoundError",
    "config_from_env",
    "config_from_file",
    # Opt-in STRICT credential profile (submodule, not flattened)
    "contract",
    "create_stats_callback",
    "emit_kafbat_cluster",
    "emit_kcat",
    "emit_librdkafka_properties",
    "external_sasl_scram",
    "get_default_config",
    "internal_sasl_scram",
    "merge_config",
    "partition_sample",
    "provider_config",
    # Sampling
    "reservoir_sample",
    "time_bounded_consume",
]
