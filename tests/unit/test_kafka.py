# Project:   hs-pylib
# File:      tests/unit/test_kafka.py
# Purpose:   Unit tests for hs_pylib.kafka module
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""Unit tests for hs_pylib.kafka module.

TDD approach: Write failing tests first, then implement to make them pass.
"""

import pytest

# =============================================================================
# Phase 1: Types and Config (Foundation)
# =============================================================================


class TestDefaults:
    """Tests for corporate default configurations."""

    def test_producer_defaults_has_acks_all(self):
        """Producer defaults should require all replicas to acknowledge."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS

        assert PRODUCER_DEFAULTS["acks"] == "all"

    def test_producer_defaults_no_idempotence(self):
        """Producer defaults should use at-least-once (no idempotence)."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS

        # At-least-once: acks=all + retries, but no idempotence
        assert "enable.idempotence" not in PRODUCER_DEFAULTS
        assert PRODUCER_DEFAULTS["acks"] == "all"
        assert PRODUCER_DEFAULTS["retries"] >= 1

    def test_producer_defaults_has_lz4_compression(self):
        """Producer defaults should use lz4 compression."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS

        assert PRODUCER_DEFAULTS["compression.type"] == "lz4"

    def test_producer_defaults_has_retries(self):
        """Producer defaults should have retry configuration."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS

        assert PRODUCER_DEFAULTS["retries"] >= 3

    def test_consumer_defaults_has_earliest_offset(self):
        """Consumer defaults should start from earliest offset."""
        from hs_pylib.kafka.config import CONSUMER_DEFAULTS

        assert CONSUMER_DEFAULTS["auto.offset.reset"] == "earliest"

    def test_consumer_defaults_has_auto_commit_disabled(self):
        """Consumer defaults should disable auto commit for manual control."""
        from hs_pylib.kafka.config import CONSUMER_DEFAULTS

        assert CONSUMER_DEFAULTS["enable.auto.commit"] is False

    def test_consumer_defaults_has_session_timeout(self):
        """Consumer defaults should have reasonable session timeout."""
        from hs_pylib.kafka.config import CONSUMER_DEFAULTS

        assert CONSUMER_DEFAULTS["session.timeout.ms"] >= 30000

    def test_admin_defaults_exist(self):
        """Admin defaults should exist."""
        from hs_pylib.kafka.config import ADMIN_DEFAULTS

        assert isinstance(ADMIN_DEFAULTS, dict)


class TestConfigMerge:
    """Tests for configuration merge logic."""

    def test_merge_config_applies_defaults(self):
        """Merge should apply defaults when no user config provided."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS, merge_config

        user_config = {"bootstrap.servers": "localhost:9092"}
        merged = merge_config(user_config, PRODUCER_DEFAULTS)

        assert merged["bootstrap.servers"] == "localhost:9092"
        assert merged["acks"] == "all"
        assert merged["retries"] >= 1  # At-least-once delivery

    def test_merge_config_user_overrides_defaults(self):
        """User config should override defaults."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS, merge_config

        user_config = {
            "bootstrap.servers": "localhost:9092",
            "acks": "1",  # Override default
        }
        merged = merge_config(user_config, PRODUCER_DEFAULTS)

        assert merged["acks"] == "1"  # User override wins
        assert merged["retries"] >= 1  # Default preserved

    def test_merge_config_preserves_user_keys(self):
        """Merge should preserve user-specific keys not in defaults."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS, merge_config

        user_config = {
            "bootstrap.servers": "localhost:9092",
            "client.id": "my-producer",  # Not in defaults
        }
        merged = merge_config(user_config, PRODUCER_DEFAULTS)

        assert merged["client.id"] == "my-producer"

    def test_verify_ssl_false_sets_librdkafka_config(self):
        """verify_ssl=False should set librdkafka SSL verification config."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS, merge_config

        user_config = {"bootstrap.servers": "localhost:9092"}
        merged = merge_config(user_config, PRODUCER_DEFAULTS, verify_ssl=False)

        assert merged["enable.ssl.certificate.verification"] == "false"

    def test_verify_ssl_true_by_default(self):
        """SSL verification should be enabled by default (not set explicitly)."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS, merge_config

        user_config = {"bootstrap.servers": "localhost:9092"}
        merged = merge_config(user_config, PRODUCER_DEFAULTS)

        # Should not be set, letting librdkafka use its default (true)
        assert "enable.ssl.certificate.verification" not in merged


import os


class TestConfigFromEnv:
    """Tests for environment-based configuration."""

    def test_config_from_env_reads_bootstrap_servers(self, monkeypatch):
        """config_from_env should read KAFKA_BOOTSTRAP_SERVERS."""
        from hs_pylib.kafka.config import config_from_env

        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.example.com:9092")
        config = config_from_env()

        assert config["bootstrap.servers"] == "kafka.example.com:9092"

    def test_config_from_env_reads_sasl_config(self, monkeypatch):
        """config_from_env should read SASL configuration."""
        from hs_pylib.kafka.config import config_from_env

        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT")
        monkeypatch.setenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256")
        monkeypatch.setenv("KAFKA_SASL_USERNAME", "admin")
        monkeypatch.setenv("KAFKA_SASL_PASSWORD", "secret123")

        config = config_from_env()

        assert config["security.protocol"] == "SASL_PLAINTEXT"
        assert config["sasl.mechanism"] == "SCRAM-SHA-256"
        assert config["sasl.username"] == "admin"
        assert config["sasl.password"] == "secret123"

    def test_config_from_env_reads_ssl_config(self, monkeypatch):
        """config_from_env should read SSL configuration."""
        from hs_pylib.kafka.config import config_from_env

        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9093")
        monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
        monkeypatch.setenv("KAFKA_SSL_ENDPOINT_IDENTIFICATION_ALGORITHM", "")

        config = config_from_env()

        assert config["security.protocol"] == "SASL_SSL"
        assert config["ssl.endpoint.identification.algorithm"] == ""

    def test_config_from_env_ignores_missing_vars(self, monkeypatch):
        """config_from_env should ignore unset environment variables."""
        from hs_pylib.kafka.config import config_from_env

        # Clear any existing KAFKA_ vars
        for key in list(os.environ.keys()):
            if key.startswith("KAFKA_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

        config = config_from_env()

        assert config == {"bootstrap.servers": "kafka:9092"}

    def test_config_from_env_custom_prefix(self, monkeypatch):
        """config_from_env should support custom prefix."""
        from hs_pylib.kafka.config import config_from_env

        monkeypatch.setenv("MY_KAFKA_BOOTSTRAP_SERVERS", "custom:9092")

        config = config_from_env(prefix="MY_KAFKA_")

        assert config["bootstrap.servers"] == "custom:9092"


class TestMessage:
    """Tests for Message dataclass."""

    def test_message_dataclass_fields(self):
        """Message should have expected fields."""
        from hs_pylib.kafka.types import Message

        msg = Message(
            topic="test-topic",
            partition=0,
            offset=100,
            key=b"key1",
            value=b'{"data": "test"}',
            timestamp=1234567890,
            headers=[("header1", b"value1")],
        )

        assert msg.topic == "test-topic"
        assert msg.partition == 0
        assert msg.offset == 100
        assert msg.key == b"key1"
        assert msg.value == b'{"data": "test"}'
        assert msg.timestamp == 1234567890
        assert msg.headers == [("header1", b"value1")]

    def test_message_value_as_json(self):
        """Message should parse JSON value."""
        from hs_pylib.kafka.types import Message

        msg = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b'{"name": "test", "count": 42}',
            timestamp=0,
            headers=None,
        )

        data = msg.value_as_json()
        assert data == {"name": "test", "count": 42}

    def test_message_value_as_json_returns_none_for_invalid(self):
        """Message should return None for invalid JSON."""
        from hs_pylib.kafka.types import Message

        msg = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b"not valid json",
            timestamp=0,
            headers=None,
        )

        assert msg.value_as_json() is None

    def test_message_value_as_str(self):
        """Message should decode value as string."""
        from hs_pylib.kafka.types import Message

        msg = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b"hello world",
            timestamp=0,
            headers=None,
        )

        assert msg.value_as_str() == "hello world"


class TestTopicTypes:
    """Tests for topic-related types."""

    def test_topic_info_dataclass(self):
        """TopicInfo should have name and partition count."""
        from hs_pylib.kafka.types import TopicInfo

        info = TopicInfo(name="my-topic", partition_count=3, is_internal=False)

        assert info.name == "my-topic"
        assert info.partition_count == 3
        assert info.is_internal is False

    def test_partition_info_dataclass(self):
        """PartitionInfo should have partition details."""
        from hs_pylib.kafka.types import PartitionInfo

        info = PartitionInfo(
            partition=0,
            leader=1,
            replicas=[1, 2, 3],
            isrs=[1, 2, 3],
            low_watermark=0,
            high_watermark=1000,
        )

        assert info.partition == 0
        assert info.leader == 1
        assert info.replicas == [1, 2, 3]
        assert info.low_watermark == 0
        assert info.high_watermark == 1000

    def test_topic_metadata_dataclass(self):
        """TopicMetadata should have full topic information."""
        from hs_pylib.kafka.types import PartitionInfo, TopicMetadata

        partitions = [
            PartitionInfo(
                partition=0,
                leader=1,
                replicas=[1, 2],
                isrs=[1, 2],
                low_watermark=0,
                high_watermark=500,
            ),
        ]
        metadata = TopicMetadata(
            name="my-topic",
            partitions=partitions,
            config={"retention.ms": "604800000"},
        )

        assert metadata.name == "my-topic"
        assert len(metadata.partitions) == 1
        assert metadata.config["retention.ms"] == "604800000"

    def test_consumer_group_info_dataclass(self):
        """ConsumerGroupInfo should have group details."""
        from hs_pylib.kafka.types import ConsumerGroupInfo

        info = ConsumerGroupInfo(
            group_id="my-group",
            state="Stable",
            protocol_type="consumer",
            members_count=3,
        )

        assert info.group_id == "my-group"
        assert info.state == "Stable"
        assert info.members_count == 3


# =============================================================================
# Phase 2: KafkaClient (Admin Operations)
# =============================================================================

from datetime import UTC
from unittest.mock import MagicMock, Mock, patch


@pytest.fixture
def mock_admin_client():
    """Mock confluent_kafka AdminClient."""
    with patch("hs_pylib.kafka.client.AdminClient") as mock:
        yield mock


@pytest.fixture
def mock_consumer_for_watermarks():
    """Mock confluent_kafka Consumer for watermark operations."""
    with patch("hs_pylib.kafka.client.Consumer") as mock:
        yield mock


