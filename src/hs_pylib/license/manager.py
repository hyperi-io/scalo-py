# Project:   hs-pylib
# File:      src/hs_pylib/license/manager.py
# Purpose:   License manager and loading logic
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2026 HyperSec

"""License manager with file loading, URL fetching, and singleton pattern.

Direct port from hs-rustlib/src/license/mod.rs for interoperability.

The license search cascade matches Rust exactly:
1. Explicit license_path option
2. HYPERSEC_LICENSE_PATH environment variable
3. Standard paths (./license.enc, /etc/hypersec/license.enc, etc.)
4. HYPERSEC_LICENSE_URL environment variable (if httpx available)
5. Compiled-in defaults (Community tier)
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from . import crypto, defaults, integrity
from .error import (
    LicenseAlreadyInitializedError,
    LicenseExpiredError,
    LicenseFetchError,
    LicenseLoadError,
    LicenseNotInitializedError,
    LicenseParseError,
)
from .types import (
    LicenseOptions,
    LicenseSettings,
    LicenseSource,
    LicenseSourceInfo,
)

# Global singleton
_license: License | None = None
_license_lock = threading.Lock()


class License:
    """License manager holding the current license state.

    This class is not typically instantiated directly. Use the module-level
    init() function to initialise the global license singleton.
    """

    def __init__(
        self,
        settings: LicenseSettings,
        settings_hash: bytes,
        source_info: LicenseSourceInfo,
    ) -> None:
        """Initialise the license manager.

        Args:
            settings: The loaded license settings.
            settings_hash: SHA-256 hash of settings for integrity checks.
            source_info: Information about where the license was loaded from.
        """
        self._settings = settings
        self._settings_hash = settings_hash
        self._source_info = source_info

    @classmethod
    def load(cls, opts: LicenseOptions) -> License:
        """Load a license with the given options.

        Args:
            opts: License loading options.

        Returns:
            Initialised License instance.

        Raises:
            LicenseLoadError: If the license file cannot be loaded.
            LicenseDecryptionError: If decryption fails.
            LicenseParseError: If the license JSON is invalid.
            LicenseSignatureError: If signature verification fails.
            LicenseExpiredError: If the license has expired and allow_expired is False.
        """
        settings, source_info = cls._load_license(opts)

        # Verify signature if required
        if opts.verify_signature and not settings.is_default:
            integrity.verify_signature(settings)

        # Check expiration
        if settings.is_expired() and not opts.allow_expired:
            raise LicenseExpiredError(settings.expires_at or "")

        # Compute integrity hash
        settings_hash = integrity.compute_settings_hash(settings)

        return cls(settings, settings_hash, source_info)

    @classmethod
    def _load_license(cls, opts: LicenseOptions) -> tuple[LicenseSettings, LicenseSourceInfo]:
        """Load license from file, URL, or defaults.

        Implements the search cascade matching Rust exactly.
        """
        # Priority 1: Explicit path
        if opts.license_path is not None:
            return cls._load_from_file(opts.license_path, opts)

        # Priority 2: Environment variable
        env_path = os.environ.get("HYPERSEC_LICENSE_PATH")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return cls._load_from_file(path, opts)

        # Priority 3: Standard locations
        for path in cls._standard_license_paths():
            if path.exists():
                try:
                    return cls._load_from_file(path, opts)
                except Exception:
                    # Try next path on failure
                    continue

        # Priority 4: URL (environment variable or option)
        url = opts.license_url or os.environ.get("HYPERSEC_LICENSE_URL")
        if url:
            try:
                return cls._load_from_url(url, opts)
            except Exception:
                # Fall through to defaults
                pass

        # Priority 5: Compiled defaults
        return (
            defaults.get_default_settings(),
            LicenseSourceInfo(source=LicenseSource.DEFAULT),
        )

    @staticmethod
    def _standard_license_paths() -> list[Path]:
        """Get standard paths to search for license files.

        Returns paths in the same order as the Rust implementation.
        """
        paths: list[Path] = []

        # Current directory
        paths.append(Path("license.enc"))
        paths.append(Path(".license.enc"))

        # /etc/hypersec/
        paths.append(Path("/etc/hypersec/license.enc"))

        # User config directory
        # XDG_CONFIG_HOME or ~/.config
        config_home = os.environ.get("XDG_CONFIG_HOME")
        if config_home:
            paths.append(Path(config_home) / "hypersec" / "license.enc")
        else:
            home = Path.home()
            paths.append(home / ".config" / "hypersec" / "license.enc")

        # Home directory
        paths.append(Path.home() / ".hypersec" / "license.enc")

        return paths

    @classmethod
    def _load_from_file(cls, path: Path, opts: LicenseOptions) -> tuple[LicenseSettings, LicenseSourceInfo]:
        """Load and decrypt a license file."""
        try:
            encrypted = path.read_bytes()
        except Exception as e:
            raise LicenseLoadError(path, str(e)) from e

        settings = cls._decrypt_and_parse(encrypted, opts)
        return (
            settings,
            LicenseSourceInfo(source=LicenseSource.FILE, path=path),
        )

    @classmethod
    def _load_from_url(cls, url: str, opts: LicenseOptions) -> tuple[LicenseSettings, LicenseSourceInfo]:
        """Fetch and decrypt a license from URL."""
        try:
            import httpx
        except ImportError as e:
            raise LicenseFetchError(url, "httpx not installed - install with: pip install httpx") from e

        try:
            response = httpx.get(url, timeout=30.0)
            response.raise_for_status()
            encrypted = response.content
        except Exception as e:
            raise LicenseFetchError(url, str(e)) from e

        settings = cls._decrypt_and_parse(encrypted, opts)
        return (
            settings,
            LicenseSourceInfo(source=LicenseSource.URL, url=url),
        )

    @classmethod
    def _decrypt_and_parse(cls, encrypted: bytes, opts: LicenseOptions) -> LicenseSettings:
        """Decrypt encrypted data and parse as license settings."""
        # Get decryption key
        if opts.custom_key is not None:
            key = crypto.derive_key(opts.custom_key)
        else:
            key = crypto.derive_key(defaults.get_decryption_key())

        # Decrypt
        decrypted = crypto.decrypt(encrypted, key)

        # Parse JSON
        try:
            data = json.loads(decrypted)
        except Exception as e:
            raise LicenseParseError(str(e)) from e

        return LicenseSettings.from_dict(data)

    @property
    def settings(self) -> LicenseSettings:
        """Get the license settings."""
        return self._settings

    @property
    def source(self) -> LicenseSource:
        """Get the license source type."""
        return self._source_info.source

    @property
    def source_info(self) -> LicenseSourceInfo:
        """Get detailed license source information."""
        return self._source_info

    def verify_integrity(self) -> None:
        """Run integrity checks on the license.

        Call this periodically to detect tampering.

        Raises:
            LicenseIntegrityError: If the settings have been modified.
            LicenseExpiredError: If the license has expired.
        """
        integrity.run_integrity_checks(self._settings, self._settings_hash)


# =============================================================================
# Global singleton API
# =============================================================================


def init(opts: LicenseOptions | None = None) -> None:
    """Initialise the global license.

    This should be called once at application startup.

    Args:
        opts: License loading options. If None, uses defaults.

    Raises:
        LicenseAlreadyInitializedError: If the license was already initialised.
        LicenseLoadError: If the license file cannot be loaded.
        LicenseDecryptionError: If decryption fails.
        LicenseParseError: If the license JSON is invalid.
        LicenseSignatureError: If signature verification fails.
        LicenseExpiredError: If the license has expired.
    """
    global _license

    if opts is None:
        opts = LicenseOptions()

    with _license_lock:
        if _license is not None:
            raise LicenseAlreadyInitializedError()
        _license = License.load(opts)


def init_default() -> None:
    """Initialise with default options.

    Searches standard paths and falls back to compiled defaults.

    Raises:
        LicenseAlreadyInitializedError: If the license was already initialised.
    """
    init(LicenseOptions())


def reset() -> None:
    """Reset the global license singleton.

    This is primarily for testing. Production code should not call this.
    """
    global _license

    with _license_lock:
        _license = None


def get() -> LicenseSettings:
    """Get the global license settings.

    Returns:
        The license settings.

    Raises:
        LicenseNotInitializedError: If the license has not been initialised.
    """
    if _license is None:
        raise LicenseNotInitializedError()
    return _license.settings


def try_get() -> LicenseSettings | None:
    """Try to get the global license settings.

    Returns:
        The license settings, or None if not initialised.
    """
    if _license is None:
        return None
    return _license.settings


def get_license() -> License:
    """Get the full license manager.

    Returns:
        The License instance.

    Raises:
        LicenseNotInitializedError: If the license has not been initialised.
    """
    if _license is None:
        raise LicenseNotInitializedError()
    return _license


def verify_integrity() -> None:
    """Verify license integrity.

    Call this periodically to detect tampering.

    Raises:
        LicenseNotInitializedError: If the license has not been initialised.
        LicenseIntegrityError: If integrity checks fail.
        LicenseExpiredError: If the license has expired.
    """
    get_license().verify_integrity()


def is_default() -> bool:
    """Check if using default (fallback) license.

    Returns:
        True if using the compiled-in default license.
    """
    settings = try_get()
    if settings is None:
        return True
    return settings.is_default


def has_feature(name: str) -> bool:
    """Check if a feature is enabled in the license.

    Args:
        name: The feature name to check.

    Returns:
        True if the feature is enabled.
    """
    settings = try_get()
    if settings is None:
        return False
    return settings.has_feature(name)


# =============================================================================
# Utility functions for license file creation (external tooling)
# =============================================================================


def encrypt_license(settings: LicenseSettings, key: bytes) -> bytes:
    """Encrypt license settings for distribution.

    This is used by external tooling to create encrypted license files.

    Args:
        settings: The license settings to encrypt.
        key: The secret key (will be derived via SHA-256).

    Returns:
        Encrypted license data.

    Raises:
        LicenseEncryptionError: If encryption fails.
    """
    # Serialise to JSON
    data = settings.to_dict()
    json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")

    # Derive key and encrypt
    derived_key = crypto.derive_key(key)
    return crypto.encrypt(json_bytes, derived_key)


def decrypt_license(encrypted: bytes, key: bytes) -> LicenseSettings:
    """Decrypt a license file for inspection.

    This is used by external tooling to verify license contents.

    Args:
        encrypted: The encrypted license data.
        key: The secret key (will be derived via SHA-256).

    Returns:
        The decrypted license settings.

    Raises:
        LicenseDecryptionError: If decryption fails.
        LicenseParseError: If the JSON is invalid.
    """
    # Derive key and decrypt
    derived_key = crypto.derive_key(key)
    decrypted = crypto.decrypt(encrypted, derived_key)

    # Parse JSON
    try:
        data = json.loads(decrypted)
    except Exception as e:
        raise LicenseParseError(str(e)) from e

    return LicenseSettings.from_dict(data)
