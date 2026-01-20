# Project:   hs-pylib
# File:      src/hs_pylib/license/crypto.py
# Purpose:   AES-256-GCM encryption/decryption for license files
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2026 HyperSec

"""Cryptographic operations for license file encryption/decryption.

Uses AES-256-GCM for authenticated encryption. The encryption key is
derived from a secret using SHA-256 with domain separation.

Direct port from hs-rustlib/src/license/crypto.rs for interoperability.
The encrypted format MUST match exactly for cross-language compatibility.

Format:
    [12-byte nonce][ciphertext][16-byte auth tag]
"""

from __future__ import annotations

import hashlib
import os

from .error import LicenseDecryptionError, LicenseEncryptionError

# Nonce size for AES-GCM (96 bits / 12 bytes)
NONCE_SIZE = 12

# Authentication tag size (128 bits / 16 bytes)
TAG_SIZE = 16

# Minimum encrypted payload size (nonce + tag)
MIN_ENCRYPTED_SIZE = NONCE_SIZE + TAG_SIZE

# Domain separation string - MUST match Rust implementation exactly
_DOMAIN_SEPARATOR = b"hs-rustlib-license-v1"


def derive_key(secret: bytes) -> bytes:
    """Derive a 256-bit key from a secret.

    Uses SHA-256 with domain separation to derive a fixed-size key.
    This MUST match the Rust implementation exactly for interoperability.

    Args:
        secret: The secret bytes to derive from.

    Returns:
        32-byte derived key suitable for AES-256.
    """
    hasher = hashlib.sha256()
    hasher.update(secret)
    hasher.update(_DOMAIN_SEPARATOR)
    return hasher.digest()


def decrypt(encrypted: bytes, key: bytes) -> bytes:
    """Decrypt an AES-256-GCM encrypted payload.

    Args:
        encrypted: The encrypted data in format [nonce][ciphertext][tag].
        key: The 32-byte AES-256 key.

    Returns:
        The decrypted plaintext.

    Raises:
        LicenseDecryptionError: If decryption fails (wrong key, tampered data,
            or data too short).
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise LicenseDecryptionError(
            "cryptography library not installed - install with: pip install hs-pylib[license]"
        ) from e

    if len(encrypted) < MIN_ENCRYPTED_SIZE:
        raise LicenseDecryptionError("encrypted data too short")

    if len(key) != 32:
        raise LicenseDecryptionError(f"invalid key length: expected 32, got {len(key)}")

    # Extract nonce (first 12 bytes)
    nonce = encrypted[:NONCE_SIZE]
    # Remaining bytes are ciphertext + tag (AESGCM handles tag internally)
    ciphertext_with_tag = encrypted[NONCE_SIZE:]

    try:
        cipher = AESGCM(key)
        plaintext = cipher.decrypt(nonce, ciphertext_with_tag, associated_data=None)
        return plaintext
    except Exception as e:
        raise LicenseDecryptionError("decryption failed - invalid key or tampered data") from e


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt data using AES-256-GCM.

    This is used for creating license files (external tooling).
    The nonce is randomly generated and prepended to the ciphertext.

    Args:
        plaintext: The data to encrypt.
        key: The 32-byte AES-256 key.

    Returns:
        Encrypted data in format [nonce][ciphertext][tag].

    Raises:
        LicenseEncryptionError: If encryption fails.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise LicenseEncryptionError(
            "cryptography library not installed - install with: pip install hs-pylib[license]"
        ) from e

    if len(key) != 32:
        raise LicenseEncryptionError(f"invalid key length: expected 32, got {len(key)}")

    try:
        # Generate random nonce
        nonce = os.urandom(NONCE_SIZE)

        cipher = AESGCM(key)
        # AESGCM.encrypt() returns ciphertext + tag concatenated
        ciphertext_with_tag = cipher.encrypt(nonce, plaintext, associated_data=None)

        # Prepend nonce to ciphertext
        return nonce + ciphertext_with_tag
    except Exception as e:
        raise LicenseEncryptionError(f"encryption failed: {e}") from e
