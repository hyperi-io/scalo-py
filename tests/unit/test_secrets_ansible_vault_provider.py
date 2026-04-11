"""Unit tests for Ansible Vault secret provider."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from hyperi_pylib.secrets.exceptions import (
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
)
from hyperi_pylib.secrets.providers.ansible_vault import (
    ANSIBLE_VAULT_AVAILABLE,
    AnsibleVaultProvider,
    _read_password_file,
    _resolve_password,
)
from hyperi_pylib.secrets.types import AnsibleVaultConfig, SecretFilter

# Skip entire module if ansible-vault not installed
pytestmark = pytest.mark.skipif(not ANSIBLE_VAULT_AVAILABLE, reason="ansible-vault not installed")

TEST_PASSWORD = "test-vault-password-42"


def _create_vault_file(tmp_path: Path, content: str | dict, filename: str = "secret.vault") -> Path:
    """Create an Ansible Vault-encrypted file for testing."""
    from ansible_vault import Vault

    vault = Vault(TEST_PASSWORD)
    if isinstance(content, dict):
        raw = yaml.dump(content, default_flow_style=False)
    else:
        raw = content
    encrypted = vault.dump_raw(raw)
    vault_file = tmp_path / filename
    if isinstance(encrypted, bytes):
        vault_file.write_bytes(encrypted)
    else:
        vault_file.write_text(encrypted)
    return vault_file


def _make_provider(password: str = TEST_PASSWORD) -> AnsibleVaultProvider:
    """Create a provider with a direct password."""
    return AnsibleVaultProvider(AnsibleVaultConfig(password=password))


class TestAnsibleVaultProviderHappyPath:
    """Happy path tests for AnsibleVaultProvider."""

    def test_provider_name(self):
        """Provider name is 'ansible_vault'."""
        provider = _make_provider()
        assert provider.name == "ansible_vault"

    def test_decrypt_single_value_file(self, tmp_path):
        """Decrypt a single-value vault file and return raw bytes."""
        vault_file = _create_vault_file(tmp_path, "my-secret-value")

        provider = _make_provider()
        result = provider.get_sync(str(vault_file))

        assert result.decode() == "my-secret-value"
        assert result.source == "ansible_vault"

    def test_decrypt_yaml_file_extract_key(self, tmp_path):
        """Decrypt YAML vault file and extract a specific key."""
        vault_file = _create_vault_file(tmp_path, {"db_password": "hunter2", "api_key": "secret123"})

        provider = _make_provider()
        result = provider.get_sync(str(vault_file), key="db_password")

        assert result.decode() == "hunter2"

    def test_decrypt_yaml_file_no_key(self, tmp_path):
        """Decrypt YAML vault file without key returns raw decrypted bytes."""
        data = {"db_password": "hunter2", "api_key": "secret123"}
        vault_file = _create_vault_file(tmp_path, data)

        provider = _make_provider()
        result = provider.get_sync(str(vault_file))

        parsed = yaml.safe_load(result.data)
        assert parsed["db_password"] == "hunter2"
        assert parsed["api_key"] == "secret123"

    def test_decrypt_yaml_nested_value(self, tmp_path):
        """Extracting a nested YAML value returns YAML-serialized bytes."""
        data = {"database": {"host": "localhost", "port": 5432}}
        vault_file = _create_vault_file(tmp_path, data)

        provider = _make_provider()
        result = provider.get_sync(str(vault_file), key="database")

        parsed = yaml.safe_load(result.data)
        assert parsed["host"] == "localhost"
        assert parsed["port"] == 5432

    def test_password_from_env_var(self, tmp_path):
        """Password resolved from ANSIBLE_VAULT_PASSWORD env var."""
        vault_file = _create_vault_file(tmp_path, "env-secret")

        with patch.dict(os.environ, {"ANSIBLE_VAULT_PASSWORD": TEST_PASSWORD}, clear=False):
            provider = AnsibleVaultProvider(AnsibleVaultConfig())
            result = provider.get_sync(str(vault_file))

        assert result.decode() == "env-secret"

    def test_password_from_fallback_env_var(self, tmp_path):
        """Password resolved from ANSIBLE_VAULT_PASS env var."""
        vault_file = _create_vault_file(tmp_path, "fallback-secret")

        env = {"ANSIBLE_VAULT_PASS": TEST_PASSWORD}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
            provider = AnsibleVaultProvider(AnsibleVaultConfig())
            result = provider.get_sync(str(vault_file))

        assert result.decode() == "fallback-secret"

    def test_password_from_env_password_file(self, tmp_path):
        """Password file path from ANSIBLE_VAULT_PASSWORD_FILE env var."""
        vault_file = _create_vault_file(tmp_path, "file-env-secret")

        pass_file = tmp_path / "vault_pass"
        pass_file.write_text(TEST_PASSWORD)

        env = {"ANSIBLE_VAULT_PASSWORD_FILE": str(pass_file)}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
            os.environ.pop("ANSIBLE_VAULT_PASS", None)
            provider = AnsibleVaultProvider(AnsibleVaultConfig())
            result = provider.get_sync(str(vault_file))

        assert result.decode() == "file-env-secret"

    def test_password_from_config_file(self, tmp_path):
        """Password from password_file config."""
        vault_file = _create_vault_file(tmp_path, "config-file-secret")

        pass_file = tmp_path / "vault_pass"
        pass_file.write_text(TEST_PASSWORD)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
            os.environ.pop("ANSIBLE_VAULT_PASS", None)
            os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)
            provider = AnsibleVaultProvider(AnsibleVaultConfig(password_file=str(pass_file)))
            result = provider.get_sync(str(vault_file))

        assert result.decode() == "config-file-secret"

    def test_password_priority_order(self, tmp_path):
        """Env var takes precedence over password file."""
        vault_file = _create_vault_file(tmp_path, "priority-secret")

        pass_file = tmp_path / "vault_pass"
        pass_file.write_text("wrong-password")

        with patch.dict(os.environ, {"ANSIBLE_VAULT_PASSWORD": TEST_PASSWORD}, clear=False):
            provider = AnsibleVaultProvider(AnsibleVaultConfig(password_file=str(pass_file)))
            result = provider.get_sync(str(vault_file))

        assert result.decode() == "priority-secret"

    def test_health_check_passes(self):
        """Health check returns True when password is configured."""
        provider = _make_provider()
        assert provider.health_check_sync() is True

    def test_version_tracking(self, tmp_path):
        """Version string is in mtime:size format."""
        vault_file = _create_vault_file(tmp_path, "version-test")

        provider = _make_provider()
        result = provider.get_sync(str(vault_file))

        assert result.version is not None
        parts = result.version.split(":")
        assert len(parts) == 2
        float(parts[0])  # mtime is a float
        int(parts[1])  # size is an int

    @pytest.mark.asyncio
    async def test_async_delegates_to_sync(self, tmp_path):
        """Async get returns same result as sync get."""
        vault_file = _create_vault_file(tmp_path, "async-test")

        provider = _make_provider()
        sync_result = provider.get_sync(str(vault_file))
        async_result = await provider.get_async(str(vault_file))

        assert sync_result.data == async_result.data
        assert sync_result.source == async_result.source

    @pytest.mark.asyncio
    async def test_health_check_async(self):
        """Async health check delegates to sync."""
        provider = _make_provider()
        assert await provider.health_check_async() is True

    def test_password_file_strips_whitespace(self, tmp_path):
        """Password file content is stripped of trailing whitespace."""
        vault_file = _create_vault_file(tmp_path, "strip-test")

        pass_file = tmp_path / "vault_pass"
        pass_file.write_text(f"{TEST_PASSWORD}\n\n")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
            os.environ.pop("ANSIBLE_VAULT_PASS", None)
            os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)
            provider = AnsibleVaultProvider(AnsibleVaultConfig(password_file=str(pass_file)))
            result = provider.get_sync(str(vault_file))

        assert result.decode() == "strip-test"


class TestAnsibleVaultProviderFailures:
    """Expected failure tests for AnsibleVaultProvider."""

    def test_no_password_source_raises(self):
        """No password configured raises ProviderError at init."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
            os.environ.pop("ANSIBLE_VAULT_PASS", None)
            os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)

            with pytest.raises(ProviderError) as exc_info:
                AnsibleVaultProvider(AnsibleVaultConfig())

            assert "no vault password configured" in str(exc_info.value)

    def test_file_not_found_raises(self, tmp_path):
        """Vault file missing raises SecretNotFoundError."""
        provider = _make_provider()

        with pytest.raises(SecretNotFoundError) as exc_info:
            provider.get_sync(str(tmp_path / "nonexistent.vault"))

        assert "nonexistent.vault" in str(exc_info.value)
        assert exc_info.value.provider == "ansible_vault"

    def test_wrong_password_raises(self, tmp_path):
        """Wrong password raises ProviderError."""
        vault_file = _create_vault_file(tmp_path, "secret-data")

        provider = _make_provider(password="wrong-password")

        with pytest.raises(ProviderError) as exc_info:
            provider.get_sync(str(vault_file))

        assert "decryption failed" in str(exc_info.value)

    def test_key_from_non_yaml_raises(self, tmp_path):
        """Key requested but content is not YAML mapping raises ProviderError."""
        vault_file = _create_vault_file(tmp_path, "just-a-plain-string")

        provider = _make_provider()

        with pytest.raises(ProviderError) as exc_info:
            provider.get_sync(str(vault_file), key="some_key")

        assert "not a YAML mapping" in str(exc_info.value)

    def test_missing_key_in_yaml_raises(self, tmp_path):
        """Key not found in YAML raises SecretNotFoundError."""
        vault_file = _create_vault_file(tmp_path, {"existing_key": "value"})

        provider = _make_provider()

        with pytest.raises(SecretNotFoundError) as exc_info:
            provider.get_sync(str(vault_file), key="nonexistent_key")

        assert "nonexistent_key" in str(exc_info.value)

    def test_password_file_missing_raises(self):
        """Password file doesn't exist raises ProviderError at init."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
            os.environ.pop("ANSIBLE_VAULT_PASS", None)
            os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)

            with pytest.raises(ProviderError) as exc_info:
                AnsibleVaultProvider(AnsibleVaultConfig(password_file="/nonexistent/path"))

            assert "password file not found" in str(exc_info.value)

    def test_password_file_empty_raises(self, tmp_path):
        """Password file is empty raises ProviderError at init."""
        pass_file = tmp_path / "empty_pass"
        pass_file.write_text("")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANSIBLE_VAULT_PASSWORD", None)
            os.environ.pop("ANSIBLE_VAULT_PASS", None)
            os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)

            with pytest.raises(ProviderError) as exc_info:
                AnsibleVaultProvider(AnsibleVaultConfig(password_file=str(pass_file)))

            assert "password file is empty" in str(exc_info.value)

    def test_corrupted_vault_file_raises(self, tmp_path):
        """Corrupted vault file content raises ProviderError."""
        vault_file = tmp_path / "corrupted.vault"
        vault_file.write_text("$ANSIBLE_VAULT;1.1;AES256\ncorrupted-garbage-data")

        provider = _make_provider()

        with pytest.raises(ProviderError) as exc_info:
            provider.get_sync(str(vault_file))

        assert "decryption failed" in str(exc_info.value)

    def test_permission_denied_raises(self, tmp_path):
        """Unreadable vault file raises ProviderError."""
        vault_file = _create_vault_file(tmp_path, "secret")
        vault_file.chmod(0o000)

        provider = _make_provider()

        try:
            with pytest.raises((ProviderError, SecretNotFoundError)):
                provider.get_sync(str(vault_file))
        finally:
            vault_file.chmod(0o644)

    @pytest.mark.asyncio
    async def test_file_not_found_async_raises(self, tmp_path):
        """Async version also raises SecretNotFoundError for missing files."""
        provider = _make_provider()

        with pytest.raises(SecretNotFoundError):
            await provider.get_async(str(tmp_path / "missing.vault"))


class TestResolvePassword:
    """Tests for _resolve_password helper."""

    def test_config_password_takes_priority(self):
        """Direct password in config is used first."""
        config = AnsibleVaultConfig(password="direct-pass")
        with patch.dict(os.environ, {"ANSIBLE_VAULT_PASSWORD": "env-pass"}, clear=False):
            assert _resolve_password(config) == "direct-pass"

    def test_env_over_file(self, tmp_path):
        """ANSIBLE_VAULT_PASSWORD env var beats password file."""
        pass_file = tmp_path / "vault_pass"
        pass_file.write_text("file-pass")

        config = AnsibleVaultConfig(password_file=str(pass_file))
        with patch.dict(os.environ, {"ANSIBLE_VAULT_PASSWORD": "env-pass"}, clear=False):
            assert _resolve_password(config) == "env-pass"


class TestReadPasswordFile:
    """Tests for _read_password_file helper."""

    def test_reads_and_strips_trailing(self, tmp_path):
        """Reads file and strips trailing whitespace."""
        f = tmp_path / "pass"
        f.write_text("my-password  \n")
        assert _read_password_file(str(f)) == "my-password"

    def test_missing_file(self):
        """Missing file raises ProviderError."""
        with pytest.raises(ProviderError, match="password file not found"):
            _read_password_file("/nonexistent/file")

    def test_empty_file(self, tmp_path):
        """Empty file raises ProviderError."""
        f = tmp_path / "empty"
        f.write_text("")
        with pytest.raises(ProviderError, match="password file is empty"):
            _read_password_file(str(f))


# =============================================================================
# Plan 2: AnsibleVault CRUD extensions
# =============================================================================


class TestAnsibleVaultMetadata:
    """Tests for AnsibleVaultProvider get_metadata."""

    def test_get_metadata_reads_stat_without_decrypting(self, tmp_path):
        """Metadata is stat-based and doesn't require decryption."""
        vault_file = _create_vault_file(tmp_path, "value")

        provider = _make_provider()
        md = provider.get_metadata_sync(str(vault_file))

        assert md.name == str(vault_file)
        assert md.created_at is not None
        assert md.updated_at is not None
        assert md.source == "ansible_vault"

    def test_get_metadata_missing_raises(self, tmp_path):
        provider = _make_provider()
        with pytest.raises(SecretNotFoundError):
            provider.get_metadata_sync(str(tmp_path / "missing.vault"))

    def test_get_metadata_wrong_password_still_works(self, tmp_path):
        """Metadata only stats the file — password isn't needed."""
        vault_file = _create_vault_file(tmp_path, "secret")
        # Use a completely different password
        provider = AnsibleVaultProvider(AnsibleVaultConfig(password="wrong-password"))
        md = provider.get_metadata_sync(str(vault_file))
        assert md.name == str(vault_file)


