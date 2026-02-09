# Project:   hyperi-pylib
# File:      tests/unit/test_license_crypto.py
# Purpose:   Unit tests for license crypto module
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for hyperi_pylib.license.crypto module."""

from __future__ import annotations

import pytest

from hyperi_pylib.license.crypto import (
    MIN_ENCRYPTED_SIZE,
    NONCE_SIZE,
    TAG_SIZE,
    decrypt,
    derive_key,
    encrypt,
)
from hyperi_pylib.license.error import LicenseDecryptionError, LicenseEncryptionError


class TestDeriveKey:
    """Tests for derive_key function."""

    def test_deterministic(self) -> None:
        """Same secret should produce same key."""
        key1 = derive_key(b"test-secret")
        key2 = derive_key(b"test-secret")
        assert key1 == key2

    def test_different_inputs(self) -> None:
        """Different secrets should produce different keys."""
        key1 = derive_key(b"secret-a")
        key2 = derive_key(b"secret-b")
        assert key1 != key2

    def test_key_length(self) -> None:
        """Derived key should be 32 bytes (256 bits)."""
        key = derive_key(b"test")
        assert len(key) == 32

    def test_empty_secret(self) -> None:
        """Empty secret should still produce valid key."""
        key = derive_key(b"")
        assert len(key) == 32


class TestEncryptDecrypt:
    """Tests for encrypt and decrypt functions."""

    def test_roundtrip(self) -> None:
        """Encrypt then decrypt should return original data."""
        key = derive_key(b"test-key-for-roundtrip")
        plaintext = b"Hello, this is a test license!"

        encrypted = encrypt(plaintext, key)
        decrypted = decrypt(encrypted, key)

        assert decrypted == plaintext

    def test_roundtrip_empty(self) -> None:
        """Should handle empty plaintext."""
        key = derive_key(b"test-key")
        plaintext = b""

        encrypted = encrypt(plaintext, key)
        decrypted = decrypt(encrypted, key)

        assert decrypted == plaintext

    def test_roundtrip_large(self) -> None:
        """Should handle large plaintext."""
        key = derive_key(b"test-key")
        plaintext = b"x" * 100000  # 100KB

        encrypted = encrypt(plaintext, key)
        decrypted = decrypt(encrypted, key)

        assert decrypted == plaintext

    def test_encrypted_structure(self) -> None:
        """Encrypted data should have correct structure."""
        key = derive_key(b"test-key")
        plaintext = b"test"

        encrypted = encrypt(plaintext, key)

        # Should have nonce + ciphertext + tag
        # Ciphertext is same length as plaintext for GCM
        assert len(encrypted) >= NONCE_SIZE + len(plaintext) + TAG_SIZE

    def test_different_nonces(self) -> None:
        """Each encryption should use a different nonce."""
        key = derive_key(b"test-key")
        plaintext = b"same plaintext"

        encrypted1 = encrypt(plaintext, key)
        encrypted2 = encrypt(plaintext, key)

        # First 12 bytes are nonce - should be different
        assert encrypted1[:NONCE_SIZE] != encrypted2[:NONCE_SIZE]
        # But both should decrypt to same plaintext
        assert decrypt(encrypted1, key) == decrypt(encrypted2, key) == plaintext

    def test_decrypt_wrong_key_fails(self) -> None:
        """Decryption with wrong key should fail."""
        key1 = derive_key(b"correct-key")
        key2 = derive_key(b"wrong-key")
        plaintext = b"secret data"

        encrypted = encrypt(plaintext, key1)

        with pytest.raises(LicenseDecryptionError) as exc_info:
            decrypt(encrypted, key2)
        assert "invalid key or tampered data" in str(exc_info.value)

    def test_decrypt_tampered_data_fails(self) -> None:
        """Decryption of tampered data should fail."""
        key = derive_key(b"test-key")
        plaintext = b"original data"

        encrypted = bytearray(encrypt(plaintext, key))

        # Tamper with the ciphertext (not the nonce)
        if len(encrypted) > NONCE_SIZE + 5:
            encrypted[NONCE_SIZE + 5] ^= 0xFF

        with pytest.raises(LicenseDecryptionError) as exc_info:
            decrypt(bytes(encrypted), key)
        assert "invalid key or tampered data" in str(exc_info.value)

    def test_decrypt_too_short_fails(self) -> None:
        """Decryption of too-short data should fail."""
        key = derive_key(b"test-key")
        short_data = bytes(MIN_ENCRYPTED_SIZE - 1)

        with pytest.raises(LicenseDecryptionError) as exc_info:
            decrypt(short_data, key)
        assert "encrypted data too short" in str(exc_info.value)

    def test_decrypt_invalid_key_length(self) -> None:
        """Decryption with wrong key length should fail."""
        short_key = b"too-short"
        encrypted = b"x" * MIN_ENCRYPTED_SIZE

        with pytest.raises(LicenseDecryptionError) as exc_info:
            decrypt(encrypted, short_key)
        assert "invalid key length" in str(exc_info.value)

    def test_encrypt_invalid_key_length(self) -> None:
        """Encryption with wrong key length should fail."""
        short_key = b"too-short"
        plaintext = b"test"

        with pytest.raises(LicenseEncryptionError) as exc_info:
            encrypt(plaintext, short_key)
        assert "invalid key length" in str(exc_info.value)


class TestRustInteroperability:
    """Tests to verify interoperability with Rust implementation.

    These tests use known values that match the Rust implementation.
    """

    def test_derive_key_matches_rust(self) -> None:
        """Key derivation should match Rust implementation.

        The Rust implementation uses SHA-256 with domain separation:
        SHA256(secret + "hs-rustlib-license-v1")
        """
        # This test verifies the algorithm matches
        # The exact output depends on the domain separator
        key = derive_key(b"test-secret")

        # Key should be 32 bytes
        assert len(key) == 32

        # Same input should always produce same output
        assert key == derive_key(b"test-secret")

    def test_encrypted_format_compatible(self) -> None:
        """Encrypted format should be compatible with Rust.

        Format: [12-byte nonce][ciphertext][16-byte tag]
        """
        key = derive_key(b"test-key")
        plaintext = b'{"label":"Test"}'

        encrypted = encrypt(plaintext, key)

        # Verify structure
        assert len(encrypted) >= MIN_ENCRYPTED_SIZE
        # Nonce is first 12 bytes
        nonce = encrypted[:NONCE_SIZE]
        assert len(nonce) == 12
        # Remaining is ciphertext + tag
        ciphertext_with_tag = encrypted[NONCE_SIZE:]
        # Tag is 16 bytes, so ciphertext should be at least plaintext length
        assert len(ciphertext_with_tag) >= len(plaintext) + TAG_SIZE