class TestKafkaClientInit:
    """Tests for KafkaClient initialization."""

    def test_client_init_with_bootstrap_servers_string(self, mock_admin_client):
        """Client should accept bootstrap.servers as string."""
        from hs_pylib.kafka.client import KafkaClient

        KafkaClient("localhost:9092")

        mock_admin_client.assert_called_once()
        call_config = mock_admin_client.call_args[0][0]
        assert call_config["bootstrap.servers"] == "localhost:9092"

    def test_client_init_with_dict_config(self, mock_admin_client):
        """Client should accept full config dict."""
        from hs_pylib.kafka.client import KafkaClient

        config = {
            "bootstrap.servers": "kafka1:9092,kafka2:9092",
            "client.id": "my-admin",
        }
        KafkaClient(config)

        call_config = mock_admin_client.call_args[0][0]
        assert call_config["bootstrap.servers"] == "kafka1:9092,kafka2:9092"
        assert call_config["client.id"] == "my-admin"

    def test_client_init_merges_admin_defaults(self, mock_admin_client):
        """Client should merge admin defaults."""
        from hs_pylib.kafka.client import KafkaClient
        from hs_pylib.kafka.config import ADMIN_DEFAULTS

        KafkaClient("localhost:9092")

        call_config = mock_admin_client.call_args[0][0]
        # Should have admin defaults applied
        assert call_config["request.timeout.ms"] == ADMIN_DEFAULTS["request.timeout.ms"]

    def test_client_init_verify_ssl_false(self, mock_admin_client):
        """Client should support verify_ssl=False."""
        from hs_pylib.kafka.client import KafkaClient

        KafkaClient("localhost:9092", verify_ssl=False)

        call_config = mock_admin_client.call_args[0][0]
        assert call_config["enable.ssl.certificate.verification"] == "false"

    def test_client_context_manager(self, mock_admin_client):
        """Client should work as context manager."""
        from hs_pylib.kafka.client import KafkaClient

        with KafkaClient("localhost:9092") as client:
            assert client is not None


class TestKafkaClientListTopics:
    """Tests for listing topics."""

    def test_list_topics_returns_topic_info_list(self, mock_admin_client):
        """list_topics should return list of TopicInfo."""
        from hs_pylib.kafka.client import KafkaClient
        from hs_pylib.kafka.types import TopicInfo

        # Setup mock
        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: Mock(), 1: Mock(), 2: Mock()}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}

        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        client = KafkaClient("localhost:9092")
        topics = client.list_topics()

        assert len(topics) == 1
        assert isinstance(topics[0], TopicInfo)
        assert topics[0].name == "test-topic"
        assert topics[0].partition_count == 3

    def test_list_topics_excludes_internal_by_default(self, mock_admin_client):
        """list_topics should exclude internal topics by default."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup mock with internal topic
        mock_internal = Mock()
        mock_internal.topic = "__consumer_offsets"
        mock_internal.partitions = {0: Mock()}

        mock_user = Mock()
        mock_user.topic = "user-topic"
        mock_user.partitions = {0: Mock()}

        mock_metadata = Mock()
        mock_metadata.topics = {
            "__consumer_offsets": mock_internal,
            "user-topic": mock_user,
        }

        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        client = KafkaClient("localhost:9092")
        topics = client.list_topics()

        assert len(topics) == 1
        assert topics[0].name == "user-topic"

    def test_list_topics_includes_internal_when_requested(self, mock_admin_client):
        """list_topics should include internal topics when include_internal=True."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup mock with internal topic
        mock_internal = Mock()
        mock_internal.topic = "__consumer_offsets"
        mock_internal.partitions = {0: Mock()}

        mock_user = Mock()
        mock_user.topic = "user-topic"
        mock_user.partitions = {0: Mock()}

        mock_metadata = Mock()
        mock_metadata.topics = {
            "__consumer_offsets": mock_internal,
            "user-topic": mock_user,
        }

        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        client = KafkaClient("localhost:9092")
        topics = client.list_topics(include_internal=True)

        assert len(topics) == 2
        topic_names = [t.name for t in topics]
        assert "__consumer_offsets" in topic_names
        assert "user-topic" in topic_names

    def test_list_topics_empty_cluster(self, mock_admin_client):
        """list_topics should handle empty cluster."""
        from hs_pylib.kafka.client import KafkaClient

        mock_metadata = Mock()
        mock_metadata.topics = {}

        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        client = KafkaClient("localhost:9092")
        topics = client.list_topics()

        assert topics == []


class TestKafkaClientDescribeTopic:
    """Tests for describing topics."""

    def test_describe_topic_returns_metadata(self, mock_admin_client, mock_consumer_for_watermarks):
        """describe_topic should return TopicMetadata."""
        from hs_pylib.kafka.client import KafkaClient
        from hs_pylib.kafka.types import TopicMetadata

        # Setup topic metadata mock
        mock_partition = Mock()
        mock_partition.id = 0
        mock_partition.leader = 1
        mock_partition.replicas = [1, 2]
        mock_partition.isrs = [1, 2]

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}

        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        # Setup watermarks mock
        mock_consumer_for_watermarks.return_value.get_watermark_offsets.return_value = (0, 1000)
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        metadata = client.describe_topic("test-topic")

        assert isinstance(metadata, TopicMetadata)
        assert metadata.name == "test-topic"
        assert len(metadata.partitions) == 1
        assert metadata.partitions[0].partition == 0

    def test_describe_topic_includes_watermarks(self, mock_admin_client, mock_consumer_for_watermarks):
        """describe_topic should include watermark offsets."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup topic metadata mock
        mock_partition = Mock()
        mock_partition.id = 0
        mock_partition.leader = 1
        mock_partition.replicas = [1]
        mock_partition.isrs = [1]

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}

        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        # Setup watermarks
        mock_consumer_for_watermarks.return_value.get_watermark_offsets.return_value = (100, 5000)
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        metadata = client.describe_topic("test-topic")

        assert metadata.partitions[0].low_watermark == 100
        assert metadata.partitions[0].high_watermark == 5000

    def test_describe_topic_not_found_raises(self, mock_admin_client):
        """describe_topic should raise for non-existent topic."""
        from hs_pylib.kafka.client import KafkaClient, TopicNotFoundError

        mock_metadata = Mock()
        mock_metadata.topics = {}

        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        client = KafkaClient("localhost:9092")

        with pytest.raises(TopicNotFoundError):
            client.describe_topic("nonexistent-topic")


class TestKafkaClientOffsets:
    """Tests for offset operations."""

    def test_get_offsets_for_times_single_partition(self, mock_admin_client, mock_consumer_for_watermarks):
        """get_offsets_for_times should return offset for timestamp."""
        from hs_pylib.kafka.client import KafkaClient

        # Mock offsets_for_times
        mock_tp = Mock()
        mock_tp.partition = 0
        mock_tp.offset = 500

        mock_consumer_for_watermarks.return_value.offsets_for_times.return_value = [mock_tp]
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        offsets = client.get_offsets_for_times("test-topic", {0: 1234567890000})

        assert offsets[0] == 500

    def test_get_offsets_for_times_all_partitions(self, mock_admin_client, mock_consumer_for_watermarks):
        """get_offsets_for_times should work for multiple partitions."""
        from hs_pylib.kafka.client import KafkaClient

        # Mock for multiple partitions
        mock_tp0 = Mock()
        mock_tp0.partition = 0
        mock_tp0.offset = 100

        mock_tp1 = Mock()
        mock_tp1.partition = 1
        mock_tp1.offset = 200

        mock_consumer_for_watermarks.return_value.offsets_for_times.return_value = [mock_tp0, mock_tp1]
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        offsets = client.get_offsets_for_times("test-topic", {0: 1000, 1: 1000})

        assert offsets[0] == 100
        assert offsets[1] == 200


class TestKafkaClientConsumerLag:
    """Tests for consumer group lag (no JMX required)."""

    def test_get_consumer_lag_returns_partition_dict(self, mock_admin_client, mock_consumer_for_watermarks):
        """get_consumer_lag should return dict of partition -> lag."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup list_topics for partition count
        mock_partition = Mock()
        mock_partition.id = 0

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}
        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        # Setup committed offsets
        mock_tp = Mock()
        mock_tp.partition = 0
        mock_tp.offset = 800

        mock_consumer_for_watermarks.return_value.committed.return_value = [mock_tp]
        mock_consumer_for_watermarks.return_value.get_watermark_offsets.return_value = (0, 1000)
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        lag = client.get_consumer_lag("my-group", "test-topic")

        assert isinstance(lag, dict)
        assert 0 in lag
        assert lag[0] == 200  # 1000 - 800 = 200 messages behind

    def test_get_consumer_lag_calculates_correctly(self, mock_admin_client, mock_consumer_for_watermarks):
        """Lag calculation: high_watermark - committed_offset."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup
        mock_partition = Mock()
        mock_partition.id = 0

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}
        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        # Committed at 500, high watermark at 750
        mock_tp = Mock()
        mock_tp.partition = 0
        mock_tp.offset = 500

        mock_consumer_for_watermarks.return_value.committed.return_value = [mock_tp]
        mock_consumer_for_watermarks.return_value.get_watermark_offsets.return_value = (0, 750)
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        lag = client.get_consumer_lag("my-group", "test-topic")

        assert lag[0] == 250  # 750 - 500

    def test_get_consumer_lag_no_commits_returns_full_lag(self, mock_admin_client, mock_consumer_for_watermarks):
        """No committed offset should return full partition size as lag."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup
        mock_partition = Mock()
        mock_partition.id = 0

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}
        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        # No committed offset (-1001 is OFFSET_INVALID)
        mock_tp = Mock()
        mock_tp.partition = 0
        mock_tp.offset = -1001

        mock_consumer_for_watermarks.return_value.committed.return_value = [mock_tp]
        mock_consumer_for_watermarks.return_value.get_watermark_offsets.return_value = (0, 1000)
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        lag = client.get_consumer_lag("my-group", "test-topic")

        assert lag[0] == 1000  # Full partition size


class TestKafkaClientTopicStats:
    """Tests for topic statistics."""

    def test_get_watermark_offsets(self, mock_admin_client, mock_consumer_for_watermarks):
        """get_watermark_offsets should return (low, high) for each partition."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup topic metadata
        mock_partition0 = Mock()
        mock_partition0.id = 0
        mock_partition1 = Mock()
        mock_partition1.id = 1

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition0, 1: mock_partition1}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}
        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        # Setup watermarks - called per partition
        mock_consumer_for_watermarks.return_value.get_watermark_offsets.side_effect = [
            (0, 500),  # Partition 0
            (100, 800),  # Partition 1
        ]
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        watermarks = client.get_watermark_offsets("test-topic")

        assert watermarks[0] == (0, 500)
        assert watermarks[1] == (100, 800)

    def test_get_topic_message_count(self, mock_admin_client, mock_consumer_for_watermarks):
        """get_topic_message_count should sum partition sizes."""
        from hs_pylib.kafka.client import KafkaClient

        # Setup topic metadata
        mock_partition0 = Mock()
        mock_partition0.id = 0
        mock_partition1 = Mock()
        mock_partition1.id = 1

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition0, 1: mock_partition1}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}
        mock_admin_client.return_value.list_topics.return_value = mock_metadata

        # Partition 0: 500 messages (0-500), Partition 1: 700 messages (100-800)
        mock_consumer_for_watermarks.return_value.get_watermark_offsets.side_effect = [
            (0, 500),
            (100, 800),
        ]
        mock_consumer_for_watermarks.return_value.close = Mock()

        client = KafkaClient("localhost:9092")
        count = client.get_topic_message_count("test-topic")

        assert count == 1200  # 500 + 700


# =============================================================================
# Phase 3: KafkaConsumer
# =============================================================================


@pytest.fixture
def mock_consumer():
    """Mock confluent_kafka Consumer."""
    with patch("hs_pylib.kafka.consumer.Consumer") as mock:
        yield mock


class TestKafkaConsumerInit:
    """Tests for KafkaConsumer initialization."""

    def test_consumer_init_with_group_id(self, mock_consumer):
        """Consumer should require group.id."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        KafkaConsumer("localhost:9092", "my-group")

        mock_consumer.assert_called_once()
        call_config = mock_consumer.call_args[0][0]
        assert call_config["bootstrap.servers"] == "localhost:9092"
        assert call_config["group.id"] == "my-group"

    def test_consumer_init_with_dict_config(self, mock_consumer):
        """Consumer should accept full config dict."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        config = {
            "bootstrap.servers": "kafka1:9092,kafka2:9092",
            "client.id": "my-consumer",
        }
        KafkaConsumer(config, "my-group")

        call_config = mock_consumer.call_args[0][0]
        assert call_config["bootstrap.servers"] == "kafka1:9092,kafka2:9092"
        assert call_config["client.id"] == "my-consumer"
        assert call_config["group.id"] == "my-group"

    def test_consumer_init_merges_defaults(self, mock_consumer):
        """Consumer should merge consumer defaults."""
        from hs_pylib.kafka.config import CONSUMER_DEFAULTS
        from hs_pylib.kafka.consumer import KafkaConsumer

        KafkaConsumer("localhost:9092", "my-group")

        call_config = mock_consumer.call_args[0][0]
        assert call_config["auto.offset.reset"] == CONSUMER_DEFAULTS["auto.offset.reset"]
        assert call_config["enable.auto.commit"] == CONSUMER_DEFAULTS["enable.auto.commit"]

    def test_consumer_init_verify_ssl_false(self, mock_consumer):
        """Consumer should support verify_ssl=False."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        KafkaConsumer("localhost:9092", "my-group", verify_ssl=False)

        call_config = mock_consumer.call_args[0][0]
        assert call_config["enable.ssl.certificate.verification"] == "false"

    def test_consumer_context_manager(self, mock_consumer):
        """Consumer should work as context manager."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        mock_consumer.return_value.close = Mock()

        with KafkaConsumer("localhost:9092", "my-group") as consumer:
            assert consumer is not None

        mock_consumer.return_value.close.assert_called_once()


class TestKafkaConsumerSubscribe:
    """Tests for consumer subscription."""

    def test_consumer_subscribe_single_topic(self, mock_consumer):
        """Consumer should subscribe to single topic."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.subscribe("test-topic")

        mock_consumer.return_value.subscribe.assert_called_once_with(["test-topic"])

    def test_consumer_subscribe_multiple_topics(self, mock_consumer):
        """Consumer should subscribe to multiple topics."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.subscribe(["topic1", "topic2", "topic3"])

        mock_consumer.return_value.subscribe.assert_called_once_with(["topic1", "topic2", "topic3"])

    def test_consumer_unsubscribe(self, mock_consumer):
        """Consumer should support unsubscribe."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.unsubscribe()

        mock_consumer.return_value.unsubscribe.assert_called_once()


