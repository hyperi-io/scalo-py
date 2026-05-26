"""Ansible Vault secret provider.

Designed primarily for SME networks that need encrypted-at-rest secrets without
the operational overhead of a dedicated secrets server (OpenBao, AWS Secrets
Manager, etc.). Also suitable for any environment where Ansible Vault is already
the team's standard for secret management -- dev/test environments, CI pipelines,
or hybrid setups where some secrets live in vault files alongside
infrastructure-as-code.

When to use this provider:
- Small-to-medium deployments where running a secrets server is overkill
- Teams already using Ansible for configuration management
- Environments transitioning from plaintext config files to encrypted secrets
- Dev/test environments that need secrets but not full secrets infrastructure
- Air-gapped or restricted networks where SaaS secrets managers aren't available

When NOT to use this provider:
- High-availability requirements (use OpenBao or a cloud secrets manager)
- Dynamic secret generation / rotation (use OpenBao)
- Fine-grained access control per secret (use OpenBao or cloud provider)

Dependencies:
    pip install hyperi-pylib[secrets-ansible-vault]
"""

from __future__ import annotations

import fnmatch
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ..exceptions import (
    ProviderError,
    ProviderNotAvailableError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
)
from ..types import AnsibleVaultConfig, SecretFilter, SecretMetadata, SecretValue
from .base import SecretProvider

logger = logging.getLogger(__name__)

try:
    from ansible_vault import Vault

    ANSIBLE_VAULT_AVAILABLE = True
except ImportError:
    ANSIBLE_VAULT_AVAILABLE = False


def _resolve_password(config: AnsibleVaultConfig) -> str:
    """Resolve vault password from environment or config.

    Priority order:
    1. ANSIBLE_VAULT_PASSWORD env var
    2. ANSIBLE_VAULT_PASS env var (common shorthand)
    3. ANSIBLE_VAULT_PASSWORD_FILE env var -> read file
    4. config.password_file -> read file

    Args:
        config: Provider configuration.

    Returns:
        Resolved password string.

    Raises:
        ProviderError: No password source found, or password file unreadable.
    """
    # Direct password from config (already resolved by manager)
    if config.password:
        return config.password

    # Env var: ANSIBLE_VAULT_PASSWORD
    password = os.environ.get("ANSIBLE_VAULT_PASSWORD")
    if password:
        return password

    # Env var: ANSIBLE_VAULT_PASS (common shorthand)
    password = os.environ.get("ANSIBLE_VAULT_PASS")
    if password:
        return password

    # Env var: ANSIBLE_VAULT_PASSWORD_FILE -> read file
    password_file_env = os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE")
    if password_file_env:
        return _read_password_file(password_file_env)

    # Config: password_file -> read file
    if config.password_file:
        return _read_password_file(config.password_file)

    raise ProviderError(
        "ansible_vault", "no vault password configured -- set ANSIBLE_VAULT_PASSWORD or provide password_file"
    )


def _read_password_file(path: str) -> str:
    """Read vault password from a file.

    Args:
        path: Path to the password file.

    Returns:
        Password string (stripped of trailing whitespace).

    Raises:
        ProviderError: File missing, empty, or unreadable.
    """
    file_path = Path(path)

    if not file_path.exists():
        raise ProviderError("ansible_vault", f"password file not found: {path}")

    try:
        password = file_path.read_text().strip()
    except OSError as e:
        raise ProviderError("ansible_vault", f"failed to read password file {path}: {e}")

    if not password:
        raise ProviderError("ansible_vault", f"password file is empty: {path}")

    return password


