# Project:   hyperi-pylib
# File:      src/hyperi_pylib/license/error.py
# Purpose:   License module error types
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Error types for the license module."""

from __future__ import annotations

from pathlib import Path


class LicenseError(Exception):
    """Base exception for all license-related errors."""


class LicenseLoadError(LicenseError):
    """Failed to load license file from disk."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"failed to load license file '{path}': {reason}")


class LicenseFetchError(LicenseError):
    """Failed to fetch license from URL."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"failed to fetch license from '{url}': {reason}")


class LicenseDecryptionError(LicenseError):
    """Decryption of license data failed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"license decryption failed: {reason}")


class LicenseEncryptionError(LicenseError):
    """Encryption of license data failed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"license encryption failed: {reason}")


class LicenseParseError(LicenseError):
    """License JSON parsing failed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid license format: {reason}")


class LicenseSignatureError(LicenseError):
    """License signature verification failed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"license signature invalid: {reason}")


class LicenseExpiredError(LicenseError):
    """License has expired."""

    def __init__(self, expiry: str) -> None:
        self.expiry = expiry
        super().__init__(f"license expired on {expiry}")


class LicenseIntegrityError(LicenseError):
    """Integrity check failed (tampering detected)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"integrity check failed: {reason}")


class LicenseNotInitializedError(LicenseError):
    """License not initialized."""

    def __init__(self) -> None:
        super().__init__("license not initialized - call license.init() first")


class LicenseAlreadyInitializedError(LicenseError):
    """License already initialized."""

    def __init__(self) -> None:
        super().__init__("license already initialized")