class TestKafkaConsumerPoll:
    """Tests for polling messages."""

    def test_consumer_poll_returns_message(self, mock_consumer):
        """poll should return Message object."""
        from hs_pylib.kafka.consumer import KafkaConsumer
        from hs_pylib.kafka.types import Message

        # Setup mock message
        mock_msg = Mock()
        mock_msg.error.return_value = None
        mock_msg.topic.return_value = "test-topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100
        mock_msg.key.return_value = b"key1"
        mock_msg.value.return_value = b'{"data": "test"}'
        mock_msg.timestamp.return_value = (1, 1234567890000)  # (type, timestamp)
        mock_msg.headers.return_value = [("h1", b"v1")]

        mock_consumer.return_value.poll.return_value = mock_msg

        consumer = KafkaConsumer("localhost:9092", "my-group")
        msg = consumer.poll(timeout=1.0)

        assert isinstance(msg, Message)
        assert msg.topic == "test-topic"
        assert msg.partition == 0
        assert msg.offset == 100
        assert msg.key == b"key1"
        assert msg.value == b'{"data": "test"}'
        assert msg.headers == [("h1", b"v1")]

    def test_consumer_poll_timeout_returns_none(self, mock_consumer):
        """poll should return None on timeout."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        mock_consumer.return_value.poll.return_value = None

        consumer = KafkaConsumer("localhost:9092", "my-group")
        msg = consumer.poll(timeout=0.1)

        assert msg is None

    def test_consumer_poll_error_raises(self, mock_consumer):
        """poll should raise on message error."""
        from confluent_kafka import KafkaError, KafkaException

        from hs_pylib.kafka.consumer import KafkaConsumer

        # Setup mock message with error
        mock_msg = Mock()
        mock_error = Mock()
        mock_error.code.return_value = KafkaError._PARTITION_EOF
        mock_msg.error.return_value = mock_error

        mock_consumer.return_value.poll.return_value = mock_msg

        consumer = KafkaConsumer("localhost:9092", "my-group")

        # Partition EOF is not an error, should return None
        msg = consumer.poll(timeout=1.0)
        assert msg is None

    def test_consumer_poll_fatal_error_raises(self, mock_consumer):
        """poll should raise on fatal error."""
        from confluent_kafka import KafkaError, KafkaException

        from hs_pylib.kafka.consumer import KafkaConsumer, KafkaConsumerError

        # Setup mock message with fatal error
        mock_msg = Mock()
        mock_error = Mock()
        mock_error.code.return_value = KafkaError._ALL_BROKERS_DOWN
        mock_error.str.return_value = "All brokers down"
        mock_msg.error.return_value = mock_error

        mock_consumer.return_value.poll.return_value = mock_msg

        consumer = KafkaConsumer("localhost:9092", "my-group")

        with pytest.raises(KafkaConsumerError):
            consumer.poll(timeout=1.0)


class TestKafkaConsumerSeek:
    """Tests for seek operations."""

    def test_consumer_seek_to_offset(self, mock_consumer):
        """Consumer should seek to specific offset."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.seek("test-topic", 0, 500)

        mock_consumer.return_value.seek.assert_called_once()

    def test_consumer_seek_to_beginning(self, mock_consumer):
        """Consumer should seek to beginning of partition."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        mock_consumer.return_value.get_watermark_offsets.return_value = (100, 1000)

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.seek_to_beginning("test-topic", 0)

        # Should seek to low watermark
        mock_consumer.return_value.seek.assert_called_once()

    def test_consumer_seek_to_end(self, mock_consumer):
        """Consumer should seek to end of partition."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        mock_consumer.return_value.get_watermark_offsets.return_value = (100, 1000)

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.seek_to_end("test-topic", 0)

        # Should seek to high watermark
        mock_consumer.return_value.seek.assert_called_once()

    def test_consumer_position_returns_offset(self, mock_consumer):
        """position should return current offset."""
        from confluent_kafka import TopicPartition

        from hs_pylib.kafka.consumer import KafkaConsumer

        mock_tp = Mock()
        mock_tp.offset = 500
        mock_consumer.return_value.position.return_value = [mock_tp]

        consumer = KafkaConsumer("localhost:9092", "my-group")
        offset = consumer.position("test-topic", 0)

        assert offset == 500


class TestKafkaConsumerCommit:
    """Tests for commit operations."""

    def test_consumer_commit_sync(self, mock_consumer):
        """Consumer should commit synchronously."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.commit()

        mock_consumer.return_value.commit.assert_called_once_with(asynchronous=False)

    def test_consumer_commit_async(self, mock_consumer):
        """Consumer should commit asynchronously."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.commit(asynchronous=True)

        mock_consumer.return_value.commit.assert_called_once_with(asynchronous=True)

    def test_consumer_committed_returns_offsets(self, mock_consumer):
        """committed should return committed offsets."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        mock_tp = Mock()
        mock_tp.partition = 0
        mock_tp.offset = 500
        mock_consumer.return_value.committed.return_value = [mock_tp]

        consumer = KafkaConsumer("localhost:9092", "my-group")
        offsets = consumer.committed("test-topic", [0])

        assert offsets[0] == 500


class TestKafkaConsumerAssign:
    """Tests for manual partition assignment."""

    def test_consumer_assign_partitions(self, mock_consumer):
        """Consumer should manually assign partitions."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        consumer = KafkaConsumer("localhost:9092", "my-group")
        consumer.assign("test-topic", [0, 1, 2])

        mock_consumer.return_value.assign.assert_called_once()

    def test_consumer_assignment_returns_partitions(self, mock_consumer):
        """assignment should return assigned partitions."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        mock_tp0 = Mock()
        mock_tp0.topic = "test-topic"
        mock_tp0.partition = 0

        mock_tp1 = Mock()
        mock_tp1.topic = "test-topic"
        mock_tp1.partition = 1

        mock_consumer.return_value.assignment.return_value = [mock_tp0, mock_tp1]

        consumer = KafkaConsumer("localhost:9092", "my-group")
        assignment = consumer.assignment()

        assert len(assignment) == 2
        assert ("test-topic", 0) in assignment
        assert ("test-topic", 1) in assignment


class TestKafkaConsumerIterator:
    """Tests for iterator interface."""

    def test_consumer_iter_yields_messages(self, mock_consumer):
        """Iterator should yield messages."""
        from hs_pylib.kafka.consumer import KafkaConsumer
        from hs_pylib.kafka.types import Message

        # Setup mock messages
        mock_msg1 = Mock()
        mock_msg1.error.return_value = None
        mock_msg1.topic.return_value = "test-topic"
        mock_msg1.partition.return_value = 0
        mock_msg1.offset.return_value = 0
        mock_msg1.key.return_value = None
        mock_msg1.value.return_value = b"msg1"
        mock_msg1.timestamp.return_value = (1, 1000)
        mock_msg1.headers.return_value = None

        mock_msg2 = Mock()
        mock_msg2.error.return_value = None
        mock_msg2.topic.return_value = "test-topic"
        mock_msg2.partition.return_value = 0
        mock_msg2.offset.return_value = 1
        mock_msg2.key.return_value = None
        mock_msg2.value.return_value = b"msg2"
        mock_msg2.timestamp.return_value = (1, 2000)
        mock_msg2.headers.return_value = None

        # Return messages then None to stop
        mock_consumer.return_value.poll.side_effect = [mock_msg1, mock_msg2, None]

        consumer = KafkaConsumer("localhost:9092", "my-group")
        messages = []
        for msg in consumer:
            messages.append(msg)
            if len(messages) >= 2:
                break

        assert len(messages) == 2
        assert messages[0].value == b"msg1"
        assert messages[1].value == b"msg2"

    def test_consumer_consume_batch(self, mock_consumer):
        """consume should return batch of messages."""
        from hs_pylib.kafka.consumer import KafkaConsumer

        # Setup mock messages
        mock_msg1 = Mock()
        mock_msg1.error.return_value = None
        mock_msg1.topic.return_value = "test-topic"
        mock_msg1.partition.return_value = 0
        mock_msg1.offset.return_value = 0
        mock_msg1.key.return_value = None
        mock_msg1.value.return_value = b"msg1"
        mock_msg1.timestamp.return_value = (1, 1000)
        mock_msg1.headers.return_value = None

        mock_msg2 = Mock()
        mock_msg2.error.return_value = None
        mock_msg2.topic.return_value = "test-topic"
        mock_msg2.partition.return_value = 0
        mock_msg2.offset.return_value = 1
        mock_msg2.key.return_value = None
        mock_msg2.value.return_value = b"msg2"
        mock_msg2.timestamp.return_value = (1, 2000)
        mock_msg2.headers.return_value = None

        mock_consumer.return_value.consume.return_value = [mock_msg1, mock_msg2]

        consumer = KafkaConsumer("localhost:9092", "my-group")
        messages = consumer.consume(num_messages=10, timeout=1.0)

        assert len(messages) == 2
        assert messages[0].value == b"msg1"
        assert messages[1].value == b"msg2"


# =============================================================================
# Phase 4: KafkaProducer
# =============================================================================


@pytest.fixture
def mock_producer():
    """Mock confluent_kafka Producer."""
    with patch("hs_pylib.kafka.producer.Producer") as mock:
        yield mock


class TestKafkaProducerInit:
    """Tests for KafkaProducer initialization."""

    def test_producer_init_with_bootstrap_servers(self, mock_producer):
        """Producer should accept bootstrap.servers string."""
        from hs_pylib.kafka.producer import KafkaProducer

        KafkaProducer("localhost:9092")

        mock_producer.assert_called_once()
        call_config = mock_producer.call_args[0][0]
        assert call_config["bootstrap.servers"] == "localhost:9092"

    def test_producer_init_with_dict_config(self, mock_producer):
        """Producer should accept full config dict."""
        from hs_pylib.kafka.producer import KafkaProducer

        config = {
            "bootstrap.servers": "kafka1:9092,kafka2:9092",
            "client.id": "my-producer",
        }
        KafkaProducer(config)

        call_config = mock_producer.call_args[0][0]
        assert call_config["bootstrap.servers"] == "kafka1:9092,kafka2:9092"
        assert call_config["client.id"] == "my-producer"

    def test_producer_init_merges_defaults(self, mock_producer):
        """Producer should merge producer defaults."""
        from hs_pylib.kafka.config import PRODUCER_DEFAULTS
        from hs_pylib.kafka.producer import KafkaProducer

        KafkaProducer("localhost:9092")

        call_config = mock_producer.call_args[0][0]
        assert call_config["acks"] == PRODUCER_DEFAULTS["acks"]
        assert call_config["retries"] == PRODUCER_DEFAULTS["retries"]
        assert call_config["compression.type"] == PRODUCER_DEFAULTS["compression.type"]

    def test_producer_init_verify_ssl_false(self, mock_producer):
        """Producer should support verify_ssl=False."""
        from hs_pylib.kafka.producer import KafkaProducer

        KafkaProducer("localhost:9092", verify_ssl=False)

        call_config = mock_producer.call_args[0][0]
        assert call_config["enable.ssl.certificate.verification"] == "false"

    def test_producer_context_manager(self, mock_producer):
        """Producer should work as context manager."""
        from hs_pylib.kafka.producer import KafkaProducer

        mock_producer.return_value.flush = Mock(return_value=0)

        with KafkaProducer("localhost:9092") as producer:
            assert producer is not None

        mock_producer.return_value.flush.assert_called_once()


class TestKafkaProducerSend:
    """Tests for sending messages."""

    def test_producer_send_string_value(self, mock_producer):
        """Producer should send string values."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        producer.send("test-topic", "hello world")

        mock_producer.return_value.produce.assert_called_once()
        call_kwargs = mock_producer.return_value.produce.call_args[1]
        assert call_kwargs["topic"] == "test-topic"
        assert call_kwargs["value"] == b"hello world"

    def test_producer_send_bytes_value(self, mock_producer):
        """Producer should send bytes values."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        producer.send("test-topic", b"raw bytes")

        call_kwargs = mock_producer.return_value.produce.call_args[1]
        assert call_kwargs["value"] == b"raw bytes"

    def test_producer_send_json_value(self, mock_producer):
        """Producer should serialize dict to JSON."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        producer.send("test-topic", {"name": "test", "count": 42})

        call_kwargs = mock_producer.return_value.produce.call_args[1]
        assert call_kwargs["value"] == b'{"name": "test", "count": 42}'

    def test_producer_send_with_key(self, mock_producer):
        """Producer should send with key."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        producer.send("test-topic", "value", key="my-key")

        call_kwargs = mock_producer.return_value.produce.call_args[1]
        assert call_kwargs["key"] == b"my-key"

    def test_producer_send_with_bytes_key(self, mock_producer):
        """Producer should send with bytes key."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        producer.send("test-topic", "value", key=b"bytes-key")

        call_kwargs = mock_producer.return_value.produce.call_args[1]
        assert call_kwargs["key"] == b"bytes-key"

    def test_producer_send_with_headers(self, mock_producer):
        """Producer should send with headers."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        headers = {"trace-id": "abc123", "source": "test"}
        producer.send("test-topic", "value", headers=headers)

        call_kwargs = mock_producer.return_value.produce.call_args[1]
        # Headers converted to list of tuples with bytes values
        assert ("trace-id", b"abc123") in call_kwargs["headers"]
        assert ("source", b"test") in call_kwargs["headers"]

    def test_producer_send_with_partition(self, mock_producer):
        """Producer should send to specific partition."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        producer.send("test-topic", "value", partition=2)

        call_kwargs = mock_producer.return_value.produce.call_args[1]
        assert call_kwargs["partition"] == 2

    def test_producer_send_triggers_poll(self, mock_producer):
        """Producer should poll to trigger callbacks."""
        from hs_pylib.kafka.producer import KafkaProducer

        producer = KafkaProducer("localhost:9092")
        producer.send("test-topic", "value")

        mock_producer.return_value.poll.assert_called_once_with(0)


