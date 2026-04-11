"""Unit tests for secrets types."""

from datetime import UTC, datetime, timedelta

import pytest

from hyperi_pylib.secrets.types import (
    AWSConfig,
    CacheConfig,
    OpenBaoConfig,
    ProviderType,
    RotationEvent,
    SecretFilter,
    SecretMetadata,
    SecretValue,
    SourceConfig,
)


class TestSecretValue:
    """Tests for SecretValue dataclass."""

    def test_create_secret_value(self):
        """Test creating a SecretValue."""
        data = b"secret-data"
        fetched_at = datetime.now(UTC)

        value = SecretValue(
            data=data,
            fetched_at=fetched_at,
            version="v1",
            source="test",
        )

        assert value.data == data
        assert value.fetched_at == fetched_at
        assert value.version == "v1"
        assert value.source == "test"

    def test_decode(self):
        """Test decoding secret data to string."""
        value = SecretValue(
            data=b"hello world",
            fetched_at=datetime.now(UTC),
        )

        assert value.decode() == "hello world"

    def test_decode_custom_encoding(self):
        """Test decoding with custom encoding."""
        value = SecretValue(
            data="héllo".encode("latin-1"),
            fetched_at=datetime.now(UTC),
        )

        assert value.decode("latin-1") == "héllo"

    def test_is_expired_false(self):
        """Test secret not expired within TTL."""
        value = SecretValue(
            data=b"data",
            fetched_at=datetime.now(UTC),
        )

        assert value.is_expired(ttl_secs=3600) is False

    def test_is_expired_true(self):
        """Test secret expired after TTL."""
        old_time = datetime.now(UTC) - timedelta(hours=2)
        value = SecretValue(
            data=b"data",
            fetched_at=old_time,
        )

        assert value.is_expired(ttl_secs=3600) is True

    def test_is_within_grace_true(self):
        """Test secret within grace period."""
        # 90 minutes old, TTL is 60 min, grace is 60 min
        old_time = datetime.now(UTC) - timedelta(minutes=90)
        value = SecretValue(
            data=b"data",
            fetched_at=old_time,
        )

        assert value.is_expired(ttl_secs=3600) is True
        assert value.is_within_grace(ttl_secs=3600, grace_secs=3600) is True

    def test_is_within_grace_false(self):
        """Test secret beyond grace period."""
        # 3 hours old, TTL is 1 hour, grace is 1 hour
        old_time = datetime.now(UTC) - timedelta(hours=3)
        value = SecretValue(
            data=b"data",
            fetched_at=old_time,
        )

        assert value.is_within_grace(ttl_secs=3600, grace_secs=3600) is False


class TestRotationEvent:
    """Tests for RotationEvent dataclass."""

    def test_create_rotation_event(self):
        """Test creating a RotationEvent."""
        event = RotationEvent(
            name="my-secret",
            old_version="v1",
            new_version="v2",
            rotated_at=datetime.now(UTC),
        )

        assert event.name == "my-secret"
        assert event.old_version == "v1"
        assert event.new_version == "v2"


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""

    def test_defaults(self):
        """Test CacheConfig default values."""
        config = CacheConfig()

        assert config.enabled is True
        assert config.directory is None
        assert config.ttl_secs == 3600
        assert config.stale_grace_secs == 86400
        assert config.refresh_interval_secs == 1800
        assert config.refresh_jitter_secs == 300
        assert config.encryption_key is None

    def test_custom_values(self):
        """Test CacheConfig with custom values."""
        config = CacheConfig(
            enabled=False,
            directory="/tmp/cache",
            ttl_secs=1800,
            encryption_key=b"secret-key",
        )

        assert config.enabled is False
        assert config.directory == "/tmp/cache"
        assert config.ttl_secs == 1800
        assert config.encryption_key == b"secret-key"


class TestSourceConfig:
    """Tests for SourceConfig dataclass."""

    def test_file_source(self):
        """Test file source config."""
        config = SourceConfig(
            provider=ProviderType.FILE,
            path="/etc/secrets/api-key",
        )

        assert config.provider == ProviderType.FILE
        assert config.path == "/etc/secrets/api-key"

    def test_vault_source_with_key(self):
        """Test Vault source config with key extraction."""
        config = SourceConfig(
            provider=ProviderType.OPENBAO,
            path="secret/data/myapp/config",
            key="api_key",
        )

        assert config.provider == ProviderType.OPENBAO
        assert config.path == "secret/data/myapp/config"
        assert config.key == "api_key"

    def test_aws_source(self):
        """Test AWS source config."""
        config = SourceConfig(
            provider=ProviderType.AWS,
            secret_id="my-secret",
            key="password",
        )

        assert config.provider == ProviderType.AWS
        assert config.secret_id == "my-secret"
        assert config.key == "password"


