# Project:   hyperi-pylib
# File:      tests/unit/test_license_defaults.py
# Purpose:   Unit tests for license defaults module
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for hyperi_pylib.license.defaults module."""

from __future__ import annotations

from hyperi_pylib.license.defaults import (
    get_decryption_key,
    get_default_settings,
    get_test_enterprise_settings,
)


class TestGetDecryptionKey:
    """Tests for get_decryption_key function."""

    def test_returns_bytes(self) -> None:
        """Should return bytes."""
        key = get_decryption_key()
        assert isinstance(key, bytes)

    def test_not_empty(self) -> None:
        """Key should not be empty."""
        key = get_decryption_key()
        assert len(key) > 0

    def test_minimum_length(self) -> None:
        """Key should be at least 16 bytes (128 bits)."""
        key = get_decryption_key()
        assert len(key) >= 16

    def test_deterministic(self) -> None:
        """Same key should be returned each time."""
        key1 = get_decryption_key()
        key2 = get_decryption_key()
        assert key1 == key2


class TestGetDefaultSettings:
    """Tests for get_default_settings function."""

    def test_returns_license_settings(self) -> None:
        """Should return LicenseSettings instance."""
        from hyperi_pylib.license.types import LicenseSettings

        settings = get_default_settings()
        assert isinstance(settings, LicenseSettings)

    def test_community_label(self) -> None:
        """Should have Community label."""
        settings = get_default_settings()
        assert settings.label == "Community"

    def test_is_default_true(self) -> None:
        """is_default should be True."""
        settings = get_default_settings()
        assert settings.is_default is True

    def test_has_limits(self) -> None:
        """Community tier should have resource limits."""
        settings = get_default_settings()
        assert settings.max_cores == 4
        assert settings.max_memory_gb == 8
        assert settings.max_throughput_mbps == 100
        assert settings.max_container_throughput_mbps == 25
        assert settings.max_nodes == 1

    def test_no_expiry(self) -> None:
        """Default license should not expire."""
        settings = get_default_settings()
        assert settings.expires_at is None
        assert settings.is_expired() is False

    def test_no_signature(self) -> None:
        """Default license should have no signature."""
        settings = get_default_settings()
        assert settings.signature is None

    def test_no_features(self) -> None:
        """Default license should have no features enabled."""
        settings = get_default_settings()
        assert settings.features == {}

    def test_no_organization(self) -> None:
        """Default license should have no organization."""
        settings = get_default_settings()
        assert settings.organization is None


class TestGetTestEnterpriseSettings:
    """Tests for get_test_enterprise_settings function."""

    def test_returns_license_settings(self) -> None:
        """Should return LicenseSettings instance."""
        from hyperi_pylib.license.types import LicenseSettings

        settings = get_test_enterprise_settings()
        assert isinstance(settings, LicenseSettings)

    def test_enterprise_label(self) -> None:
        """Should have Enterprise label."""
        settings = get_test_enterprise_settings()
        assert settings.label == "Enterprise"

    def test_is_default_false(self) -> None:
        """is_default should be False."""
        settings = get_test_enterprise_settings()
        assert settings.is_default is False

    def test_unlimited(self) -> None:
        """Enterprise should have no resource limits."""
        settings = get_test_enterprise_settings()
        assert settings.max_cores is None
        assert settings.max_memory_gb is None
        assert settings.max_throughput_mbps is None
        assert settings.max_container_throughput_mbps is None
        assert settings.max_nodes is None
        assert settings.is_unlimited() is True

    def test_has_organization(self) -> None:
        """Enterprise should have test organization."""
        settings = get_test_enterprise_settings()
        assert settings.organization == "Test Organization"

    def test_has_features(self) -> None:
        """Enterprise should have features enabled."""
        settings = get_test_enterprise_settings()
        assert settings.has_feature("advanced_analytics")
        assert settings.has_feature("custom_rules")
        assert settings.has_feature("multi_tenant")

    def test_no_expiry(self) -> None:
        """Test enterprise should not expire."""
        settings = get_test_enterprise_settings()
        assert settings.expires_at is None
        assert settings.is_expired() is False

    def test_has_issued_at(self) -> None:
        """Test enterprise should have issued_at."""
        settings = get_test_enterprise_settings()
        assert settings.issued_at is not None