class TestKafkaProducerFlush:
    """Tests for flushing messages."""

    def test_producer_flush_all_messages(self, mock_producer):
        """flush should wait for all messages."""
        from hs_pylib.kafka.producer import KafkaProducer

        mock_producer.return_value.flush.return_value = 0

        producer = KafkaProducer("localhost:9092")
        unflushed = producer.flush()

        mock_producer.return_value.flush.assert_called_once()
        assert unflushed == 0

    def test_producer_flush_with_timeout(self, mock_producer):
        """flush should accept timeout."""
        from hs_pylib.kafka.producer import KafkaProducer

        mock_producer.return_value.flush.return_value = 0

        producer = KafkaProducer("localhost:9092")
        producer.flush(timeout=5.0)

        mock_producer.return_value.flush.assert_called_once_with(5.0)

    def test_producer_flush_returns_unflushed_count(self, mock_producer):
        """flush should return count of unflushed messages."""
        from hs_pylib.kafka.producer import KafkaProducer

        mock_producer.return_value.flush.return_value = 3

        producer = KafkaProducer("localhost:9092")
        unflushed = producer.flush()

        assert unflushed == 3


class TestKafkaProducerPoll:
    """Tests for poll operation."""

    def test_producer_poll_triggers_callbacks(self, mock_producer):
        """poll should trigger delivery callbacks."""
        from hs_pylib.kafka.producer import KafkaProducer

        mock_producer.return_value.poll.return_value = 5

        producer = KafkaProducer("localhost:9092")
        events = producer.poll(timeout=1.0)

        mock_producer.return_value.poll.assert_called_with(1.0)
        assert events == 5


# =============================================================================
# Phase 5: Sampling Utilities
# =============================================================================


class TestReservoirSample:
    """Tests for reservoir sampling."""

    def test_reservoir_sample_returns_k_messages(self):
        """Reservoir sample should return exactly k messages."""
        from hs_pylib.kafka.sampling import reservoir_sample
        from hs_pylib.kafka.types import Message

        # Create 100 messages
        messages = [
            Message(
                topic="test",
                partition=0,
                offset=i,
                key=None,
                value=f"msg{i}".encode(),
                timestamp=i * 1000,
                headers=None,
            )
            for i in range(100)
        ]

        result = reservoir_sample(iter(messages), k=10)

        assert len(result) == 10

    def test_reservoir_sample_less_than_k_available(self):
        """Reservoir sample should return all if fewer than k available."""
        from hs_pylib.kafka.sampling import reservoir_sample
        from hs_pylib.kafka.types import Message

        messages = [
            Message(
                topic="test",
                partition=0,
                offset=i,
                key=None,
                value=f"msg{i}".encode(),
                timestamp=i * 1000,
                headers=None,
            )
            for i in range(5)
        ]

        result = reservoir_sample(iter(messages), k=10)

        assert len(result) == 5

    def test_reservoir_sample_deterministic_with_seed(self):
        """Reservoir sample should be deterministic with seed."""
        from hs_pylib.kafka.sampling import reservoir_sample
        from hs_pylib.kafka.types import Message

        messages = [
            Message(
                topic="test",
                partition=0,
                offset=i,
                key=None,
                value=f"msg{i}".encode(),
                timestamp=i * 1000,
                headers=None,
            )
            for i in range(100)
        ]

        result1 = reservoir_sample(iter(messages), k=10, seed=42)
        result2 = reservoir_sample(iter(messages), k=10, seed=42)

        # Same seed = same sample
        assert [m.offset for m in result1] == [m.offset for m in result2]

    def test_reservoir_sample_empty_iterator(self):
        """Reservoir sample should handle empty iterator."""
        from hs_pylib.kafka.sampling import reservoir_sample

        result = reservoir_sample(iter([]), k=10)

        assert result == []


class TestTimeBoundedConsume:
    """Tests for time-bounded consumption."""

    def test_time_bounded_consume_respects_limit(self, mock_consumer):
        """Time-bounded consume should respect message limit."""
        from hs_pylib.kafka.consumer import KafkaConsumer
        from hs_pylib.kafka.sampling import time_bounded_consume

        # Setup mock messages with timestamps
        def make_mock_msg(offset, ts):
            msg = Mock()
            msg.error.return_value = None
            msg.topic.return_value = "test-topic"
            msg.partition.return_value = 0
            msg.offset.return_value = offset
            msg.key.return_value = None
            msg.value.return_value = f"msg{offset}".encode()
            msg.timestamp.return_value = (1, ts)
            msg.headers.return_value = None
            return msg

        mock_consumer.return_value.poll.side_effect = [
            make_mock_msg(0, 1000),
            make_mock_msg(1, 2000),
            make_mock_msg(2, 3000),
            make_mock_msg(3, 4000),
            make_mock_msg(4, 5000),
        ]
        mock_consumer.return_value.close = Mock()

        consumer = KafkaConsumer("localhost:9092", "my-group")
        messages = time_bounded_consume(
            consumer,
            start_time=1000,
            end_time=10000,
            limit=3,
        )

        assert len(messages) == 3

    def test_time_bounded_consume_filters_by_time(self, mock_consumer):
        """Time-bounded consume should filter by timestamp."""
        from hs_pylib.kafka.consumer import KafkaConsumer
        from hs_pylib.kafka.sampling import time_bounded_consume

        def make_mock_msg(offset, ts):
            msg = Mock()
            msg.error.return_value = None
            msg.topic.return_value = "test-topic"
            msg.partition.return_value = 0
            msg.offset.return_value = offset
            msg.key.return_value = None
            msg.value.return_value = f"msg{offset}".encode()
            msg.timestamp.return_value = (1, ts)
            msg.headers.return_value = None
            return msg

        # Messages at timestamps 1000, 2000, 3000, 4000, 5000
        mock_consumer.return_value.poll.side_effect = [
            make_mock_msg(0, 1000),
            make_mock_msg(1, 2000),
            make_mock_msg(2, 3000),
            make_mock_msg(3, 4000),  # Beyond end_time
            None,  # End
        ]
        mock_consumer.return_value.close = Mock()

        consumer = KafkaConsumer("localhost:9092", "my-group")
        messages = time_bounded_consume(
            consumer,
            start_time=1000,
            end_time=3500,  # Should stop before ts=4000
        )

        assert len(messages) == 3
        assert all(m.timestamp <= 3500 for m in messages)

    def test_time_bounded_consume_empty_range(self, mock_consumer):
        """Time-bounded consume should handle empty time range."""
        from hs_pylib.kafka.consumer import KafkaConsumer
        from hs_pylib.kafka.sampling import time_bounded_consume

        mock_consumer.return_value.poll.return_value = None
        mock_consumer.return_value.close = Mock()

        consumer = KafkaConsumer("localhost:9092", "my-group")
        messages = time_bounded_consume(
            consumer,
            start_time=1000,
            end_time=2000,
        )

        assert messages == []