class TestAnsibleVaultList:
    """Tests for AnsibleVaultProvider list."""

    def test_list_returns_files_without_decrypting(self, tmp_path):
        _create_vault_file(tmp_path, "a", "a.vault")
        _create_vault_file(tmp_path, "b", "b.vault")

        provider = _make_provider()
        result = provider.list_sync(SecretFilter(prefix=str(tmp_path)))

        names = sorted(Path(p).name for p in result)
        assert names == ["a.vault", "b.vault"]

    def test_list_pattern_filters(self, tmp_path):
        _create_vault_file(tmp_path, "a", "api_key.vault")
        _create_vault_file(tmp_path, "b", "db_password.vault")

        provider = _make_provider()
        result = provider.list_sync(SecretFilter(prefix=str(tmp_path), pattern="api_*"))

        assert len(result) == 1
        assert result[0].endswith("api_key.vault")

    def test_list_no_prefix_returns_empty(self):
        provider = _make_provider()
        assert provider.list_sync(None) == []


class TestAnsibleVaultCreate:
    """Tests for AnsibleVaultProvider create."""

    def test_create_encrypts_and_writes(self, tmp_path):
        """Created file is vault-encrypted (not plaintext)."""
        path = tmp_path / "new.vault"
        provider = _make_provider()

        md = provider.create_sync(str(path), b"super-secret-value")

        assert path.exists()
        # Must NOT be plaintext
        assert b"super-secret-value" not in path.read_bytes()
        # Must be a vault file
        assert path.read_bytes().startswith(b"$ANSIBLE_VAULT")
        # Round-trip: we should be able to decrypt it back
        value = provider.get_sync(str(path))
        assert value.decode() == "super-secret-value"
        assert md.name == str(path)

    def test_create_already_exists_raises(self, tmp_path):
        path = _create_vault_file(tmp_path, "existing")
        provider = _make_provider()
        with pytest.raises(SecretAlreadyExistsError):
            provider.create_sync(str(path), b"new")

    def test_create_permission_denied(self, tmp_path):
        os.chmod(tmp_path, 0o500)
        try:
            provider = _make_provider()
            with pytest.raises(SecretPermissionError):
                provider.create_sync(str(tmp_path / "denied.vault"), b"v")
        finally:
            os.chmod(tmp_path, 0o700)


class TestAnsibleVaultUpdate:
    """Tests for AnsibleVaultProvider update."""

    def test_update_encrypts_new_value(self, tmp_path):
        path = _create_vault_file(tmp_path, "old-value")
        provider = _make_provider()

        provider.update_sync(str(path), b"new-value")

        # Decrypt to verify
        value = provider.get_sync(str(path))
        assert value.decode() == "new-value"
        # Must still be vault format
        assert path.read_bytes().startswith(b"$ANSIBLE_VAULT")

    def test_update_missing_raises(self, tmp_path):
        provider = _make_provider()
        with pytest.raises(SecretNotFoundError):
            provider.update_sync(str(tmp_path / "missing.vault"), b"v")


class TestAnsibleVaultDelete:
    """Tests for AnsibleVaultProvider delete."""

    def test_delete_removes_file(self, tmp_path):
        path = _create_vault_file(tmp_path, "v")

        provider = _make_provider()
        provider.delete_sync(str(path))

        assert not path.exists()

    def test_delete_missing_raises(self, tmp_path):
        provider = _make_provider()
        with pytest.raises(SecretNotFoundError):
            provider.delete_sync(str(tmp_path / "missing.vault"))
