"""Unit tests for file provider."""

import json
import os
from pathlib import Path

import pytest

from hyperi_pylib.secrets.exceptions import (
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
)
from hyperi_pylib.secrets.providers.file import FileProvider
from hyperi_pylib.secrets.types import SecretFilter


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


class TestFileProviderMetadata:
    """Tests for FileProvider get_metadata."""

    def test_get_metadata_returns_stat_based_info(self, tmp_path):
        """get_metadata_sync reads timestamps from stat()."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("value")

        provider = FileProvider()
        md = provider.get_metadata_sync(str(secret_file))

        assert md.name == str(secret_file)
        assert md.created_at is not None
        assert md.updated_at is not None
        assert md.source == "file"
        # File provider has no concept of tags / version_count / expires_at
        assert md.tags is None
        assert md.version_count is None
        assert md.expires_at is None

    def test_get_metadata_missing_file_raises(self, tmp_path):
        """get_metadata_sync raises SecretNotFoundError for missing files."""
        provider = FileProvider()
        with pytest.raises(SecretNotFoundError):
            provider.get_metadata_sync(str(tmp_path / "does_not_exist"))

    @pytest.mark.asyncio
    async def test_get_metadata_async_delegates(self, tmp_path):
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("v")
        provider = FileProvider()
        md = await provider.get_metadata_async(str(secret_file))
        assert md.name == str(secret_file)


class TestFileProviderList:
    """Tests for FileProvider list."""

    def test_list_directory_returns_files(self, tmp_path):
        """list_sync treats prefix as a directory and returns its files."""
        (tmp_path / "a").write_text("1")
        (tmp_path / "b").write_text("2")
        (tmp_path / "c").write_text("3")

        provider = FileProvider()
        result = provider.list_sync(SecretFilter(prefix=str(tmp_path)))

        assert sorted(Path(p).name for p in result) == ["a", "b", "c"]

    def test_list_pattern_filters_fnmatch(self, tmp_path):
        """list_sync applies fnmatch pattern as client-side filter."""
        (tmp_path / "api_key").write_text("1")
        (tmp_path / "db_password").write_text("2")
        (tmp_path / "api_token").write_text("3")

        provider = FileProvider()
        result = provider.list_sync(SecretFilter(prefix=str(tmp_path), pattern="api_*"))

        names = sorted(Path(p).name for p in result)
        assert names == ["api_key", "api_token"]

    def test_list_no_filter_returns_empty(self, tmp_path):
        """list_sync without a prefix returns empty (no 'list all' concept)."""
        (tmp_path / "a").write_text("1")
        provider = FileProvider()
        # No filter means no prefix → provider cannot enumerate without a root
        result = provider.list_sync(None)
        assert result == []

    def test_list_missing_directory_returns_empty(self, tmp_path):
        """list_sync returns empty for a non-existent prefix directory."""
        provider = FileProvider()
        result = provider.list_sync(SecretFilter(prefix=str(tmp_path / "missing")))
        assert result == []

    def test_list_tags_ignored(self, tmp_path):
        """list_sync ignores tags filter (file provider has no tags)."""
        (tmp_path / "a").write_text("1")
        provider = FileProvider()
        result = provider.list_sync(SecretFilter(prefix=str(tmp_path), tags={"env": "prod"}))
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_async_delegates(self, tmp_path):
        (tmp_path / "a").write_text("1")
        provider = FileProvider()
        result = await provider.list_async(SecretFilter(prefix=str(tmp_path)))
        assert len(result) == 1


class TestFileProviderCreate:
    """Tests for FileProvider create."""

    def test_create_new_file(self, tmp_path):
        """create_sync writes a new file and returns metadata."""
        path = str(tmp_path / "new_secret")
        provider = FileProvider()

        md = provider.create_sync(path, b"value")

        assert Path(path).read_bytes() == b"value"
        assert md.name == path
        assert md.source == "file"

    def test_create_already_exists_raises(self, tmp_path):
        """create_sync raises SecretAlreadyExistsError if file exists."""
        path = tmp_path / "existing"
        path.write_text("old")

        provider = FileProvider()
        with pytest.raises(SecretAlreadyExistsError):
            provider.create_sync(str(path), b"new")

        # Original content should not be overwritten
        assert path.read_text() == "old"

    def test_create_tags_ignored(self, tmp_path):
        """create_sync ignores the tags argument (file provider has no tags)."""
        path = str(tmp_path / "tagged")
        provider = FileProvider()
        md = provider.create_sync(path, b"v", tags={"env": "prod"})
        assert md.tags is None

    def test_create_permission_denied(self, tmp_path):
        """create_sync raises SecretPermissionError on OSError PermissionError."""
        # Make tmp_path read-only so we cannot create files inside
        os.chmod(tmp_path, 0o500)
        try:
            provider = FileProvider()
            with pytest.raises(SecretPermissionError) as exc_info:
                provider.create_sync(str(tmp_path / "denied"), b"v")
            assert exc_info.value.operation == "create"
        finally:
            os.chmod(tmp_path, 0o700)

    @pytest.mark.asyncio
    async def test_create_async_delegates(self, tmp_path):
        path = str(tmp_path / "async_secret")
        provider = FileProvider()
        md = await provider.create_async(path, b"v")
        assert md.name == path


class TestFileProviderUpdate:
    """Tests for FileProvider update."""

    def test_update_existing_file(self, tmp_path):
        path = tmp_path / "secret"
        path.write_text("old")

        provider = FileProvider()
        md = provider.update_sync(str(path), b"new")

        assert path.read_bytes() == b"new"
        assert md.name == str(path)

    def test_update_missing_raises(self, tmp_path):
        provider = FileProvider()
        with pytest.raises(SecretNotFoundError):
            provider.update_sync(str(tmp_path / "missing"), b"v")

    def test_update_permission_denied(self, tmp_path):
        path = tmp_path / "readonly"
        path.write_text("v")
        os.chmod(path, 0o400)
        try:
            provider = FileProvider()
            with pytest.raises(SecretPermissionError) as exc_info:
                provider.update_sync(str(path), b"new")
            assert exc_info.value.operation == "update"
        finally:
            os.chmod(path, 0o600)

    @pytest.mark.asyncio
    async def test_update_async_delegates(self, tmp_path):
        path = tmp_path / "secret"
        path.write_text("old")
        provider = FileProvider()
        md = await provider.update_async(str(path), b"new")
        assert md.name == str(path)


class TestFileProviderDelete:
    """Tests for FileProvider delete."""

    def test_delete_existing_file(self, tmp_path):
        path = tmp_path / "secret"
        path.write_text("v")

        provider = FileProvider()
        provider.delete_sync(str(path))

        assert not path.exists()

    def test_delete_missing_raises(self, tmp_path):
        provider = FileProvider()
        with pytest.raises(SecretNotFoundError):
            provider.delete_sync(str(tmp_path / "missing"))

    def test_delete_permission_denied(self, tmp_path):
        path = tmp_path / "secret"
        path.write_text("v")
        # Remove write permission on the parent directory (needed to unlink)
        os.chmod(tmp_path, 0o500)
        try:
            provider = FileProvider()
            with pytest.raises(SecretPermissionError) as exc_info:
                provider.delete_sync(str(path))
            assert exc_info.value.operation == "delete"
        finally:
            os.chmod(tmp_path, 0o700)

    @pytest.mark.asyncio
    async def test_delete_async_delegates(self, tmp_path):
        path = tmp_path / "secret"
        path.write_text("v")
        provider = FileProvider()
        await provider.delete_async(str(path))
        assert not path.exists()