class TestPartitionSample:
    """Tests for partition-based sampling."""

    def test_partition_sample_returns_dict(self):
        """Partition sample should return dict of partition -> messages."""
        from hs_pylib.kafka.sampling import partition_sample
        from hs_pylib.kafka.types import Message

        messages = [
            Message(
                topic="test",
                partition=p,
                offset=i,
                key=None,
                value=f"msg{i}".encode(),
                timestamp=i * 1000,
                headers=None,
            )
            for i in range(30)
            for p in range(3)
        ]

        result = partition_sample(iter(messages), n_per_partition=5)

        assert isinstance(result, dict)
        # Should have keys 0, 1, 2
        assert set(result.keys()) == {0, 1, 2}
        # Each partition should have at most 5 messages
        for partition, msgs in result.items():
            assert len(msgs) <= 5

    def test_partition_sample_uniform_per_partition(self):
        """Partition sample should sample uniformly per partition."""
        from hs_pylib.kafka.sampling import partition_sample
        from hs_pylib.kafka.types import Message

        # Create 100 messages per partition
        messages = []
        for p in range(3):
            for i in range(100):
                messages.append(
                    Message(
                        topic="test",
                        partition=p,
                        offset=i,
                        key=None,
                        value=f"p{p}msg{i}".encode(),
                        timestamp=i * 1000,
                        headers=None,
                    )
                )

        result = partition_sample(iter(messages), n_per_partition=10, seed=42)

        for partition, msgs in result.items():
            assert len(msgs) == 10

    def test_partition_sample_sparse_partition(self):
        """Partition sample should handle partitions with fewer messages."""
        from hs_pylib.kafka.sampling import partition_sample
        from hs_pylib.kafka.types import Message

        messages = [
            # Partition 0: 100 messages
            *[
                Message(
                    topic="test",
                    partition=0,
                    offset=i,
                    key=None,
                    value=f"msg{i}".encode(),
                    timestamp=i * 1000,
                    headers=None,
                )
                for i in range(100)
            ],
            # Partition 1: only 3 messages
            *[
                Message(
                    topic="test",
                    partition=1,
                    offset=i,
                    key=None,
                    value=f"msg{i}".encode(),
                    timestamp=i * 1000,
                    headers=None,
                )
                for i in range(3)
            ],
        ]

        result = partition_sample(iter(messages), n_per_partition=10)

        assert len(result[0]) == 10
        assert len(result[1]) == 3  # Only had 3 messages


# =============================================================================
# Phase 6: Schema Analyser
# =============================================================================


class TestSchemaAnalyser:
    """Tests for JSON schema inference."""

    def test_analyser_init(self):
        """SchemaAnalyser should initialize."""
        from hs_pylib.kafka.schema import SchemaAnalyser

        analyser = SchemaAnalyser()
        assert analyser is not None

    def test_analyser_single_message_schema(self):
        """SchemaAnalyser should infer schema from single message."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        msg = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b'{"name": "test", "count": 42}',
            timestamp=1000,
            headers=None,
        )
        analyser.add_message(msg)

        schema = analyser.get_schema()
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]

    def test_analyser_multiple_same_schema(self):
        """SchemaAnalyser should handle multiple messages with same schema."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        for i in range(10):
            msg = Message(
                topic="test",
                partition=0,
                offset=i,
                key=None,
                value=f'{{"name": "test{i}", "count": {i}}}'.encode(),
                timestamp=i * 1000,
                headers=None,
            )
            analyser.add_message(msg)

        schema = analyser.get_schema()
        assert schema["type"] == "object"
        assert analyser.message_count == 10

    def test_analyser_merged_schema(self):
        """SchemaAnalyser should merge schemas with different fields."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        # Message with field A
        msg1 = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b'{"name": "test", "field_a": 1}',
            timestamp=1000,
            headers=None,
        )
        analyser.add_message(msg1)

        # Message with field B
        msg2 = Message(
            topic="test",
            partition=0,
            offset=1,
            key=None,
            value=b'{"name": "test", "field_b": 2}',
            timestamp=2000,
            headers=None,
        )
        analyser.add_message(msg2)

        schema = analyser.get_schema()
        # Should have all fields
        assert "name" in schema["properties"]
        assert "field_a" in schema["properties"]
        assert "field_b" in schema["properties"]

    def test_analyser_non_json_skipped(self):
        """SchemaAnalyser should skip non-JSON messages."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        msg = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b"not json",
            timestamp=1000,
            headers=None,
        )
        analyser.add_message(msg)

        assert analyser.message_count == 0
        assert analyser.skipped_count == 1


class TestSchemaAnalyserFieldStats:
    """Tests for field statistics."""

    def test_analyser_tracks_field_types(self):
        """SchemaAnalyser should track field types."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        # String value
        msg1 = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b'{"value": "hello"}',
            timestamp=1000,
            headers=None,
        )
        analyser.add_message(msg1)

        # Integer value
        msg2 = Message(
            topic="test",
            partition=0,
            offset=1,
            key=None,
            value=b'{"value": 42}',
            timestamp=2000,
            headers=None,
        )
        analyser.add_message(msg2)

        stats = analyser.get_field_stats()
        assert "value" in stats
        assert "string" in stats["value"]["types"]
        assert "integer" in stats["value"]["types"]

    def test_analyser_tracks_null_count(self):
        """SchemaAnalyser should track null values."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        for i in range(5):
            value = "null" if i % 2 == 0 else f'"{i}"'
            msg = Message(
                topic="test",
                partition=0,
                offset=i,
                key=None,
                value=f'{{"value": {value}}}'.encode(),
                timestamp=i * 1000,
                headers=None,
            )
            analyser.add_message(msg)

        stats = analyser.get_field_stats()
        assert stats["value"]["null_count"] == 3  # i=0, 2, 4

    def test_analyser_tracks_sample_values(self):
        """SchemaAnalyser should track sample values."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        for i in range(10):
            msg = Message(
                topic="test",
                partition=0,
                offset=i,
                key=None,
                value=f'{{"name": "user{i}"}}'.encode(),
                timestamp=i * 1000,
                headers=None,
            )
            analyser.add_message(msg)

        stats = analyser.get_field_stats()
        assert len(stats["name"]["sample_values"]) > 0
        assert len(stats["name"]["sample_values"]) <= 5  # Max 5 samples


class TestSchemaAnalysisResult:
    """Tests for analysis result."""

    def test_analyse_returns_result(self):
        """analyse should return AnalysisResult."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        for i in range(10):
            msg = Message(
                topic="test",
                partition=0,
                offset=i,
                key=None,
                value=f'{{"name": "test{i}", "count": {i}}}'.encode(),
                timestamp=i * 1000,
                headers=None,
            )
            analyser.add_message(msg)

        result = analyser.analyse()

        assert result.total_messages == 10
        assert result.skipped_messages == 0
        assert result.schema is not None
        assert result.field_stats is not None

    def test_analyse_with_skipped_messages(self):
        """analyse should report skipped messages."""
        from hs_pylib.kafka.schema import SchemaAnalyser
        from hs_pylib.kafka.types import Message

        analyser = SchemaAnalyser()

        # Valid JSON
        msg1 = Message(
            topic="test",
            partition=0,
            offset=0,
            key=None,
            value=b'{"name": "test"}',
            timestamp=1000,
            headers=None,
        )
        analyser.add_message(msg1)

        # Invalid JSON
        msg2 = Message(
            topic="test",
            partition=0,
            offset=1,
            key=None,
            value=b"not json",
            timestamp=2000,
            headers=None,
        )
        analyser.add_message(msg2)

        result = analyser.analyse()

        assert result.total_messages == 1
        assert result.skipped_messages == 1


# =============================================================================
# Phase 7: Async Wrappers
# =============================================================================


@pytest.fixture
def mock_async_admin_client():
    """Mock AdminClient for async wrapper."""
    with patch("hs_pylib.kafka.async_client.AdminClient") as mock:
        yield mock


@pytest.fixture
def mock_async_consumer():
    """Mock Consumer for async wrapper."""
    with patch("hs_pylib.kafka.async_consumer.Consumer") as mock:
        yield mock


@pytest.fixture
def mock_async_producer():
    """Mock Producer for async wrapper."""
    with patch("hs_pylib.kafka.async_producer.Producer") as mock:
        yield mock


class TestAsyncKafkaClient:
    """Tests for async Kafka client."""

    @pytest.mark.asyncio
    async def test_async_client_init(self, mock_async_admin_client):
        """AsyncKafkaClient should initialize."""
        from hs_pylib.kafka.async_client import AsyncKafkaClient

        client = AsyncKafkaClient("localhost:9092")
        assert client is not None

    @pytest.mark.asyncio
    async def test_async_client_context_manager(self, mock_async_admin_client):
        """AsyncKafkaClient should work as async context manager."""
        from hs_pylib.kafka.async_client import AsyncKafkaClient

        async with AsyncKafkaClient("localhost:9092") as client:
            assert client is not None

    @pytest.mark.asyncio
    async def test_async_list_topics(self, mock_async_admin_client):
        """list_topics should be async."""
        from hs_pylib.kafka.async_client import AsyncKafkaClient

        # Setup mock
        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: Mock()}

        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}

        mock_async_admin_client.return_value.list_topics.return_value = mock_metadata

        async with AsyncKafkaClient("localhost:9092") as client:
            topics = await client.list_topics()

        assert len(topics) == 1
        assert topics[0].name == "test-topic"


class TestAsyncKafkaConsumer:
    """Tests for async Kafka consumer."""

    @pytest.mark.asyncio
    async def test_async_consumer_init(self, mock_async_consumer):
        """AsyncKafkaConsumer should initialize."""
        from hs_pylib.kafka.async_consumer import AsyncKafkaConsumer

        consumer = AsyncKafkaConsumer("localhost:9092", "my-group")
        assert consumer is not None

    @pytest.mark.asyncio
    async def test_async_consumer_context_manager(self, mock_async_consumer):
        """AsyncKafkaConsumer should work as async context manager."""
        from hs_pylib.kafka.async_consumer import AsyncKafkaConsumer

        mock_async_consumer.return_value.close = Mock()

        async with AsyncKafkaConsumer("localhost:9092", "my-group") as consumer:
            assert consumer is not None

        mock_async_consumer.return_value.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_consumer_poll(self, mock_async_consumer):
        """poll should be async."""
        from hs_pylib.kafka.async_consumer import AsyncKafkaConsumer
        from hs_pylib.kafka.types import Message

        # Setup mock message
        mock_msg = Mock()
        mock_msg.error.return_value = None
        mock_msg.topic.return_value = "test-topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100
        mock_msg.key.return_value = None
        mock_msg.value.return_value = b"test"
        mock_msg.timestamp.return_value = (1, 1000)
        mock_msg.headers.return_value = None

        mock_async_consumer.return_value.poll.return_value = mock_msg

        consumer = AsyncKafkaConsumer("localhost:9092", "my-group")
        msg = await consumer.poll(timeout=1.0)

        assert isinstance(msg, Message)
        assert msg.value == b"test"

    @pytest.mark.asyncio
    async def test_async_consumer_aiter(self, mock_async_consumer):
        """AsyncKafkaConsumer should support async iteration."""
        from hs_pylib.kafka.async_consumer import AsyncKafkaConsumer

        # Setup mock messages
        mock_msg1 = Mock()
        mock_msg1.error.return_value = None
        mock_msg1.topic.return_value = "test"
        mock_msg1.partition.return_value = 0
        mock_msg1.offset.return_value = 0
        mock_msg1.key.return_value = None
        mock_msg1.value.return_value = b"msg1"
        mock_msg1.timestamp.return_value = (1, 1000)
        mock_msg1.headers.return_value = None

        mock_msg2 = Mock()
        mock_msg2.error.return_value = None
        mock_msg2.topic.return_value = "test"
        mock_msg2.partition.return_value = 0
        mock_msg2.offset.return_value = 1
        mock_msg2.key.return_value = None
        mock_msg2.value.return_value = b"msg2"
        mock_msg2.timestamp.return_value = (1, 2000)
        mock_msg2.headers.return_value = None

        mock_async_consumer.return_value.poll.side_effect = [mock_msg1, mock_msg2, None]
        mock_async_consumer.return_value.close = Mock()

        consumer = AsyncKafkaConsumer("localhost:9092", "my-group")
        messages = []
        async for msg in consumer:
            messages.append(msg)
            if len(messages) >= 2:
                break

        assert len(messages) == 2


