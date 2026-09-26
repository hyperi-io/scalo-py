"""Unit tests for secrets disk cache."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scalo.secrets.cache import DiskCache
from scalo.secrets.types import CacheConfig, SecretValue


class TestDiskCache:
    """Tests for DiskCache."""

    def test_cache_disabled(self, tmp_path):
        """Test that disabled cache always returns None."""
        config = CacheConfig(enabled=False, directory=str(tmp_path))
        cache = DiskCache(config)

        # Set should be no-op
        value = SecretValue(data=b"test", fetched_at=datetime.now(UTC))
        cache.set("my-secret", value)

        # Get should return None
        assert cache.get("my-secret") is None

    def test_set_and_get(self, tmp_path):
        """Test basic set and get."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        value = SecretValue(
            data=b"secret-data",
            fetched_at=datetime.now(UTC),
            version="v1",
            source="test",
        )
        cache.set("my-secret", value)

        result = cache.get("my-secret")
        assert result is not None
        assert result.data == b"secret-data"
        assert result.version == "v1"
        assert result.source == "test"

    def test_cache_miss(self, tmp_path):
        """Test cache miss returns None."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self, tmp_path):
        """Test that expired cache entries are not returned."""
        config = CacheConfig(
            enabled=True,
            directory=str(tmp_path),
            ttl_secs=60,
            stale_grace_secs=0,  # No grace period
        )
        cache = DiskCache(config)

        # Create value that's already expired
        old_time = datetime.now(UTC) - timedelta(minutes=5)
        value = SecretValue(data=b"old-data", fetched_at=old_time)
        cache.set("expired-secret", value)

        # Should return None because TTL exceeded and no grace
        result = cache.get("expired-secret")
        assert result is None

    def test_stale_grace_period(self, tmp_path):
        """Test that stale entries within grace period are returned."""
        config = CacheConfig(
            enabled=True,
            directory=str(tmp_path),
            ttl_secs=60,  # 1 minute TTL
            stale_grace_secs=3600,  # 1 hour grace
        )
        cache = DiskCache(config)

        # Create value that's past TTL but within grace
        old_time = datetime.now(UTC) - timedelta(minutes=30)
        value = SecretValue(data=b"stale-data", fetched_at=old_time)
        cache.set("stale-secret", value)

        # Should return stale value because within grace period
        result = cache.get("stale-secret")
        assert result is not None
        assert result.data == b"stale-data"

    def test_beyond_grace_period(self, tmp_path):
        """Test that entries beyond grace period are deleted."""
        config = CacheConfig(
            enabled=True,
            directory=str(tmp_path),
            ttl_secs=60,
            stale_grace_secs=60,  # Only 1 minute grace
        )
        cache = DiskCache(config)

        # Create value that's way past grace period
        old_time = datetime.now(UTC) - timedelta(hours=2)
        value = SecretValue(data=b"very-old", fetched_at=old_time)
        cache.set("very-old-secret", value)

        # Should return None and delete the file
        result = cache.get("very-old-secret")
        assert result is None

    def test_delete(self, tmp_path):
        """Test deleting cache entry."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        value = SecretValue(data=b"data", fetched_at=datetime.now(UTC))
        cache.set("to-delete", value)

        assert cache.get("to-delete") is not None
        assert cache.delete("to-delete") is True
        assert cache.get("to-delete") is None

    def test_delete_nonexistent(self, tmp_path):
        """Test deleting nonexistent entry."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        # Should not raise, returns True (idempotent)
        assert cache.delete("nonexistent") is True

    def test_clear(self, tmp_path):
        """Test clearing all cache entries."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        # Add multiple entries
        for i in range(5):
            value = SecretValue(data=f"data-{i}".encode(), fetched_at=datetime.now(UTC))
            cache.set(f"secret-{i}", value)

        count = cache.clear()
        assert count == 5

        # All should be gone
        for i in range(5):
            assert cache.get(f"secret-{i}") is None

    def test_encrypted_cache(self, tmp_path):
        """Test cache with encryption enabled."""
        config = CacheConfig(
            enabled=True,
            directory=str(tmp_path),
            encryption_key=b"my-secret-encryption-key",
        )
        cache = DiskCache(config)

        value = SecretValue(data=b"sensitive-data", fetched_at=datetime.now(UTC))
        cache.set("encrypted-secret", value)

        cache_files = list(tmp_path.glob("*.cache"))
        assert len(cache_files) == 1

        raw_content = cache_files[0].read_bytes()
        # The AES-256-GCM envelope is JSON, but must not leak the
        # plaintext secret (nor its hex-encoded plaintext payload).
        assert b"sensitive-data" not in raw_content
        assert b"sensitive-data".hex().encode() not in raw_content
        assert b"data_hex" not in raw_content
        envelope = json.loads(raw_content.decode("utf-8"))
        assert envelope["v"] == 1
        assert "nonce" in envelope
        assert "ct" in envelope

        # But cache.get should decrypt and return original value
        result = cache.get("encrypted-secret")
        assert result is not None
        assert result.data == b"sensitive-data"

    def test_encryption_key_mismatch(self, tmp_path):
        """Test that wrong encryption key fails gracefully."""
        # Create cache with one key
        config1 = CacheConfig(
            enabled=True,
            directory=str(tmp_path),
            encryption_key=b"key-one",
        )
        cache1 = DiskCache(config1)

        value = SecretValue(data=b"data", fetched_at=datetime.now(UTC))
        cache1.set("secret", value)

        # Try to read with different key
        config2 = CacheConfig(
            enabled=True,
            directory=str(tmp_path),
            encryption_key=b"key-two",
        )
        cache2 = DiskCache(config2)

        # Should return None (decryption fails gracefully)
        result = cache2.get("secret")
        assert result is None

    def test_string_encryption_key(self, tmp_path):
        """Test that string encryption keys work."""
        config = CacheConfig(
            enabled=True,
            directory=str(tmp_path),
            encryption_key="my-string-key",  # type: ignore[arg-type]
        )
        cache = DiskCache(config)

        value = SecretValue(data=b"data", fetched_at=datetime.now(UTC))
        cache.set("secret", value)

        result = cache.get("secret")
        assert result is not None
        assert result.data == b"data"

    def test_special_characters_in_name(self, tmp_path):
        """Test handling secret names with special characters."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        # Names that might cause filesystem issues
        names = [
            "path/to/secret",
            "secret:with:colons",
            "secret with spaces",
            "émojis-🔐-work",
        ]

        for name in names:
            value = SecretValue(data=f"value-for-{name}".encode(), fetched_at=datetime.now(UTC))
            cache.set(name, value)

            result = cache.get(name)
            assert result is not None, f"Failed for name: {name}"
            assert result.decode() == f"value-for-{name}"

    def test_auto_directory_resolution_xdg(self, tmp_path, monkeypatch):
        """Test automatic directory resolution with XDG_CACHE_HOME."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
        monkeypatch.delenv("SECRETS_CACHE_DIR", raising=False)

        config = CacheConfig(enabled=True, directory=None)
        cache = DiskCache(config)

        # Should resolve to XDG_CACHE_HOME/hs-secrets
        assert "xdg-cache" in str(cache._directory)
        assert "hs-secrets" in str(cache._directory)

    def test_auto_directory_resolution_env(self, tmp_path, monkeypatch):
        """Test automatic directory resolution with SECRETS_CACHE_DIR."""
        custom_dir = tmp_path / "custom-cache"
        monkeypatch.setenv("SECRETS_CACHE_DIR", str(custom_dir))

        config = CacheConfig(enabled=True, directory=None)
        cache = DiskCache(config)

        assert cache._directory == custom_dir

    def test_atomic_write(self, tmp_path):
        """Test that writes are atomic (temp file then rename)."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        value = SecretValue(data=b"data", fetched_at=datetime.now(UTC))
        cache.set("atomic-test", value)

        # Should not have any .tmp files left over
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

        # Should have one .cache file
        cache_files = list(tmp_path.glob("*.cache"))
        assert len(cache_files) == 1

    def test_config_property(self, tmp_path):
        """Test that config property returns the configuration."""
        config = CacheConfig(enabled=True, directory=str(tmp_path), ttl_secs=1234)
        cache = DiskCache(config)

        assert cache.config is config
        assert cache.config.ttl_secs == 1234

    def test_binary_data_roundtrip(self, tmp_path):
        """Test caching binary data with various byte values."""
        config = CacheConfig(enabled=True, directory=str(tmp_path))
        cache = DiskCache(config)

        # Include all byte values
        binary_data = bytes(range(256))
        value = SecretValue(data=binary_data, fetched_at=datetime.now(UTC))
        cache.set("binary-secret", value)

        result = cache.get("binary-secret")
        assert result is not None
        assert result.data == binary_data


class TestDiskCacheLogsNameNotValue:
    """Every cache log record names the secret and never carries its value."""

    NAME = "vault:app/db:password"
    VALUE = b"s3cr3t-value-7f3a9c"

    def _assert_no_value_logged(self, caplog) -> None:
        records = [r for r in caplog.records if r.name == "scalo.secrets.cache"]
        assert records, "expected at least one cache log record"
        for record in records:
            fields = " ".join(str(v) for v in vars(record).values())
            assert self.VALUE.decode() not in fields
            assert self.VALUE.hex() not in fields
            assert getattr(record, "secret_name", None) == self.NAME

    def _entry(self, fetched_at: datetime) -> SecretValue:
        return SecretValue(data=self.VALUE, fetched_at=fetched_at)

    def test_hit_stale_and_expired_paths(self, tmp_path, caplog):
        caplog.set_level("DEBUG", logger="scalo.secrets.cache")
        cache = DiskCache(CacheConfig(enabled=True, directory=str(tmp_path), ttl_secs=60, stale_grace_secs=600))
        cache.set(self.NAME, self._entry(datetime.now(UTC)))
        assert cache.get(self.NAME) is not None
        cache.set(self.NAME, self._entry(datetime.now(UTC) - timedelta(minutes=5)))
        assert cache.get(self.NAME) is not None
        cache.set(self.NAME, self._entry(datetime.now(UTC) - timedelta(hours=2)))
        assert cache.get(self.NAME) is None
        messages = {r.getMessage() for r in caplog.records}
        assert {"Cache set", "Cache hit", "Using stale cached secret", "Cache expired beyond grace period"} <= messages
        self._assert_no_value_logged(caplog)

    @pytest.mark.parametrize(
        "corrupt",
        [
            b"{not json",
            # Truncated mid-document with the hex payload already written.
            b'{"data_hex": "' + VALUE.hex().encode() + b'", "fetched_at": ',
            b'{"data_hex": "' + VALUE.hex().encode() + b'", "fetched_at": "not-a-time"}',
            b"\xff\xfe" + VALUE,
        ],
        # Named ids keep the fixture value out of test output.
        ids=["not-json", "truncated-holding-hex", "bad-timestamp-holding-hex", "non-utf8-holding-value"],
    )
    def test_read_failure_does_not_log_the_value(self, tmp_path, caplog, corrupt):
        caplog.set_level("DEBUG", logger="scalo.secrets.cache")
        cache = DiskCache(CacheConfig(enabled=True, directory=str(tmp_path)))
        cache.set(self.NAME, self._entry(datetime.now(UTC)))
        cache._key_to_path(self.NAME).write_bytes(corrupt)
        assert cache.get(self.NAME) is None
        assert any(r.getMessage() == "Cache read failed" for r in caplog.records)
        self._assert_no_value_logged(caplog)

    def test_decryption_failure_does_not_log_the_value(self, tmp_path, caplog):
        caplog.set_level("DEBUG", logger="scalo.secrets.cache")
        DiskCache(CacheConfig(enabled=True, directory=str(tmp_path), encryption_key=b"key-one")).set(
            self.NAME, self._entry(datetime.now(UTC))
        )
        other = DiskCache(CacheConfig(enabled=True, directory=str(tmp_path), encryption_key=b"key-two"))
        assert other.get(self.NAME) is None
        assert any(r.getMessage() == "Cache decryption failed" for r in caplog.records)
        self._assert_no_value_logged(caplog)

    def test_write_failure_does_not_log_the_value(self, tmp_path, caplog):
        caplog.set_level("DEBUG", logger="scalo.secrets.cache")
        cache_dir = tmp_path / "cache"
        cache = DiskCache(CacheConfig(enabled=True, directory=str(cache_dir)))
        cache_dir.rmdir()
        cache.set(self.NAME, self._entry(datetime.now(UTC)))
        assert any(r.getMessage() == "Cache write failed" for r in caplog.records)
        self._assert_no_value_logged(caplog)
