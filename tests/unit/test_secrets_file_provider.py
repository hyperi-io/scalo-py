"""Unit tests for file provider."""

import json
from pathlib import Path

import pytest

from hs_pylib.secrets.exceptions import ProviderError, SecretNotFoundError
from hs_pylib.secrets.providers.file import FileProvider


class TestFileProvider:
    """Tests for FileProvider."""

    def test_provider_name(self):
        """Test provider name."""
        provider = FileProvider()
        assert provider.name == "file"

    def test_read_text_file(self, tmp_path):
        """Test reading a plain text file."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("my-secret-value")

        provider = FileProvider()
        result = provider.get_sync(str(secret_file))

        assert result.decode() == "my-secret-value"
        assert result.source == "file"
        assert result.version is not None  # mtime:size

    def test_read_binary_file(self, tmp_path):
        """Test reading a binary file."""
        secret_file = tmp_path / "secret.bin"
        binary_data = bytes([0x00, 0x01, 0x02, 0xFF])
        secret_file.write_bytes(binary_data)

        provider = FileProvider()
        result = provider.get_sync(str(secret_file))

        assert result.data == binary_data

    def test_read_json_with_key(self, tmp_path):
        """Test reading a specific key from JSON file."""
        secret_file = tmp_path / "secrets.json"
        data = {"api_key": "secret123", "password": "hunter2"}
        secret_file.write_text(json.dumps(data))

        provider = FileProvider()
        result = provider.get_sync(str(secret_file), key="api_key")

        assert result.decode() == "secret123"

    def test_read_json_nested_value(self, tmp_path):
        """Test reading a nested JSON value (returns JSON string)."""
        secret_file = tmp_path / "secrets.json"
        data = {"database": {"host": "localhost", "port": 5432}}
        secret_file.write_text(json.dumps(data))

        provider = FileProvider()
        result = provider.get_sync(str(secret_file), key="database")

        # Nested objects are returned as JSON
        parsed = json.loads(result.decode())
        assert parsed["host"] == "localhost"
        assert parsed["port"] == 5432

    def test_file_not_found(self, tmp_path):
        """Test error when file doesn't exist."""
        provider = FileProvider()

        with pytest.raises(SecretNotFoundError) as exc_info:
            provider.get_sync(str(tmp_path / "nonexistent.txt"))

        assert "nonexistent.txt" in str(exc_info.value)
        assert exc_info.value.provider == "file"

    def test_json_key_not_found(self, tmp_path):
        """Test error when JSON key doesn't exist."""
        secret_file = tmp_path / "secrets.json"
        secret_file.write_text('{"existing": "value"}')

        provider = FileProvider()

        with pytest.raises(SecretNotFoundError) as exc_info:
            provider.get_sync(str(secret_file), key="nonexistent")

        assert "nonexistent" in str(exc_info.value)

    def test_invalid_json(self, tmp_path):
        """Test error when file is not valid JSON."""
        secret_file = tmp_path / "invalid.json"
        secret_file.write_text("not valid json {")

        provider = FileProvider()

        with pytest.raises(ProviderError) as exc_info:
            provider.get_sync(str(secret_file), key="anything")

        assert "invalid JSON" in str(exc_info.value)

    def test_version_from_mtime(self, tmp_path):
        """Test that version is computed from file metadata."""
        import time

        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("value1")

        provider = FileProvider()
        result1 = provider.get_sync(str(secret_file))

        # Ensure mtime changes (filesystem may have 1-second resolution)
        time.sleep(0.1)

        # Modify file with different size to guarantee version change
        secret_file.write_text("value2-longer-content")
        result2 = provider.get_sync(str(secret_file))

        # Versions should be different after modification
        assert result1.version != result2.version

    def test_health_check_sync(self):
        """Test health check always returns True."""
        provider = FileProvider()
        assert provider.health_check_sync() is True

    @pytest.mark.asyncio
    async def test_get_async(self, tmp_path):
        """Test async get delegates to sync."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("async-value")

        provider = FileProvider()
        result = await provider.get_async(str(secret_file))

        assert result.decode() == "async-value"

    @pytest.mark.asyncio
    async def test_health_check_async(self):
        """Test async health check."""
        provider = FileProvider()
        assert await provider.health_check_async() is True

    def test_kubernetes_secrets_style(self, tmp_path):
        """Test reading Kubernetes-style mounted secrets."""
        # Kubernetes mounts secrets as individual files in a directory
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "username").write_text("admin")
        (secrets_dir / "password").write_text("s3cr3t")

        provider = FileProvider()

        username = provider.get_sync(str(secrets_dir / "username"))
        password = provider.get_sync(str(secrets_dir / "password"))

        assert username.decode() == "admin"
        assert password.decode() == "s3cr3t"

    def test_docker_secrets_style(self, tmp_path):
        """Test reading Docker-style secrets from /run/secrets."""
        # Docker mounts secrets in /run/secrets/
        run_secrets = tmp_path / "run" / "secrets"
        run_secrets.mkdir(parents=True)
        (run_secrets / "db_password").write_text("docker-secret")

        provider = FileProvider()
        result = provider.get_sync(str(run_secrets / "db_password"))

        assert result.decode() == "docker-secret"

    def test_whitespace_preserved(self, tmp_path):
        """Test that whitespace in secrets is preserved."""
        secret_file = tmp_path / "secret.txt"
        # Secrets often have trailing newlines from echo
        secret_file.write_text("value-with-newline\n")

        provider = FileProvider()
        result = provider.get_sync(str(secret_file))

        assert result.decode() == "value-with-newline\n"

    def test_empty_file(self, tmp_path):
        """Test reading an empty file."""
        secret_file = tmp_path / "empty.txt"
        secret_file.write_text("")

        provider = FileProvider()
        result = provider.get_sync(str(secret_file))

        assert result.data == b""
        assert result.decode() == ""
