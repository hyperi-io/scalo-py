"""Disk-based cache for secrets with optional encryption."""

import base64
import hashlib
import json
import logging
import os
import sys
import tempfile
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

# File mode for cache files: owner-read/write only (0o600).
_CACHE_FILE_MODE = 0o600
# Directory mode: owner rwx only (0o700).
_CACHE_DIR_MODE = 0o700


class DiskCache:
    """Disk-based cache for secrets with optional encryption.

    Features:
    - TTL-based expiration with stale grace period
    - Optional Fernet (AES-128-CBC + HMAC) encryption at rest
    - Atomic writes via unique tempfile + fsync + os.replace
    - Owner-only file permissions (0o600) on cache files

    **Crypto note**: ``CacheConfig.encryption_key`` MUST be high-entropy
    key material (>=32 bytes recommended) -- e.g. the output of
    ``secrets.token_bytes(32)`` stored in an env var, or a value pulled
    from a KMS. It is NOT a user password: the key derivation is a
    single SHA-256 pass (fast, no work factor). If the input could be
    a password (low entropy, human-typed), use PBKDF2/argon2 to
    pre-derive a 32-byte key BEFORE passing it here.
    """

    def __init__(self, config: CacheConfig) -> None:
        self._config = config
        self._directory = self._resolve_directory(config.directory)
        self._fernet: Fernet | None = None

        if config.encryption_key and FERNET_AVAILABLE:
            key_bytes = config.encryption_key
            if isinstance(key_bytes, str):
                key_bytes = key_bytes.encode("utf-8")
            derived_key = hashlib.sha256(key_bytes).digest()
            self._fernet = Fernet(base64.urlsafe_b64encode(derived_key))
        elif config.encryption_key and not FERNET_AVAILABLE:
            logger.warning(
                "Cache encryption requested but cryptography not installed. Install with: pip install cryptography"
            )

        if config.enabled:
            self._directory.mkdir(parents=True, exist_ok=True)
            # Tighten dir perms even if mkdir's mode arg was ignored
            # under umask. No-op on Windows (chmod sets read-only only).
            try:
                self._directory.chmod(_CACHE_DIR_MODE)
            except (OSError, NotImplementedError):
                pass

    @property
    def config(self) -> CacheConfig:
        """Get cache configuration."""
        return self._config

    def _resolve_directory(self, directory: str | None) -> Path:
        """Cache dir priority (never /tmp): explicit arg, HYPERI_SECRETS_CACHE_DIR,
        $XDG_CACHE_HOME/hs-secrets, %LOCALAPPDATA%/hyperi-ai/secrets-cache (Win),
        ~/.cache/hyperi-ai/secrets-cache.
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

        Uses a UNIQUE tempfile (tempfile.NamedTemporaryFile in the same
        directory as the target) + fsync + os.replace. Two writers
        racing on the same secret name no longer share a ``.tmp`` path,
        and a crash mid-write can't leave the final path pointing at
        truncated data. File mode is set to 0o600 before rename.
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

            # Atomic write: unique tempfile in same dir, fsync, replace.
            # NamedTemporaryFile gives us a fresh inode per writer so
            # concurrent set() calls for the same secret can't trample
            # each other's bytes.
            fd, tmp_str = tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=str(self._directory),
            )
            tmp_path = Path(tmp_str)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                try:
                    os.chmod(tmp_path, _CACHE_FILE_MODE)
                except (OSError, NotImplementedError):
                    pass
                os.replace(tmp_path, path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

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

        Raises ``OSError`` if the cache directory cannot be listed
        (caller gets a real signal). Per-file unlink failures are still
        swallowed (best-effort).

        Returns:
            Number of deleted cache entries.
        """
        if not self._directory.exists():
            return 0
        count = 0
        for cache_file in self._directory.glob("*.cache"):
            try:
                cache_file.unlink()
                count += 1
            except OSError as e:
                logger.warning("Cache file unlink failed", extra={"path": str(cache_file), "error": str(e)})
        return count


__all__ = ["DiskCache"]
