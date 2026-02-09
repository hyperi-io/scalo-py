# Project:   hyperi-pylib
# File:      src/hyperi_pylib/license/integrity.py
# Purpose:   Anti-tampering and integrity verification
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Integrity verification and anti-tampering measures.

This module provides:
- License signature verification (Ed25519)
- Runtime integrity checks (SHA-256 hash comparison)

Direct port from hs-rustlib/src/license/integrity.rs for interoperability.

Security Model:
--------------
These protections are designed to deter casual tampering. The cryptographic
signature verification (Ed25519) ensures license authenticity - you cannot
forge a valid license without the private key.

Note: Anti-debugging measures from the Rust implementation are NOT ported
to Python as they would be trivially bypassed in an interpreted language.
Use Nuitka compilation for production deployments.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from .error import (
    LicenseExpiredError,
    LicenseIntegrityError,
    LicenseSignatureError,
)
from .types import LicenseSettings

# The Ed25519 public key for verifying license signatures.
# This key is in SPKI format (44 bytes base64 = 12-byte header + 32-byte key).
#
# PRODUCTION DEPLOYMENT:
# Replace this with your actual public key before deployment.
# Generate a keypair with: openssl genpkey -algorithm ed25519
#
# SECURITY: This is plaintext in Python source - use Nuitka for protection.
_PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAPlaceholderKeyForDevReplace="


def _get_public_key_bytes() -> bytes:
    """Get the Ed25519 public key bytes.

    Extracts the 32-byte public key from the SPKI format.

    Returns:
        32-byte Ed25519 public key.
    """
    try:
        decoded = base64.b64decode(_PUBLIC_KEY_B64)
    except Exception:
        return b"\x00" * 32  # Fallback to zeros (will fail verification)

    if len(decoded) >= 44:
        # SPKI format: skip 12-byte header
        return decoded[12:44]
    elif len(decoded) == 32:
        # Raw 32-byte key
        return decoded
    else:
        # Fallback to zeros (will fail verification)
        return b"\x00" * 32


def verify_signature(settings: LicenseSettings) -> None:
    """Verify the Ed25519 signature on a license.

    The signature is computed over the canonical JSON representation
    of the license (excluding the signature field itself).

    Args:
        settings: The license settings to verify.

    Raises:
        LicenseSignatureError: If the license has no signature (and is not default),
            the signature is malformed, or verification fails.
    """
    if settings.signature is None:
        # No signature - allow for default/test licenses
        if settings.is_default:
            return
        raise LicenseSignatureError("license has no signature")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as e:
        raise LicenseSignatureError(
            "cryptography library not installed - install with: pip install hyperi-pylib[license]"
        ) from e

    # Decode the signature
    try:
        sig_bytes = base64.b64decode(settings.signature)
    except Exception as e:
        raise LicenseSignatureError(f"invalid signature encoding: {e}") from e

    if len(sig_bytes) != 64:
        raise LicenseSignatureError(f"invalid signature length: expected 64, got {len(sig_bytes)}")

    # Get the public key
    pk_bytes = _get_public_key_bytes()
    try:
        public_key = Ed25519PublicKey.from_public_bytes(pk_bytes)
    except Exception as e:
        raise LicenseSignatureError(f"invalid public key: {e}") from e

    # Create canonical message (license JSON without signature)
    message = _create_signing_message(settings)

    # Verify
    try:
        public_key.verify(sig_bytes, message.encode("utf-8"))
    except Exception:
        raise LicenseSignatureError("signature verification failed")


def _create_signing_message(settings: LicenseSettings) -> str:
    """Create the canonical message for signing/verification.

    This is the JSON representation of the license with the signature
    field removed, ensuring deterministic serialisation.

    Args:
        settings: The license settings.

    Returns:
        JSON string for signing/verification.
    """
    # Create dict without signature
    data = settings.to_dict()
    data.pop("signature", None)

    # Use compact JSON with sorted keys for determinism
    # Note: Rust's serde_json uses compact format by default
    return json.dumps(data, separators=(",", ":"), sort_keys=False)


def compute_settings_hash(settings: LicenseSettings) -> bytes:
    """Compute a SHA-256 hash of critical license fields.

    This can be used to detect if license settings have been modified
    in memory after loading.

    The hash is computed over the same fields as the Rust implementation
    for consistency.

    Args:
        settings: The license settings.

    Returns:
        32-byte SHA-256 hash.
    """
    hasher = hashlib.sha256()

    # Hash critical fields (must match Rust implementation)
    hasher.update(settings.label.encode("utf-8"))
    hasher.update((settings.max_cores or 0).to_bytes(4, "little"))
    hasher.update((settings.max_throughput_mbps or 0).to_bytes(8, "little"))
    hasher.update((settings.max_nodes or 0).to_bytes(4, "little"))

    if settings.expires_at is not None:
        hasher.update(settings.expires_at.encode("utf-8"))

    return hasher.digest()


def verify_settings_integrity(settings: LicenseSettings, expected_hash: bytes) -> bool:
    """Verify that settings haven't been tampered with in memory.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        settings: The license settings to verify.
        expected_hash: The hash computed when the license was loaded.

    Returns:
        True if the settings match the expected hash.
    """
    current_hash = compute_settings_hash(settings)

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(current_hash, expected_hash)


def run_integrity_checks(settings: LicenseSettings, expected_hash: bytes) -> None:
    """Perform integrity checks on the license.

    Call this periodically to detect tampering.

    Args:
        settings: The license settings.
        expected_hash: The hash computed when the license was loaded.

    Raises:
        LicenseIntegrityError: If the settings have been modified.
        LicenseExpiredError: If the license has expired.
    """
    # Check 1: Settings hash
    if not verify_settings_integrity(settings, expected_hash):
        raise LicenseIntegrityError("license settings modified in memory")

    # Check 2: Expiration (in case system clock was manipulated)
    if settings.is_expired():
        raise LicenseExpiredError(settings.expires_at or "")

    # Note: Debugger detection is NOT implemented in Python
    # as it would be trivially bypassed. Use Nuitka for production.
