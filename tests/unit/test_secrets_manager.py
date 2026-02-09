"""Unit tests for secrets manager."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hyperi_pylib.secrets.exceptions import (
    ProviderNotConfiguredError,
    SecretNotFoundError,
)
from hyperi_pylib.secrets.manager import SecretsManager
from hyperi_pylib.secrets.types import CacheConfig, RotationEvent, SecretValue


class TestSecretsManager:
    """Tests for SecretsManager."""

    def test_default_construction(self):
        """Test creating manager with defaults."""
        manager = SecretsManager()

        assert manager._file_provider is not None
        assert manager._cache is not None

    def test_cache_disabled(self, tmp_path):
        """Test manager with caching disabled."""
        manager = SecretsManager(cache=CacheConfig(enabled=False))

        # File provider should still work
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("my-value")

        result = manager.get_sync(str(secret_file))
        assert result.decode() == "my-value"

    def test_get_sync_file_provider(self, tmp_path):
        """Test synchronous get from file provider."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("sync-secret")

        manager = SecretsManager()
        result = manager.get_sync(str(secret_file))

        assert result.decode() == "sync-secret"
        assert result.source == "file"

    @pytest.mark.asyncio
    async def test_get_async_file_provider(self, tmp_path):
        """Test async get from file provider."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("async-secret")

        manager = SecretsManager()
        result = await manager.get(str(secret_file))

        assert result.decode() == "async-secret"

    def test_get_string(self, tmp_path):
        """Test get_string convenience method."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("string-value")

        manager = SecretsManager()
        result = manager.get_string_sync(str(secret_file))

        assert result == "string-value"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_string_async(self, tmp_path):
        """Test async get_string."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("async-string")

        manager = SecretsManager()
        result = await manager.get_string(str(secret_file))

        assert result == "async-string"

    def test_memory_cache_hit(self, tmp_path):
        """Test that memory cache is used on second access."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("original-value")

        # Use custom cache config with short TTL for testing
        cache_config = CacheConfig(
            enabled=True,
            directory=str(tmp_path / "cache"),
            ttl_secs=3600,
        )
        manager = SecretsManager(cache=cache_config)

        # First access - from file
        result1 = manager.get_sync(str(secret_file))
        assert result1.decode() == "original-value"

        # Modify file
        secret_file.write_text("new-value")

        # Second access should use memory cache
        result2 = manager.get_sync(str(secret_file))
        assert result2.decode() == "original-value"  # Still cached

    def test_disk_cache_persistence(self, tmp_path):
        """Test that disk cache persists across manager instances."""
        secret_file = tmp_path / "secret.txt"
        cache_dir = tmp_path / "cache"
        secret_file.write_text("persistent-value")

        cache_config = CacheConfig(enabled=True, directory=str(cache_dir))

        # First manager - populate cache
        manager1 = SecretsManager(cache=cache_config)
        result1 = manager1.get_sync(str(secret_file))
        assert result1.decode() == "persistent-value"

        # Delete the original file
        secret_file.unlink()

        # Second manager - should use disk cache
        manager2 = SecretsManager(cache=cache_config)
        # Clear memory cache (new instance has empty memory cache)
        result2 = manager2.get_sync(str(secret_file))
        assert result2.decode() == "persistent-value"

    def test_json_key_extraction(self, tmp_path):
        """Test extracting specific key from JSON secret."""
        secret_file = tmp_path / "secrets.json"
        secret_file.write_text('{"api_key": "secret123", "other": "value"}')

        manager = SecretsManager()
        result = manager.get_sync(str(secret_file), key="api_key")

        assert result.decode() == "secret123"

    def test_provider_not_configured(self):
        """Test error when requesting unconfigured provider."""
        manager = SecretsManager()  # No OpenBao configured

        with pytest.raises(ProviderNotConfiguredError):
            manager.get_sync("secret/path", provider="openbao")

    def test_rotation_callback(self, tmp_path):
        """Test rotation callback is called when version changes.

        Rotation is detected when a provider fetch returns a different version
        than what was previously cached in memory.
        """
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("value-v1")

        events = []

        def on_rotation(event: RotationEvent):
            events.append(event)

        cache_config = CacheConfig(
            enabled=False,  # Disable disk caching to simplify test
            directory=str(tmp_path / "cache"),
            ttl_secs=0,  # TTL of 0 means always re-fetch
        )
        manager = SecretsManager(cache=cache_config)
        cache_key = f"file:{secret_file}:"
        manager.on_rotation(on_rotation, names=[cache_key])

        # First fetch - stores in memory cache
        result1 = manager.get_sync(str(secret_file))
        assert result1.decode() == "value-v1"

        # Modify file (changes version based on mtime)
        import time

        time.sleep(0.1)  # Ensure mtime changes
        secret_file.write_text("value-v2")

        # Second fetch - cache is expired (ttl=0), so will re-fetch from provider
        # This should detect rotation since version changed
        result2 = manager.get_sync(str(secret_file))
        assert result2.decode() == "value-v2"

        # Callback should have been called
        assert len(events) == 1
        assert secret_file.name in events[0].name

    def test_health_check_sync(self):
        """Test sync health check."""
        manager = SecretsManager()
        health = manager.health_check_sync()

        assert "file" in health
        assert health["file"] is True

    @pytest.mark.asyncio
    async def test_health_check_async(self):
        """Test async health check."""
        manager = SecretsManager()
        health = await manager.health_check()

        assert "file" in health
        assert health["file"] is True

    def test_multiple_secrets(self, tmp_path):
        """Test fetching multiple different secrets."""
        (tmp_path / "secret1.txt").write_text("value1")
        (tmp_path / "secret2.txt").write_text("value2")
        (tmp_path / "secret3.txt").write_text("value3")

        manager = SecretsManager()

        r1 = manager.get_sync(str(tmp_path / "secret1.txt"))
        r2 = manager.get_sync(str(tmp_path / "secret2.txt"))
        r3 = manager.get_sync(str(tmp_path / "secret3.txt"))

        assert r1.decode() == "value1"
        assert r2.decode() == "value2"
        assert r3.decode() == "value3"

    def test_secret_not_found_not_cached(self, tmp_path):
        """Test that SecretNotFoundError is raised and nothing is cached."""
        cache_dir = tmp_path / "cache"
        manager = SecretsManager(cache=CacheConfig(enabled=True, directory=str(cache_dir)))

        with pytest.raises(SecretNotFoundError):
            manager.get_sync(str(tmp_path / "nonexistent.txt"))

        # Nothing should be in cache
        assert len(list(cache_dir.glob("*.cache"))) == 0

    def test_file_provider_always_default(self, tmp_path):
        """Test that file provider is used by default for file paths."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("file-value")

        manager = SecretsManager()

        # No provider specified - should auto-detect file
        result = manager.get_sync(str(secret_file))
        assert result.source == "file"

    def test_class_level_cache(self, tmp_path):
        """Test that memory cache is class-level (shared across instances)."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("shared-value")

        cache_config = CacheConfig(
            enabled=True,
            directory=str(tmp_path / "cache"),
        )

        # First instance
        manager1 = SecretsManager(cache=cache_config)
        manager1.get_sync(str(secret_file))

        # Modify file
        secret_file.write_text("new-value")

        # Second instance should still get cached value from class-level cache
        manager2 = SecretsManager(cache=cache_config)
        result = manager2.get_sync(str(secret_file))

        # Class-level memory cache should return original value
        assert result.decode() == "shared-value"

    def test_explicit_file_provider(self, tmp_path):
        """Test explicitly requesting file provider."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("explicit-file")

        manager = SecretsManager()
        result = manager.get_sync(str(secret_file), provider="file")

        assert result.decode() == "explicit-file"
        assert result.source == "file"


class TestSecretsManagerWithMockedProviders:
    """Tests with mocked optional providers."""

    @pytest.mark.asyncio
    async def test_openbao_provider_mocked(self, tmp_path):
        """Test OpenBao provider with mocked httpx."""
        # Skip if httpx not available
        pytest.importorskip("httpx")

        from hyperi_pylib.secrets.types import OpenBaoConfig

        mock_value = SecretValue(
            data=b"vault-secret",
            fetched_at=datetime.now(UTC),
            version="1",
            source="openbao",
        )

        with patch("hyperi_pylib.secrets.providers.openbao.OpenBaoProvider") as MockProvider:
            mock_instance = MagicMock()
            mock_instance.name = "openbao"
            mock_instance.get_async = AsyncMock(return_value=mock_value)
            mock_instance.health_check_async = AsyncMock(return_value=True)
            MockProvider.return_value = mock_instance

            # Config would be used to construct the provider normally
            _ = OpenBaoConfig(
                address="https://vault:8200",
                token="test-token",
            )

            # Manually set the mocked provider
            manager = SecretsManager()
            manager._providers["openbao"] = mock_instance

            result = await manager.get("secret/data/myapp", provider="openbao")
            assert result.decode() == "vault-secret"

    @pytest.mark.asyncio
    async def test_aws_provider_mocked(self, tmp_path):
        """Test AWS provider with mocked boto3."""
        # Skip if boto3 not available
        pytest.importorskip("boto3")

        from hyperi_pylib.secrets.types import AWSConfig

        mock_value = SecretValue(
            data=b"aws-secret",
            fetched_at=datetime.now(UTC),
            version="arn:aws:secretsmanager:...",
            source="aws",
        )

        with patch("hyperi_pylib.secrets.providers.aws.AWSProvider") as MockProvider:
            mock_instance = MagicMock()
            mock_instance.name = "aws"
            mock_instance.get_async = AsyncMock(return_value=mock_value)
            mock_instance.health_check_async = AsyncMock(return_value=True)
            MockProvider.return_value = mock_instance

            # Config would be used to construct the provider normally
            _ = AWSConfig(region="us-west-2")

            # Manually set the mocked provider
            manager = SecretsManager()
            manager._providers["aws"] = mock_instance

            result = await manager.get("my-secret", provider="aws")
            assert result.decode() == "aws-secret"