class TestAsyncKafkaProducer:
    """Tests for async Kafka producer."""

    @pytest.mark.asyncio
    async def test_async_producer_init(self, mock_async_producer):
        """AsyncKafkaProducer should initialize."""
        from hs_pylib.kafka.async_producer import AsyncKafkaProducer

        producer = AsyncKafkaProducer("localhost:9092")
        assert producer is not None

    @pytest.mark.asyncio
    async def test_async_producer_context_manager(self, mock_async_producer):
        """AsyncKafkaProducer should work as async context manager."""
        from hs_pylib.kafka.async_producer import AsyncKafkaProducer

        mock_async_producer.return_value.flush = Mock(return_value=0)

        async with AsyncKafkaProducer("localhost:9092") as producer:
            assert producer is not None

        mock_async_producer.return_value.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_producer_send(self, mock_async_producer):
        """send should be async."""
        from hs_pylib.kafka.async_producer import AsyncKafkaProducer

        producer = AsyncKafkaProducer("localhost:9092")
        await producer.send("test-topic", "hello")

        mock_async_producer.return_value.produce.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_producer_flush(self, mock_async_producer):
        """flush should be async."""
        from hs_pylib.kafka.async_producer import AsyncKafkaProducer

        mock_async_producer.return_value.flush.return_value = 0

        producer = AsyncKafkaProducer("localhost:9092")
        result = await producer.flush()

        assert result == 0


# =============================================================================
# Phase 8: Module Exports
# =============================================================================


class TestKafkaModuleExports:
    """Tests for module public API exports."""

    def test_import_kafka_client(self):
        """KafkaClient should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import KafkaClient

        assert KafkaClient is not None

    def test_import_kafka_consumer(self):
        """KafkaConsumer should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import KafkaConsumer

        assert KafkaConsumer is not None

    def test_import_kafka_producer(self):
        """KafkaProducer should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import KafkaProducer

        assert KafkaProducer is not None

    def test_import_async_variants(self):
        """Async classes should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import (
            AsyncKafkaClient,
            AsyncKafkaConsumer,
            AsyncKafkaProducer,
        )

        assert AsyncKafkaClient is not None
        assert AsyncKafkaConsumer is not None
        assert AsyncKafkaProducer is not None

    def test_import_sampling_functions(self):
        """Sampling functions should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import (
            partition_sample,
            reservoir_sample,
            time_bounded_consume,
        )

        assert reservoir_sample is not None
        assert time_bounded_consume is not None
        assert partition_sample is not None

    def test_import_schema_analyser(self):
        """SchemaAnalyser should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import SchemaAnalyser

        assert SchemaAnalyser is not None

    def test_import_types(self):
        """Types should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import (
            ConsumerGroupInfo,
            Message,
            PartitionInfo,
            TopicInfo,
            TopicMetadata,
        )

        assert Message is not None
        assert TopicInfo is not None
        assert PartitionInfo is not None
        assert TopicMetadata is not None
        assert ConsumerGroupInfo is not None

    def test_import_defaults(self):
        """Defaults should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import (
            ADMIN_DEFAULTS,
            CONSUMER_DEFAULTS,
            PRODUCER_DEFAULTS,
        )

        assert PRODUCER_DEFAULTS is not None
        assert CONSUMER_DEFAULTS is not None
        assert ADMIN_DEFAULTS is not None

    def test_import_config_utilities(self):
        """Config utilities should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import config_from_env, merge_config

        assert merge_config is not None
        assert config_from_env is not None

    def test_import_exceptions(self):
        """Exceptions should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import (
            KafkaConsumerError,
            TopicNotFoundError,
        )

        assert TopicNotFoundError is not None
        assert KafkaConsumerError is not None


# =============================================================================
# Phase 9: Kafka Metrics (librdkafka stats)
# =============================================================================


class TestKafkaMetricsCollector:
    """Tests for Kafka metrics collection."""

    def test_metrics_collector_init(self):
        """KafkaMetricsCollector should initialize."""
        from hs_pylib.kafka.metrics import KafkaMetricsCollector

        collector = KafkaMetricsCollector()
        assert collector is not None

    def test_metrics_collector_parse_stats(self):
        """Collector should parse librdkafka stats JSON."""
        from hs_pylib.kafka.metrics import KafkaMetricsCollector

        collector = KafkaMetricsCollector()

        stats_json = """{
            "name": "rdkafka#producer-1",
            "client_id": "my-producer",
            "type": "producer",
            "ts": 1234567890000,
            "msg_cnt": 100,
            "msg_size": 50000,
            "tx": 500,
            "tx_bytes": 100000,
            "rx": 450,
            "rx_bytes": 5000
        }"""

        collector.update_from_stats(stats_json)
        metrics = collector.get_metrics()

        assert metrics["kafka_messages_queued"] == 100
        assert metrics["kafka_messages_queued_bytes"] == 50000
        assert metrics["kafka_requests_total"] == 500
        assert metrics["kafka_requests_bytes_total"] == 100000

    def test_metrics_collector_broker_stats(self):
        """Collector should parse broker-level stats."""
        from hs_pylib.kafka.metrics import KafkaMetricsCollector

        collector = KafkaMetricsCollector()

        stats_json = """{
            "name": "rdkafka#consumer-1",
            "client_id": "my-consumer",
            "type": "consumer",
            "ts": 1234567890000,
            "brokers": {
                "kafka1:9092/1": {
                    "name": "kafka1:9092/1",
                    "nodeid": 1,
                    "state": "UP",
                    "stateage": 60000000,
                    "tx": 100,
                    "tx_bytes": 10000,
                    "rx": 95,
                    "rx_bytes": 5000,
                    "rtt": {"avg": 5000, "p99": 15000}
                }
            }
        }"""

        collector.update_from_stats(stats_json)
        broker_metrics = collector.get_broker_metrics()

        assert "kafka1:9092/1" in broker_metrics
        assert broker_metrics["kafka1:9092/1"]["state"] == "UP"
        assert broker_metrics["kafka1:9092/1"]["rtt_avg_us"] == 5000

    def test_metrics_collector_consumer_lag(self):
        """Collector should track consumer lag from partition stats."""
        from hs_pylib.kafka.metrics import KafkaMetricsCollector

        collector = KafkaMetricsCollector()

        stats_json = """{
            "name": "rdkafka#consumer-1",
            "client_id": "my-consumer",
            "type": "consumer",
            "ts": 1234567890000,
            "topics": {
                "test-topic": {
                    "topic": "test-topic",
                    "partitions": {
                        "0": {
                            "partition": 0,
                            "consumer_lag": 1500,
                            "hi_offset": 10000,
                            "committed_offset": 8500
                        },
                        "1": {
                            "partition": 1,
                            "consumer_lag": 500,
                            "hi_offset": 5000,
                            "committed_offset": 4500
                        }
                    }
                }
            }
        }"""

        collector.update_from_stats(stats_json)
        lag = collector.get_consumer_lag()

        assert "test-topic" in lag
        assert lag["test-topic"][0] == 1500
        assert lag["test-topic"][1] == 500

    def test_metrics_collector_cgrp_stats(self):
        """Collector should parse consumer group stats."""
        from hs_pylib.kafka.metrics import KafkaMetricsCollector

        collector = KafkaMetricsCollector()

        stats_json = """{
            "name": "rdkafka#consumer-1",
            "client_id": "my-consumer",
            "type": "consumer",
            "ts": 1234567890000,
            "cgrp": {
                "state": "up",
                "stateage": 300000,
                "join_state": "assigned",
                "rebalance_age": 120000,
                "rebalance_cnt": 3,
                "assignment_size": 6
            }
        }"""

        collector.update_from_stats(stats_json)
        cgrp = collector.get_cgrp_metrics()

        assert cgrp["state"] == "up"
        assert cgrp["join_state"] == "assigned"
        assert cgrp["rebalance_cnt"] == 3
        assert cgrp["assignment_size"] == 6


class TestKafkaMetricsCallback:
    """Tests for stats callback integration."""

    def test_create_stats_callback(self):
        """Should create stats callback function."""
        from hs_pylib.kafka.metrics import KafkaMetricsCollector, create_stats_callback

        collector = KafkaMetricsCollector()
        callback = create_stats_callback(collector)

        assert callable(callback)

    def test_stats_callback_updates_collector(self):
        """Stats callback should update collector with new stats."""
        from hs_pylib.kafka.metrics import KafkaMetricsCollector, create_stats_callback

        collector = KafkaMetricsCollector()
        callback = create_stats_callback(collector)

        stats_json = '{"name": "test", "msg_cnt": 42, "ts": 1000}'
        callback(stats_json)

        metrics = collector.get_metrics()
        assert metrics["kafka_messages_queued"] == 42


@pytest.fixture
def mock_readonly_admin_client():
    """Mock AdminClient for readonly client."""
    with patch("hs_pylib.kafka.readonly.AdminClient") as mock:
        yield mock


@pytest.fixture
def mock_readonly_consumer():
    """Mock Consumer for readonly client."""
    with patch("hs_pylib.kafka.readonly.Consumer") as mock:
        yield mock


class TestReadOnlyKafkaClient:
    """Tests for read-only Kafka client mode."""

    def test_readonly_client_cannot_produce(self, mock_readonly_admin_client):
        """Read-only client should not allow message production."""
        from hs_pylib.kafka.readonly import ReadOnlyKafkaClient

        client = ReadOnlyKafkaClient("localhost:9092")

        # Should not have send/produce methods
        assert not hasattr(client, "send")
        assert not hasattr(client, "produce")

    def test_readonly_client_can_list_topics(self, mock_readonly_admin_client):
        """Read-only client should allow listing topics."""
        from hs_pylib.kafka.readonly import ReadOnlyKafkaClient

        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: Mock()}
        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}
        mock_readonly_admin_client.return_value.list_topics.return_value = mock_metadata

        client = ReadOnlyKafkaClient("localhost:9092")
        topics = client.list_topics()

        assert len(topics) == 1

    def test_readonly_client_can_get_watermarks(self, mock_readonly_admin_client, mock_readonly_consumer):
        """Read-only client should allow getting watermarks."""
        from hs_pylib.kafka.readonly import ReadOnlyKafkaClient

        # Setup mocks
        mock_partition = Mock()
        mock_partition.id = 0
        mock_topic = Mock()
        mock_topic.topic = "test-topic"
        mock_topic.partitions = {0: mock_partition}
        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic}
        mock_readonly_admin_client.return_value.list_topics.return_value = mock_metadata
        mock_readonly_consumer.return_value.get_watermark_offsets.return_value = (0, 1000)
        mock_readonly_consumer.return_value.close = Mock()

        client = ReadOnlyKafkaClient("localhost:9092")
        watermarks = client.get_watermark_offsets("test-topic")

        assert watermarks[0] == (0, 1000)