class AnsibleVaultProvider(SecretProvider):
    """Ansible Vault secret provider.

    Reads secrets from Ansible Vault-encrypted files on the local filesystem.
    Supports both single-value encrypted files and encrypted YAML files with
    key extraction.
    """

    def __init__(self, config: AnsibleVaultConfig) -> None:
        """Initialize Ansible Vault provider.

        Args:
            config: Provider configuration.

        Raises:
            ProviderNotAvailableError: ansible-vault package not installed.
            ProviderError: No vault password configured.
        """
        if not ANSIBLE_VAULT_AVAILABLE:
            raise ProviderNotAvailableError(
                "ansible_vault",
                "ansible-vault",
                "pip install hyperi-pylib[secrets-ansible-vault]",
            )
        self._config = config
        self._password = _resolve_password(config)

    @property
    def name(self) -> str:
        """Provider name."""
        return "ansible_vault"

    def _compute_version(self, path: Path) -> str:
        """Compute version from file mtime and size."""
        stat = path.stat()
        return f"{stat.st_mtime}:{stat.st_size}"

    def _build_metadata(self, path: Path) -> SecretMetadata:
        """Build SecretMetadata from file stat."""
        stat = path.stat()
        return SecretMetadata(
            name=str(path),
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=UTC),
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            version=f"{stat.st_mtime}:{stat.st_size}",
            source=self.name,
        )

    def _decrypt(self, content: str) -> bytes:
        """Decrypt vault-encrypted content.

        Args:
            content: Raw vault-encrypted file content.

        Returns:
            Decrypted bytes.

        Raises:
            ProviderError: Decryption failed (wrong password or corrupted).
        """
        try:
            vault = Vault(self._password)
            decrypted = vault.load_raw(content)
            if isinstance(decrypted, str):
                return decrypted.encode("utf-8")
            return bytes(decrypted)
        except Exception as e:
            raise ProviderError("ansible_vault", f"decryption failed: {e}")

    def _encrypt(self, data: bytes) -> str:
        """Encrypt data using Ansible Vault.

        Args:
            data: Raw bytes to encrypt.

        Returns:
            Vault-encrypted string.
        """
        vault = Vault(self._password)
        encrypted = vault.dump_raw(data.decode("utf-8") if isinstance(data, bytes) else data)
        if isinstance(encrypted, bytes):
            return encrypted.decode("utf-8")
        return encrypted

    def _extract(self, decrypted: bytes, key: str | None) -> bytes:
        """Extract value from decrypted content.

        If key is provided, parses decrypted content as YAML and extracts
        the specified key. If no key, returns raw decrypted bytes.

        Args:
            decrypted: Decrypted bytes.
            key: Optional key to extract from YAML content.

        Returns:
            Extracted bytes.

        Raises:
            ProviderError: Key requested but content is not a YAML dict.
            SecretNotFoundError: Key not found in YAML dict.
        """
        if key is None:
            return decrypted

        # Key requested -- must be a YAML dict
        try:
            parsed = yaml.safe_load(decrypted.decode("utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            raise ProviderError("ansible_vault", f"key '{key}' requested but content is not valid YAML")

        if not isinstance(parsed, dict):
            raise ProviderError("ansible_vault", f"key '{key}' requested but content is not a YAML mapping")

        if key not in parsed:
            raise SecretNotFoundError(key, "ansible_vault")

        value = parsed[key]
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        # For nested structures, serialize back to YAML
        return yaml.dump(value, default_flow_style=False).encode("utf-8")

    # --- Read ---

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Async get -- offloads ansible-vault decrypt to a worker thread.

        Vault decrypt is CPU-bound (PBKDF2 + AES-256-CTR); run_blocking
        keeps the event loop responsive on slow keys / large payloads.
        """
        from hyperi_pylib.concurrency import run_blocking

        return await run_blocking(self.get_sync, path, key)

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Read and decrypt secret from an Ansible Vault-encrypted file.

        Args:
            path: Path to the vault-encrypted file.
            key: Optional key to extract from decrypted YAML content.

        Returns:
            SecretValue with decrypted data and metadata.

        Raises:
            SecretNotFoundError: File does not exist, or key not in YAML.
            ProviderError: Decryption or read failed.
        """
        file_path = Path(path)

        if not file_path.exists():
            raise SecretNotFoundError(path, self.name)

        try:
            content = file_path.read_text()
        except OSError as e:
            raise ProviderError(self.name, f"failed to read {path}: {e}")

        decrypted = self._decrypt(content)
        data = self._extract(decrypted, key)

        return SecretValue(
            data=data,
            fetched_at=datetime.now(UTC),
            version=self._compute_version(file_path),
            source=self.name,
        )

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """List vault files -- offloads sync filesystem glob to a worker."""
        from hyperi_pylib.concurrency import run_blocking

        return await run_blocking(self.list_sync, filter)

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        """List vault-encrypted files matching filter.

        prefix is treated as a directory path. Files in that directory are listed.
        pattern applies fnmatch glob filtering on filenames.
        tags are ignored (filesystem has no tag concept).
        """
        if filter and filter.prefix:
            base = Path(filter.prefix)
        else:
            return []  # No prefix = no directory to list

        if not base.is_dir():
            return []

        results = [str(p) for p in base.iterdir() if p.is_file()]

        if filter and filter.pattern:
            results = [r for r in results if fnmatch.fnmatch(Path(r).name, filter.pattern)]

        return sorted(results)

    # --- Metadata ---

    async def get_metadata_async(self, path: str) -> SecretMetadata:
        """Get file metadata (async delegates to sync)."""
        return self.get_metadata_sync(path)

    def get_metadata_sync(self, path: str) -> SecretMetadata:
        """Get file metadata without decrypting contents."""
        file_path = Path(path)

        if not file_path.exists():
            raise SecretNotFoundError(path, self.name)

        try:
            return self._build_metadata(file_path)
        except OSError as e:
            raise ProviderError(self.name, f"failed to stat {path}: {e}")

    # --- Create ---

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create vault file (async delegates to sync)."""
        return self.create_sync(path, value, tags)

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create a new vault-encrypted secret file. Fails if file already exists."""
        file_path = Path(path)

        if file_path.exists():
            raise SecretAlreadyExistsError(path, self.name)

        try:
            encrypted = self._encrypt(value)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(encrypted)
        except PermissionError:
            raise SecretPermissionError(self.name, "create", path, f"check filesystem permissions on '{path}'")
        except OSError as e:
            raise ProviderError(self.name, f"failed to create {path}: {e}")

        return self._build_metadata(file_path)

    # --- Update ---

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Update vault file (async delegates to sync)."""
        return self.update_sync(path, value)

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        """Update an existing vault-encrypted secret file. Fails if file doesn't exist."""
        file_path = Path(path)

        if not file_path.exists():
            raise SecretNotFoundError(path, self.name)

        try:
            encrypted = self._encrypt(value)
            file_path.write_text(encrypted)
        except PermissionError:
            raise SecretPermissionError(self.name, "update", path, f"check filesystem permissions on '{path}'")
        except OSError as e:
            raise ProviderError(self.name, f"failed to update {path}: {e}")

        return self._build_metadata(file_path)

    # --- Delete ---

    async def delete_async(self, path: str) -> None:
        """Delete vault file (async delegates to sync)."""
        self.delete_sync(path)

    def delete_sync(self, path: str) -> None:
        """Delete a vault-encrypted secret file."""
        file_path = Path(path)

        if not file_path.exists():
            raise SecretNotFoundError(path, self.name)

        try:
            file_path.unlink()
        except PermissionError:
            raise SecretPermissionError(self.name, "delete", path, f"check filesystem permissions on '{path}'")
        except OSError as e:
            raise ProviderError(self.name, f"failed to delete {path}: {e}")

    # --- Health ---

    async def health_check_async(self) -> bool:
        """Check if provider is healthy."""
        return self.health_check_sync()

    def health_check_sync(self) -> bool:
        """Check if provider is healthy.

        Verifies password is available and ansible-vault is importable.
        """
        return ANSIBLE_VAULT_AVAILABLE and self._password is not None


__all__ = ["ANSIBLE_VAULT_AVAILABLE", "AnsibleVaultProvider"]