class TestOpenBaoConfig:
    """Tests for OpenBaoConfig dataclass."""

    def test_defaults(self):
        """Test OpenBaoConfig default values."""
        config = OpenBaoConfig(address="https://vault:8200")

        assert config.address == "https://vault:8200"
        assert config.auth_method == "token"
        assert config.token is None
        assert config.role_id is None
        assert config.secret_id is None
        assert config.role is None
        assert config.token_path == "/var/run/secrets/kubernetes.io/serviceaccount/token"
        assert config.namespace is None
        assert config.skip_verify is False
        assert config.timeout_secs == 30

    def test_approle_config(self):
        """Test AppRole configuration."""
        config = OpenBaoConfig(
            address="https://vault:8200",
            auth_method="approle",
            role_id="my-role-id",
            secret_id="my-secret-id",
            mount="custom-approle",
        )

        assert config.auth_method == "approle"
        assert config.role_id == "my-role-id"
        assert config.secret_id == "my-secret-id"
        assert config.mount == "custom-approle"

    def test_kubernetes_config(self):
        """Test Kubernetes auth configuration."""
        config = OpenBaoConfig(
            address="https://vault:8200",
            auth_method="kubernetes",
            role="my-k8s-role",
            token_path="/custom/token",
        )

        assert config.auth_method == "kubernetes"
        assert config.role == "my-k8s-role"
        assert config.token_path == "/custom/token"


class TestAWSConfig:
    """Tests for AWSConfig dataclass."""

    def test_defaults(self):
        """Test AWSConfig default values."""
        config = AWSConfig()

        assert config.region == "us-east-1"
        assert config.access_key_id is None
        assert config.secret_access_key is None
        assert config.endpoint_url is None
        assert config.timeout_secs == 30

    def test_custom_config(self):
        """Test custom AWS configuration."""
        config = AWSConfig(
            region="eu-west-1",
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            endpoint_url="http://localhost:4566",  # LocalStack
        )

        assert config.region == "eu-west-1"
        assert config.access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert config.endpoint_url == "http://localhost:4566"


class TestProviderType:
    """Tests for ProviderType enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert ProviderType.FILE.value == "file"
        assert ProviderType.OPENBAO.value == "openbao"
        assert ProviderType.AWS.value == "aws"


class TestSecretMetadata:
    """Tests for SecretMetadata dataclass."""

    def test_minimal_metadata(self):
        """All fields beyond name are optional."""
        md = SecretMetadata(name="api_key")
        assert md.name == "api_key"
        assert md.created_at is None
        assert md.updated_at is None
        assert md.expires_at is None
        assert md.version is None
        assert md.version_count is None
        assert md.tags is None
        assert md.source == "unknown"

    def test_full_metadata(self):
        now = datetime.now(UTC)
        md = SecretMetadata(
            name="api_key",
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=30),
            version="v3",
            version_count=3,
            tags={"env": "prod", "team": "platform"},
            source="aws",
        )
        assert md.version == "v3"
        assert md.version_count == 3
        assert md.tags == {"env": "prod", "team": "platform"}
        assert md.source == "aws"


class TestSecretFilter:
    """Tests for SecretFilter dataclass."""

    def test_empty_filter(self):
        """All fields optional — empty filter is valid."""
        f = SecretFilter()
        assert f.prefix is None
        assert f.tags is None
        assert f.pattern is None

    def test_prefix_only(self):
        f = SecretFilter(prefix="secret/myapp/")
        assert f.prefix == "secret/myapp/"

    def test_tags_filter(self):
        f = SecretFilter(tags={"env": "prod"})
        assert f.tags == {"env": "prod"}

    def test_combined_filter(self):
        f = SecretFilter(prefix="secret/", tags={"team": "platform"}, pattern="*_key")
        assert f.prefix == "secret/"
        assert f.tags == {"team": "platform"}
        assert f.pattern == "*_key"