# =============================================================================
# Phase 10: File-based Configuration (librdkafka formats)
# =============================================================================


class TestConfigFromFile:
    """Tests for loading configuration from files."""

    def test_config_from_properties_file(self, tmp_path):
        """Should load config from .properties file."""
        from hs_pylib.kafka.config import config_from_file

        props_file = tmp_path / "kafka.properties"
        props_file.write_text("""
# Kafka connection settings
bootstrap.servers=kafka1:9092,kafka2:9092
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-256
sasl.username=admin
sasl.password=secret123
acks=all
""")

        config = config_from_file(str(props_file))

        assert config["bootstrap.servers"] == "kafka1:9092,kafka2:9092"
        assert config["security.protocol"] == "SASL_SSL"
        assert config["sasl.mechanism"] == "SCRAM-SHA-256"
        assert config["sasl.username"] == "admin"
        assert config["sasl.password"] == "secret123"
        assert config["acks"] == "all"

    def test_config_from_properties_ignores_comments(self, tmp_path):
        """Should ignore comments in properties file."""
        from hs_pylib.kafka.config import config_from_file

        props_file = tmp_path / "kafka.properties"
        props_file.write_text("""
# This is a comment
bootstrap.servers=localhost:9092
# Another comment
! Exclamation comment
client.id=test-client
""")

        config = config_from_file(str(props_file))

        assert config["bootstrap.servers"] == "localhost:9092"
        assert config["client.id"] == "test-client"
        assert len(config) == 2

    def test_config_from_json_file(self, tmp_path):
        """Should load config from .json file."""
        from hs_pylib.kafka.config import config_from_file

        json_file = tmp_path / "kafka.json"
        json_file.write_text("""{
    "bootstrap.servers": "kafka:9092",
    "security.protocol": "PLAINTEXT",
    "client.id": "my-app",
    "enable.idempotence": true,
    "retries": 5
}""")

        config = config_from_file(str(json_file))

        assert config["bootstrap.servers"] == "kafka:9092"
        assert config["security.protocol"] == "PLAINTEXT"
        assert config["client.id"] == "my-app"
        assert config["enable.idempotence"] is True
        assert config["retries"] == 5

    def test_config_from_yaml_file(self, tmp_path):
        """Should load config from .yaml file."""
        from hs_pylib.kafka.config import config_from_file

        yaml_file = tmp_path / "kafka.yaml"
        yaml_file.write_text("""
bootstrap.servers: kafka:9092
security.protocol: SASL_PLAINTEXT
sasl.mechanism: PLAIN
sasl.username: user
sasl.password: pass
""")

        config = config_from_file(str(yaml_file))

        assert config["bootstrap.servers"] == "kafka:9092"
        assert config["security.protocol"] == "SASL_PLAINTEXT"
        assert config["sasl.mechanism"] == "PLAIN"
        assert config["sasl.username"] == "user"
        assert config["sasl.password"] == "pass"

    def test_config_from_yml_file(self, tmp_path):
        """Should load config from .yml file."""
        from hs_pylib.kafka.config import config_from_file

        yml_file = tmp_path / "kafka.yml"
        yml_file.write_text("""
bootstrap.servers: localhost:9092
client.id: test
""")

        config = config_from_file(str(yml_file))

        assert config["bootstrap.servers"] == "localhost:9092"
        assert config["client.id"] == "test"

    def test_config_from_ini_file(self, tmp_path):
        """Should load config from .ini file with [kafka] section."""
        from hs_pylib.kafka.config import config_from_file

        ini_file = tmp_path / "kafka.ini"
        ini_file.write_text("""
[kafka]
bootstrap.servers = kafka:9092
security.protocol = PLAINTEXT
client.id = my-client
""")

        config = config_from_file(str(ini_file))

        assert config["bootstrap.servers"] == "kafka:9092"
        assert config["security.protocol"] == "PLAINTEXT"
        assert config["client.id"] == "my-client"

    def test_config_from_file_unsupported_extension(self, tmp_path):
        """Should raise error for unsupported file extension."""
        from hs_pylib.kafka.config import config_from_file

        txt_file = tmp_path / "kafka.txt"
        txt_file.write_text("bootstrap.servers=localhost:9092")

        with pytest.raises(ValueError, match="Unsupported"):
            config_from_file(str(txt_file))

    def test_config_from_file_not_found(self):
        """Should raise error for non-existent file."""
        from hs_pylib.kafka.config import config_from_file

        with pytest.raises(FileNotFoundError):
            config_from_file("/nonexistent/path/kafka.properties")

    def test_config_from_properties_with_equals_in_value(self, tmp_path):
        """Should handle values containing = sign."""
        from hs_pylib.kafka.config import config_from_file

        props_file = tmp_path / "kafka.properties"
        props_file.write_text("""
bootstrap.servers=localhost:9092
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="admin" password="pass=123";
""")

        config = config_from_file(str(props_file))

        assert config["bootstrap.servers"] == "localhost:9092"
        assert "password=" in config["sasl.jaas.config"]

    def test_config_from_file_with_explicit_format(self, tmp_path):
        """Should respect explicit format parameter."""
        from hs_pylib.kafka.config import config_from_file

        # File with wrong extension but contains properties format
        weird_file = tmp_path / "kafka.cfg"
        weird_file.write_text("""
bootstrap.servers=localhost:9092
client.id=test
""")

        config = config_from_file(str(weird_file), format="properties")

        assert config["bootstrap.servers"] == "localhost:9092"
        assert config["client.id"] == "test"


class TestConfigModuleExports:
    """Tests for config module exports."""

    def test_config_from_file_exported(self):
        """config_from_file should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import config_from_file

        assert callable(config_from_file)


# =============================================================================
# Phase 11: Kafka Admin Operations (Topic Config Changes)
# =============================================================================


class TestKafkaAdmin:
    """Tests for KafkaAdmin topic configuration operations."""

    @pytest.fixture
    def mock_admin_client_for_admin(self):
        """Mock AdminClient for KafkaAdmin tests."""
        with patch("hs_pylib.kafka.admin.AdminClient") as mock:
            yield mock

    def test_admin_init(self, mock_admin_client_for_admin):
        """KafkaAdmin should initialize with config."""
        from hs_pylib.kafka.admin import KafkaAdmin

        KafkaAdmin("localhost:9092")
        mock_admin_client_for_admin.assert_called_once()

    def test_admin_context_manager(self, mock_admin_client_for_admin):
        """KafkaAdmin should support context manager."""
        from hs_pylib.kafka.admin import KafkaAdmin

        with KafkaAdmin("localhost:9092") as admin:
            assert admin is not None

    def test_admin_increase_partitions(self, mock_admin_client_for_admin):
        """Should increase partition count for a topic."""
        from concurrent.futures import Future

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_future = Future()
        mock_future.set_result(None)
        mock_admin_client_for_admin.return_value.create_partitions.return_value = {"test-topic": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.increase_partitions("test-topic", 6)

        mock_admin_client_for_admin.return_value.create_partitions.assert_called_once()

    def test_admin_set_retention(self, mock_admin_client_for_admin):
        """Should set retention.ms for a topic."""
        from concurrent.futures import Future

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_future = Future()
        mock_future.set_result(None)
        mock_admin_client_for_admin.return_value.alter_configs.return_value = {"test-topic": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.set_retention("test-topic", hours=24)

        mock_admin_client_for_admin.return_value.alter_configs.assert_called_once()

    def test_admin_set_retention_ms(self, mock_admin_client_for_admin):
        """Should set retention.ms directly."""
        from concurrent.futures import Future

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_future = Future()
        mock_future.set_result(None)
        mock_admin_client_for_admin.return_value.alter_configs.return_value = {"test-topic": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.set_retention("test-topic", ms=86400000)  # 1 day

        mock_admin_client_for_admin.return_value.alter_configs.assert_called_once()

    def test_admin_get_topic_config(self, mock_admin_client_for_admin):
        """Should get topic configuration."""
        from concurrent.futures import Future

        from hs_pylib.kafka.admin import KafkaAdmin

        # Mock config result as dict[str, ConfigEntry]
        # The real API returns a dict where values are ConfigEntry objects
        mock_config = MagicMock()
        mock_config.name = "retention.ms"
        mock_config.value = "604800000"

        # Result is dict with string keys and ConfigEntry values
        mock_result = {"retention.ms": mock_config}

        mock_future = Future()
        mock_future.set_result(mock_result)
        mock_admin_client_for_admin.return_value.describe_configs.return_value = {"test-topic": mock_future}

        admin = KafkaAdmin("localhost:9092")
        config = admin.get_topic_config("test-topic")

        assert "retention.ms" in config
        assert config["retention.ms"] == "604800000"

    def test_admin_set_cleanup_policy(self, mock_admin_client_for_admin):
        """Should set cleanup.policy for a topic."""
        from concurrent.futures import Future

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_future = Future()
        mock_future.set_result(None)
        mock_admin_client_for_admin.return_value.alter_configs.return_value = {"test-topic": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.set_cleanup_policy("test-topic", "compact")

        mock_admin_client_for_admin.return_value.alter_configs.assert_called_once()

    def test_admin_alter_config(self, mock_admin_client_for_admin):
        """Should alter arbitrary topic config."""
        from concurrent.futures import Future

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_future = Future()
        mock_future.set_result(None)
        mock_admin_client_for_admin.return_value.alter_configs.return_value = {"test-topic": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.alter_config("test-topic", {"max.message.bytes": "1048576"})

        mock_admin_client_for_admin.return_value.alter_configs.assert_called_once()


class TestKafkaAdminExports:
    """Tests for KafkaAdmin module exports."""

    def test_kafka_admin_exported(self):
        """KafkaAdmin should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import KafkaAdmin

        assert KafkaAdmin is not None


# =============================================================================
# Phase 12: Consumer Group Offset Reset by Timestamp
# =============================================================================


