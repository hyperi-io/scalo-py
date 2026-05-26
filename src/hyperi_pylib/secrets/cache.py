"""Disk-based cache for secrets with optional encryption."""

import hashlib
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from .types import CacheConfig, SecretValue

logger = logging.getLogger(__name__)

# Optional encryption support
try:
    from cryptography.fernet import Fernet

    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False
    Fernet = None  # type: ignore[assignment,misc]


class DiskCache:
    """Disk-based cache for secrets with optional encryption.

    Features:
    - TTL-based expiration
    - Stale grace period for fallback
    - Optional Fernet encryption at rest
    - Atomic writes to prevent corruption
    """

    def __init__(self, config: CacheConfig) -> None:
        """Initialize disk cache.

        Args:
            config: Cache configuration.
        """
        self._config = config
        self._directory = self._resolve_directory(config.directory)
        self._fernet: Fernet | None = None

        if config.encryption_key and FERNET_AVAILABLE:
            # Derive 32-byte key for Fernet using SHA256
            key_bytes = config.encryption_key
            if isinstance(key_bytes, str):
                key_bytes = key_bytes.encode("utf-8")
            derived_key = hashlib.sha256(key_bytes).digest()
            import base64

            self._fernet = Fernet(base64.urlsafe_b64encode(derived_key))
        elif config.encryption_key and not FERNET_AVAILABLE:
            logger.warning(
                "Cache encryption requested but cryptography not installed. Install with: pip install cryptography"
            )

        # Ensure directory exists
        if config.enabled:
            self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def config(self) -> CacheConfig:
        """Get cache configuration."""
        return self._config

    def _resolve_directory(self, directory: str | None) -> Path:
        """Resolve cache directory.

        Priority (AGENT-RULES Rule 4 compliant -- never /tmp for state):

        1. Explicit ``directory`` parameter
        2. ``HYPERI_SECRETS_CACHE_DIR`` env var
        3. ``$XDG_CACHE_HOME/hs-secrets``
        4. Native Windows: ``%LOCALAPPDATA%/hyperi-ai/secrets-cache``
        5. Otherwise: ``~/.cache/hyperi-ai/secrets-cache``
        """
        if directory:
            return Path(directory)

        env_dir = os.environ.get("HYPERI_SECRETS_CACHE_DIR")
        if env_dir:
            return Path(env_dir)

        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            return Path(xdg_cache) / "hs-secrets"

        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            return base / "hyperi-ai" / "secrets-cache"

        return Path.home() / ".cache" / "hyperi-ai" / "secrets-cache"

    def _key_to_path(self, secret_name: str) -> Path:
        """Convert secret name to cache file path.

        Uses hash to avoid filesystem issues with special characters.
        """
        name_hash = hashlib.sha256(secret_name.encode()).hexdigest()[:16]
        # Sanitize name for filename (keep first 50 chars)
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in secret_name)[:50]
        return self._directory / f"{safe_name}_{name_hash}.cache"

    def get(self, secret_name: str) -> SecretValue | None:
        """Get cached secret if valid.

        Returns:
            SecretValue if cache hit and not expired, None otherwise.
        """
        if not self._config.enabled:
            return None

        path = self._key_to_path(secret_name)
        if not path.exists():
            return None

        try:
            data = path.read_bytes()

            if self._fernet:
                try:
                    data = self._fernet.decrypt(data)
                except Exception as e:
                    logger.warning("Cache decryption failed", extra={"secret_name": secret_name, "error": str(e)})
                    # Remove corrupted cache
                    path.unlink(missing_ok=True)
                    return None

            cached = json.loads(data.decode("utf-8"))

            value = SecretValue(
                data=bytes.fromhex(cached["data_hex"]),
                fetched_at=datetime.fromisoformat(cached["fetched_at"]),
                version=cached.get("version"),
                source=cached.get("source", "cache"),
            )

            # Check TTL
            if value.is_expired(self._config.ttl_secs):
                if value.is_within_grace(self._config.ttl_secs, self._config.stale_grace_secs):
                    logger.debug("Using stale cached secret", extra={"secret_name": secret_name})
                    return value
                else:
                    # Expired beyond grace period
                    logger.debug("Cache expired beyond grace period", extra={"secret_name": secret_name})
                    path.unlink(missing_ok=True)
                    return None

            logger.debug("Cache hit", extra={"secret_name": secret_name})
            return value

        except Exception as e:
            logger.warning("Cache read failed", extra={"secret_name": secret_name, "error": str(e)})
            return None

    def set(self, secret_name: str, value: SecretValue) -> None:
        """Cache a secret value.

        Uses atomic write (write to temp file, then rename) to prevent corruption.
        """
        if not self._config.enabled:
            return

        path = self._key_to_path(secret_name)

        try:
            cached = {
                "data_hex": value.data.hex(),
                "fetched_at": value.fetched_at.isoformat(),
                "version": value.version,
                "source": value.source,
            }

            data = json.dumps(cached).encode("utf-8")

            if self._fernet:
                data = self._fernet.encrypt(data)

            # Atomic write
            temp_path = path.with_suffix(".tmp")
            temp_path.write_bytes(data)
            temp_path.rename(path)

            logger.debug("Cache set", extra={"secret_name": secret_name})

        except Exception as e:
            logger.warning("Cache write failed", extra={"secret_name": secret_name, "error": str(e)})

    def delete(self, secret_name: str) -> bool:
        """Delete cached secret.

        Returns:
            True if deleted, False if not found or error.
        """
        path = self._key_to_path(secret_name)
        try:
            path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def clear(self) -> int:
        """Clear all cached secrets.

        Returns:
            Number of deleted cache entries.
        """
        count = 0
        try:
            for cache_file in self._directory.glob("*.cache"):
                try:
                    cache_file.unlink()
                    count += 1
                except Exception:
                    pass
        except Exception:
            pass
        return count


__all__ = ["DiskCache"]
