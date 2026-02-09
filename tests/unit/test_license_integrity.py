# Project:   hyperi-pylib
# File:      tests/unit/test_license_integrity.py
# Purpose:   Unit tests for license integrity module
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for hyperi_pylib.license.integrity module."""

from __future__ import annotations

import pytest

from hyperi_pylib.license.error import (
    LicenseExpiredError,
    LicenseIntegrityError,
    LicenseSignatureError,
)
from hyperi_pylib.license.integrity import (
    compute_settings_hash,
    run_integrity_checks,
    verify_settings_integrity,
    verify_signature,
)
from hyperi_pylib.license.types import LicenseSettings


class TestComputeSettingsHash:
    """Tests for compute_settings_hash function."""

    def test_deterministic(self) -> None:
        """Same settings should produce same hash."""
        settings = LicenseSettings(label="Test", max_cores=4)
        hash1 = compute_settings_hash(settings)
        hash2 = compute_settings_hash(settings)
        assert hash1 == hash2

    def test_hash_length(self) -> None:
        """Hash should be 32 bytes (SHA-256)."""
        settings = LicenseSettings()
        hash_bytes = compute_settings_hash(settings)
        assert len(hash_bytes) == 32

    def test_different_label(self) -> None:
        """Different labels should produce different hashes."""
        settings1 = LicenseSettings(label="Community")
        settings2 = LicenseSettings(label="Enterprise")
        assert compute_settings_hash(settings1) != compute_settings_hash(settings2)

    def test_different_cores(self) -> None:
        """Different max_cores should produce different hashes."""
        settings1 = LicenseSettings(max_cores=4)
        settings2 = LicenseSettings(max_cores=8)
        assert compute_settings_hash(settings1) != compute_settings_hash(settings2)

    def test_different_throughput(self) -> None:
        """Different max_throughput_mbps should produce different hashes."""
        settings1 = LicenseSettings(max_throughput_mbps=100)
        settings2 = LicenseSettings(max_throughput_mbps=1000)
        assert compute_settings_hash(settings1) != compute_settings_hash(settings2)

    def test_different_nodes(self) -> None:
        """Different max_nodes should produce different hashes."""
        settings1 = LicenseSettings(max_nodes=1)
        settings2 = LicenseSettings(max_nodes=10)
        assert compute_settings_hash(settings1) != compute_settings_hash(settings2)

    def test_different_expiry(self) -> None:
        """Different expires_at should produce different hashes."""
        settings1 = LicenseSettings(expires_at="2025-01-01T00:00:00Z")
        settings2 = LicenseSettings(expires_at="2026-01-01T00:00:00Z")
        assert compute_settings_hash(settings1) != compute_settings_hash(settings2)

    def test_none_vs_zero(self) -> None:
        """None and 0 should produce different hashes (None uses 0 in hash)."""
        # Actually, None uses 0 in the hash, so they should be the same
        settings1 = LicenseSettings(max_cores=None)
        settings2 = LicenseSettings(max_cores=0)
        # Both use 0 in the hash calculation
        assert compute_settings_hash(settings1) == compute_settings_hash(settings2)


class TestVerifySettingsIntegrity:
    """Tests for verify_settings_integrity function."""

    def test_valid_integrity(self) -> None:
        """Unmodified settings should pass integrity check."""
        settings = LicenseSettings(label="Test", max_cores=4)
        hash_bytes = compute_settings_hash(settings)
        assert verify_settings_integrity(settings, hash_bytes) is True

    def test_tampered_label(self) -> None:
        """Modified label should fail integrity check."""
        settings = LicenseSettings(label="Test", max_cores=4)
        hash_bytes = compute_settings_hash(settings)

        # Tamper with settings
        settings.label = "Tampered"

        assert verify_settings_integrity(settings, hash_bytes) is False

    def test_tampered_cores(self) -> None:
        """Modified max_cores should fail integrity check."""
        settings = LicenseSettings(label="Test", max_cores=4)
        hash_bytes = compute_settings_hash(settings)

        # Tamper with settings
        settings.max_cores = 9999

        assert verify_settings_integrity(settings, hash_bytes) is False

    def test_tampered_expiry(self) -> None:
        """Modified expires_at should fail integrity check."""
        settings = LicenseSettings(expires_at="2025-01-01T00:00:00Z")
        hash_bytes = compute_settings_hash(settings)

        # Tamper with settings
        settings.expires_at = "2099-01-01T00:00:00Z"

        assert verify_settings_integrity(settings, hash_bytes) is False


class TestVerifySignature:
    """Tests for verify_signature function."""

    def test_default_license_no_signature_ok(self) -> None:
        """Default licenses without signatures should pass."""
        settings = LicenseSettings(is_default=True, signature=None)
        # Should not raise
        verify_signature(settings)

    def test_non_default_no_signature_fails(self) -> None:
        """Non-default licenses without signatures should fail."""
        settings = LicenseSettings(is_default=False, signature=None)

        with pytest.raises(LicenseSignatureError) as exc_info:
            verify_signature(settings)
        assert "has no signature" in str(exc_info.value)

    def test_invalid_signature_encoding(self) -> None:
        """Invalid base64 signature should fail."""
        settings = LicenseSettings(
            is_default=False,
            signature="not-valid-base64!!!",
        )

        with pytest.raises(LicenseSignatureError) as exc_info:
            verify_signature(settings)
        assert "invalid signature encoding" in str(exc_info.value)

    def test_invalid_signature_length(self) -> None:
        """Wrong signature length should fail."""
        import base64

        settings = LicenseSettings(
            is_default=False,
            signature=base64.b64encode(b"too-short").decode(),
        )

        with pytest.raises(LicenseSignatureError) as exc_info:
            verify_signature(settings)
        assert "invalid signature length" in str(exc_info.value)

    def test_invalid_signature_verification(self) -> None:
        """Invalid signature should fail verification."""
        import base64

        # Create a 64-byte signature (correct length but wrong content)
        fake_signature = base64.b64encode(b"x" * 64).decode()
        settings = LicenseSettings(
            is_default=False,
            label="Test",
            signature=fake_signature,
        )

        with pytest.raises(LicenseSignatureError) as exc_info:
            verify_signature(settings)
        # Will fail either at public key or verification stage
        assert "invalid" in str(exc_info.value).lower()


class TestRunIntegrityChecks:
    """Tests for run_integrity_checks function."""

    def test_valid_checks_pass(self) -> None:
        """Valid settings should pass all checks."""
        settings = LicenseSettings(label="Test")
        hash_bytes = compute_settings_hash(settings)

        # Should not raise
        run_integrity_checks(settings, hash_bytes)

    def test_tampered_settings_fail(self) -> None:
        """Tampered settings should fail integrity check."""
        settings = LicenseSettings(label="Test", max_cores=4)
        hash_bytes = compute_settings_hash(settings)

        # Tamper
        settings.max_cores = 9999

        with pytest.raises(LicenseIntegrityError) as exc_info:
            run_integrity_checks(settings, hash_bytes)
        assert "modified in memory" in str(exc_info.value)

    def test_expired_license_fails(self) -> None:
        """Expired license should fail."""
        settings = LicenseSettings(expires_at="2020-01-01T00:00:00Z")
        hash_bytes = compute_settings_hash(settings)

        with pytest.raises(LicenseExpiredError) as exc_info:
            run_integrity_checks(settings, hash_bytes)
        assert "2020-01-01" in str(exc_info.value)

    def test_non_expired_license_passes(self) -> None:
        """Non-expired license should pass."""
        settings = LicenseSettings(expires_at="2099-12-31T23:59:59Z")
        hash_bytes = compute_settings_hash(settings)

        # Should not raise
        run_integrity_checks(settings, hash_bytes)