class TestKafkaAdminOffsetReset:
    """Tests for consumer group offset reset operations."""

    @pytest.fixture
    def mock_admin_for_offset(self):
        """Mock AdminClient for offset reset tests."""
        # Import the module first to allow patching
        import hs_pylib.kafka.admin  # noqa: F401

        with (
            patch("hs_pylib.kafka.admin.AdminClient") as mock_admin,
            patch("hs_pylib.kafka.admin.Consumer") as mock_consumer,
        ):
            yield mock_admin, mock_consumer

    def test_reset_offsets_to_timestamp(self, mock_admin_for_offset):
        """Should reset consumer group offsets to a specific timestamp."""
        from concurrent.futures import Future

        from confluent_kafka import TopicPartition

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_admin, mock_consumer = mock_admin_for_offset

        # Mock list_topics to return topic with partitions
        mock_topic_meta = Mock()
        mock_topic_meta.partitions = {0: Mock(), 1: Mock(), 2: Mock()}
        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic_meta}
        mock_admin.return_value.list_topics.return_value = mock_metadata

        # Mock offsets_for_times
        mock_consumer.return_value.offsets_for_times.return_value = [
            TopicPartition("test-topic", 0, 100),
            TopicPartition("test-topic", 1, 200),
            TopicPartition("test-topic", 2, 300),
        ]

        # Mock alter_consumer_group_offsets
        mock_future = Future()
        mock_future.set_result(None)
        mock_admin.return_value.alter_consumer_group_offsets.return_value = {"test-group": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.reset_offsets_to_timestamp(
            group_id="test-group",
            topic="test-topic",
            timestamp_ms=1700000000000,
        )

        # Verify offsets_for_times was called
        mock_consumer.return_value.offsets_for_times.assert_called_once()

        # Verify alter_consumer_group_offsets was called
        mock_admin.return_value.alter_consumer_group_offsets.assert_called_once()

    def test_reset_offsets_to_datetime(self, mock_admin_for_offset):
        """Should reset offsets using datetime object."""
        from concurrent.futures import Future
        from datetime import datetime, timezone

        from confluent_kafka import TopicPartition

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_admin, mock_consumer = mock_admin_for_offset

        # Mock list_topics
        mock_topic_meta = Mock()
        mock_topic_meta.partitions = {0: Mock()}
        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic_meta}
        mock_admin.return_value.list_topics.return_value = mock_metadata

        # Mock offsets_for_times
        mock_consumer.return_value.offsets_for_times.return_value = [
            TopicPartition("test-topic", 0, 100),
        ]

        # Mock alter_consumer_group_offsets
        mock_future = Future()
        mock_future.set_result(None)
        mock_admin.return_value.alter_consumer_group_offsets.return_value = {"test-group": mock_future}

        admin = KafkaAdmin("localhost:9092")
        target_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        admin.reset_offsets_to_time(
            group_id="test-group",
            topic="test-topic",
            time=target_time,
        )

        mock_consumer.return_value.offsets_for_times.assert_called_once()

    def test_reset_offsets_to_earliest(self, mock_admin_for_offset):
        """Should reset offsets to earliest (beginning)."""
        from concurrent.futures import Future

        from confluent_kafka import OFFSET_BEGINNING, TopicPartition

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_admin, mock_consumer = mock_admin_for_offset

        # Mock list_topics
        mock_topic_meta = Mock()
        mock_topic_meta.partitions = {0: Mock(), 1: Mock()}
        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic_meta}
        mock_admin.return_value.list_topics.return_value = mock_metadata

        # Mock get_watermark_offsets (returns low, high)
        mock_consumer.return_value.get_watermark_offsets.side_effect = [
            (0, 100),  # partition 0
            (0, 200),  # partition 1
        ]

        # Mock alter_consumer_group_offsets
        mock_future = Future()
        mock_future.set_result(None)
        mock_admin.return_value.alter_consumer_group_offsets.return_value = {"test-group": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.reset_offsets_to_earliest(
            group_id="test-group",
            topic="test-topic",
        )

        mock_admin.return_value.alter_consumer_group_offsets.assert_called_once()

    def test_reset_offsets_to_latest(self, mock_admin_for_offset):
        """Should reset offsets to latest (end)."""
        from concurrent.futures import Future

        from hs_pylib.kafka.admin import KafkaAdmin

        mock_admin, mock_consumer = mock_admin_for_offset

        # Mock list_topics
        mock_topic_meta = Mock()
        mock_topic_meta.partitions = {0: Mock()}
        mock_metadata = Mock()
        mock_metadata.topics = {"test-topic": mock_topic_meta}
        mock_admin.return_value.list_topics.return_value = mock_metadata

        # Mock get_watermark_offsets
        mock_consumer.return_value.get_watermark_offsets.return_value = (0, 500)

        # Mock alter_consumer_group_offsets
        mock_future = Future()
        mock_future.set_result(None)
        mock_admin.return_value.alter_consumer_group_offsets.return_value = {"test-group": mock_future}

        admin = KafkaAdmin("localhost:9092")
        admin.reset_offsets_to_latest(
            group_id="test-group",
            topic="test-topic",
        )

        mock_admin.return_value.alter_consumer_group_offsets.assert_called_once()


# =============================================================================
# Phase 13: Kafka Consumer Health Monitoring
# =============================================================================


class TestKafkaConsumerHealth:
    """Tests for Kafka consumer health monitoring."""

    @pytest.fixture
    def mock_collector(self):
        """Create a mock metrics collector."""
        collector = Mock()
        collector.get_cgrp_metrics.return_value = {}
        collector.get_partition_metrics.return_value = {}
        collector.get_broker_metrics.return_value = {}
        collector.get_consumer_lag.return_value = {}
        return collector

    def test_health_monitor_init(self, mock_collector):
        """KafkaConsumerHealth should initialize with defaults."""
        from hs_pylib.kafka.health import KafkaConsumerHealth

        health = KafkaConsumerHealth(collector=mock_collector)
        assert health.warning_rate_limit_sec == 60
        assert health.lag_threshold == 10000
        assert health.rebalance_threshold == 3
        assert health.rebalance_window_sec == 300

    def test_health_monitor_custom_config(self, mock_collector):
        """KafkaConsumerHealth should accept custom config."""
        from hs_pylib.kafka.health import KafkaConsumerHealth

        health = KafkaConsumerHealth(
            collector=mock_collector,
            warning_rate_limit_sec=30,
            lag_threshold=5000,
            rebalance_threshold=5,
            rebalance_window_sec=600,
        )
        assert health.warning_rate_limit_sec == 30
        assert health.lag_threshold == 5000
        assert health.rebalance_threshold == 5
        assert health.rebalance_window_sec == 600

    def test_health_from_config(self, mock_collector, monkeypatch):
        """from_config should load from environment variables."""
        from hs_pylib.kafka.health import KafkaConsumerHealth

        monkeypatch.setenv("KAFKA_HEALTH_WARNING_RATE_LIMIT_SEC", "45")
        monkeypatch.setenv("KAFKA_HEALTH_LAG_THRESHOLD", "8000")

        health = KafkaConsumerHealth.from_config(collector=mock_collector)
        assert health.warning_rate_limit_sec == 45
        assert health.lag_threshold == 8000

    def test_health_check_no_partitions(self, mock_collector):
        """Should detect no partitions assigned."""
        from hs_pylib.kafka.health import HealthIssue, KafkaConsumerHealth

        mock_collector.get_cgrp_metrics.return_value = {
            "state": "up",
            "assignment_size": 0,
            "rebalance_cnt": 1,
        }

        health = KafkaConsumerHealth(collector=mock_collector)
        results = health.check_health()
        issues = [r.issue for r in results]
        assert HealthIssue.NO_PARTITIONS in issues

    def test_health_check_high_lag(self, mock_collector):
        """Should detect high consumer lag."""
        from hs_pylib.kafka.health import HealthIssue, KafkaConsumerHealth

        mock_collector.get_cgrp_metrics.return_value = {
            "state": "up",
            "assignment_size": 2,
            "rebalance_cnt": 1,
        }
        mock_collector.get_consumer_lag.return_value = {
            "test-topic": {0: 15000, 1: 500},
        }

        health = KafkaConsumerHealth(collector=mock_collector, lag_threshold=1000)
        results = health.check_health()
        issues = [r.issue for r in results]
        assert HealthIssue.HIGH_LAG in issues

    def test_health_check_frequent_rebalances(self, mock_collector):
        """Should detect frequent rebalances."""
        import time

        from hs_pylib.kafka.health import HealthIssue, KafkaConsumerHealth

        mock_collector.get_cgrp_metrics.return_value = {
            "state": "up",
            "assignment_size": 2,
            "rebalance_cnt": 5,
        }

        health = KafkaConsumerHealth(
            collector=mock_collector,
            rebalance_threshold=3,
            rebalance_window_sec=300,
        )

        # Simulate multiple rebalances
        now = time.time()
        health._rebalance_times.extend([now - 10, now - 5, now - 2])
        health._last_rebalance_cnt = 2  # Trigger new rebalance detection

        results = health.check_health()
        issues = [r.issue for r in results]
        assert HealthIssue.FREQUENT_REBALANCES in issues

    def test_health_check_insufficient_partitions(self, mock_collector):
        """Should detect insufficient partitions for consumer count."""
        from hs_pylib.kafka.health import HealthIssue, KafkaConsumerHealth

        mock_collector.get_cgrp_metrics.return_value = {
            "state": "up",
            "assignment_size": 2,
            "rebalance_cnt": 1,
        }
        mock_collector.get_partition_metrics.return_value = {
            "test-topic": {0: {}, 1: {}},  # Only 2 partitions
        }

        # 5 consumers but only 2 partitions
        health = KafkaConsumerHealth(collector=mock_collector, consumer_count=5)
        results = health.check_health()
        issues = [r.issue for r in results]
        assert HealthIssue.INSUFFICIENT_PARTITIONS in issues

    def test_health_rate_limiting(self, mock_collector):
        """Should rate limit warnings."""
        from hs_pylib.kafka.health import KafkaConsumerHealth

        mock_collector.get_cgrp_metrics.return_value = {
            "state": "up",
            "assignment_size": 0,
            "rebalance_cnt": 1,
        }

        health = KafkaConsumerHealth(collector=mock_collector, warning_rate_limit_sec=60)

        # First check - should return issues (and log them)
        results1 = health.check_health()
        assert len(results1) > 0

        # Issues are always returned, but logging is rate-limited
        # The _last_warnings dict tracks when warnings were logged
        assert len(health._last_warnings) > 0

    def test_health_metrics(self, mock_collector):
        """Should provide metrics dictionary."""
        from hs_pylib.kafka.health import KafkaConsumerHealth

        mock_collector.get_cgrp_metrics.return_value = {
            "state": "up",
            "assignment_size": 4,
            "rebalance_cnt": 2,
        }
        mock_collector.get_partition_metrics.return_value = {
            "topic1": {0: {}, 1: {}},
        }
        mock_collector.get_consumer_lag.return_value = {
            "topic1": {0: 100, 1: 200},
        }

        health = KafkaConsumerHealth(collector=mock_collector)
        metrics = health.get_health_metrics()

        assert "kafka_consumer_partitions_assigned" in metrics
        assert metrics["kafka_consumer_partitions_assigned"] == 2
        assert "kafka_consumer_rebalance_total" in metrics
        assert "kafka_consumer_lag_total" in metrics


class TestHealthIssueEnum:
    """Tests for HealthIssue enum."""

    def test_health_issue_values(self):
        """HealthIssue should have expected values."""
        from hs_pylib.kafka.health import HealthIssue

        assert HealthIssue.NO_PARTITIONS
        assert HealthIssue.INSUFFICIENT_PARTITIONS
        assert HealthIssue.FREQUENT_REBALANCES
        assert HealthIssue.LAG_GROWING
        assert HealthIssue.PARTITION_IMBALANCE
        assert HealthIssue.FETCH_ERRORS
        assert HealthIssue.BROKER_DISCONNECTED
        assert HealthIssue.HIGH_LAG


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_health_result_creation(self):
        """HealthCheckResult should store issue details."""
        from hs_pylib.kafka.health import HealthCheckResult, HealthIssue

        result = HealthCheckResult(
            issue=HealthIssue.HIGH_LAG,
            severity="warning",
            message="Partition 0 lag is 5000 (threshold: 1000)",
            details={"partition": 0, "lag": 5000, "threshold": 1000},
        )

        assert result.issue == HealthIssue.HIGH_LAG
        assert result.severity == "warning"
        assert "5000" in result.message
        assert result.details["partition"] == 0


class TestKafkaHealthExports:
    """Tests for health module exports."""

    def test_health_classes_exported(self):
        """Health classes should be importable from hs_pylib.kafka."""
        from hs_pylib.kafka import (
            HealthCheckResult,
            HealthIssue,
            KafkaConsumerHealth,
        )

        assert KafkaConsumerHealth is not None
        assert HealthCheckResult is not None
        assert HealthIssue is not None
