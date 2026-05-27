"""File-based secret provider (always available)."""

import fnmatch
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from ..exceptions import ProviderError, SecretAlreadyExistsError, SecretNotFoundError, SecretPermissionError
from ..types import SecretFilter, SecretMetadata, SecretValue
from .base import SecretProvider

logger = logging.getLogger(__name__)


class FileProvider(SecretProvider):
    """File-based secret provider.

    Reads secrets from local filesystem. Always available with no extra dependencies.

    Use cases:
    - Kubernetes secrets mounted as files
    - Docker secrets in /run/secrets
    - Local development with file-based credentials
    - External Secrets Operator (ESO) synced files
    """

    @property
    def name(self) -> str:
        """Provider name."""
        return "file"

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

    # --- Read ---

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Async get via run_blocking (file I/O is blocking)."""
        from hyperi_pylib.concurrency import run_blocking

        return await run_blocking(self.get_sync, path, key)

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Read secret from file.

        Args:
            path: Path to the secret file.
            key: Optional key to extract from JSON file.

        Returns:
            SecretValue with file contents.

        Raises:
            SecretNotFoundError: File does not exist.
            ProviderError: Read or parse failed.
        """
        file_path = Path(path)

        if not file_path.exists():
            raise SecretNotFoundError(path, self.name)

        try:
            data = file_path.read_bytes()

            # If key specified, parse as JSON and extract
            if key is not None:
                try:
                    parsed = json.loads(data.decode("utf-8"))
                except json.JSONDecodeError as e:
                    raise ProviderError(self.name, f"invalid JSON in {path}: {e}")

                if key not in parsed:
                    raise SecretNotFoundError(f"{path}[{key}]", self.name)

                value = parsed[key]
                # Convert to bytes
                if isinstance(value, bytes):
                    data = value
                elif isinstance(value, str):
                    data = value.encode("utf-8")
                else:
                    data = json.dumps(value).encode("utf-8")

            return SecretValue(
                data=data,
                fetched_at=datetime.now(UTC),
                version=self._compute_version(file_path),
                source=self.name,
            )

        except (SecretNotFoundError, ProviderError):
            raise
        except OSError as e:
            raise ProviderError(self.name, f"failed to read {path}: {e}")

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """Async list via run_blocking (glob is blocking)."""
        from hyperi_pylib.concurrency import run_blocking

        return await run_blocking(self.list_sync, filter)

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        """List secret files matching filter.

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
        """Get file metadata without reading contents."""
        file_path = Path(path)

        if not file_path.exists():
            raise SecretNotFoundError(path, self.name)

        try:
            return self._build_metadata(file_path)
        except OSError as e:
            raise ProviderError(self.name, f"failed to stat {path}: {e}")

    # --- Create ---

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create file (async delegates to sync)."""
        return self.create_sync(path, value, tags)

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create a new secret file. Fails if file already exists."""
        file_path = Path(path)

        if file_path.exists():
            raise SecretAlreadyExistsError(path, self.name)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(value)
        except PermissionError:
            raise SecretPermissionError(self.name, "create", path, f"check filesystem permissions on '{path}'")
        except OSError as e:
            raise ProviderError(self.name, f"failed to create {path}: {e}")

        return self._build_metadata(file_path)

    # --- Update ---

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Update file (async delegates to sync)."""
        return self.update_sync(path, value)

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        """Update an existing secret file. Fails if file doesn't exist."""
        file_path = Path(path)

        if not file_path.exists():
            raise SecretNotFoundError(path, self.name)

        try:
            file_path.write_bytes(value)
        except PermissionError:
            raise SecretPermissionError(self.name, "update", path, f"check filesystem permissions on '{path}'")
        except OSError as e:
            raise ProviderError(self.name, f"failed to update {path}: {e}")

        return self._build_metadata(file_path)

    # --- Delete ---

    async def delete_async(self, path: str) -> None:
        """Delete file (async delegates to sync)."""
        self.delete_sync(path)

    def delete_sync(self, path: str) -> None:
        """Delete a secret file."""
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
        """File provider is always healthy."""
        return True

    def health_check_sync(self) -> bool:
        """File provider is always healthy."""
        return True


__all__ = ["FileProvider"]
