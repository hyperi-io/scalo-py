"""File-based secret provider (always available)."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from ..exceptions import ProviderError, SecretNotFoundError
from ..types import SecretValue
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

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Async get (delegates to sync since file I/O is fast)."""
        return self.get_sync(path, key)

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

    async def health_check_async(self) -> bool:
        """File provider is always healthy."""
        return True

    def health_check_sync(self) -> bool:
        """File provider is always healthy."""
        return True


__all__ = ["FileProvider"]
