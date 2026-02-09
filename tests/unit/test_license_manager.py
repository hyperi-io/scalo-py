# Project:   hyperi-pylib
# File:      tests/unit/test_license_manager.py
# Purpose:   Unit tests for license manager module
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for hyperi_pylib.license.manager module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from hyperi_pylib.license import (
    License,
    LicenseAlreadyInitializedError,
    LicenseDecryptionError,
    LicenseNotInitializedError,
    LicenseOptions,
    LicenseSettings,
    LicenseSource,
    decrypt_license,
    encrypt_license,
    get,
    get_license,
    has_feature,
    init,
    is_default,
    reset,
    try_get,
    verify_integrity,
)
from hyperi_pylib.license.defaults import get_default_settings


@pytest.fixture(autouse=True)
def reset_license() -> None:
    """Reset global license before and after each test."""
    reset()
    yield
    reset()


class TestLicenseOptions:
    """Tests for LicenseOptions."""

    def test_default_options(self) -> None:
        """Default options should have sensible values."""
        opts = LicenseOptions()
        assert opts.license_path is None
        assert opts.verify_signature is True
        assert opts.allow_expired is False
        assert opts.custom_key is None


class TestLicenseClass:
    """Tests for License class."""

    def test_load_with_defaults(self) -> None:
        """License should load with defaults when no file found."""
        opts = LicenseOptions(verify_signature=False)
        license_obj = License.load(opts)

        assert license_obj.settings.is_default is True
        assert license_obj.source == LicenseSource.DEFAULT

    def test_load_from_file(self, tmp_path: Path) -> None:
        """License should load from file."""
        # Create a license file
        settings = LicenseSettings(
            label="Test License",
            max_cores=8,
            is_default=False,
        )
        key = b"test-key"
        encrypted = encrypt_license(settings, key)

        license_file = tmp_path / "license.enc"
        license_file.write_bytes(encrypted)

        # Load it
        opts = LicenseOptions(
            license_path=license_file,
            verify_signature=False,
            custom_key=key,
        )
        license_obj = License.load(opts)

        assert license_obj.settings.label == "Test License"
        assert license_obj.settings.max_cores == 8
        assert license_obj.source == LicenseSource.FILE

    def test_verify_integrity_passes(self) -> None:
        """verify_integrity should pass for unmodified settings."""
        opts = LicenseOptions(verify_signature=False)
        license_obj = License.load(opts)

        # Should not raise
        license_obj.verify_integrity()

    def test_settings_property(self) -> None:
        """settings property should return license settings."""
        opts = LicenseOptions(verify_signature=False)
        license_obj = License.load(opts)

        settings = license_obj.settings
        assert isinstance(settings, LicenseSettings)

    def test_source_property(self) -> None:
        """source property should return license source."""
        opts = LicenseOptions(verify_signature=False)
        license_obj = License.load(opts)

        assert license_obj.source == LicenseSource.DEFAULT


class TestSingletonAPI:
    """Tests for global singleton API."""

    def test_init_default(self) -> None:
        """init() should initialise with defaults."""
        init(LicenseOptions(verify_signature=False))

        settings = get()
        assert settings.is_default is True

    def test_init_already_initialized(self) -> None:
        """init() should fail if already initialised."""
        init(LicenseOptions(verify_signature=False))

        with pytest.raises(LicenseAlreadyInitializedError):
            init(LicenseOptions(verify_signature=False))

    def test_get_not_initialized(self) -> None:
        """get() should fail if not initialised."""
        with pytest.raises(LicenseNotInitializedError):
            get()

    def test_try_get_not_initialized(self) -> None:
        """try_get() should return None if not initialised."""
        result = try_get()
        assert result is None

    def test_try_get_initialized(self) -> None:
        """try_get() should return settings if initialised."""
        init(LicenseOptions(verify_signature=False))

        result = try_get()
        assert result is not None
        assert isinstance(result, LicenseSettings)

    def test_get_license_not_initialized(self) -> None:
        """get_license() should fail if not initialised."""
        with pytest.raises(LicenseNotInitializedError):
            get_license()

    def test_get_license_initialized(self) -> None:
        """get_license() should return License if initialised."""
        init(LicenseOptions(verify_signature=False))

        license_obj = get_license()
        assert isinstance(license_obj, License)

    def test_verify_integrity_singleton(self) -> None:
        """verify_integrity() should work on singleton."""
        init(LicenseOptions(verify_signature=False))

        # Should not raise
        verify_integrity()

    def test_is_default_not_initialized(self) -> None:
        """is_default() should return True if not initialised."""
        assert is_default() is True

    def test_is_default_initialized(self) -> None:
        """is_default() should reflect actual license state."""
        init(LicenseOptions(verify_signature=False))

        # Default settings have is_default=True
        assert is_default() is True

    def test_has_feature_not_initialized(self) -> None:
        """has_feature() should return False if not initialised."""
        assert has_feature("some_feature") is False

    def test_has_feature_initialized(self) -> None:
        """has_feature() should check features on singleton."""
        init(LicenseOptions(verify_signature=False))

        # Default license has no features
        assert has_feature("advanced_analytics") is False

    def test_reset_allows_reinit(self) -> None:
        """reset() should allow re-initialisation."""
        init(LicenseOptions(verify_signature=False))
        reset()

        # Should not raise
        init(LicenseOptions(verify_signature=False))


class TestEncryptDecryptLicense:
    """Tests for encrypt_license and decrypt_license functions."""

    def test_roundtrip(self) -> None:
        """encrypt then decrypt should return original settings."""
        original = LicenseSettings(
            label="Enterprise",
            organization="Acme Corp",
            max_cores=16,
            features={"advanced": True},
        )
        key = b"test-encryption-key"

        encrypted = encrypt_license(original, key)
        decrypted = decrypt_license(encrypted, key)

        assert decrypted.label == original.label
        assert decrypted.organization == original.organization
        assert decrypted.max_cores == original.max_cores
        assert decrypted.features == original.features

    def test_wrong_key_fails(self) -> None:
        """decrypt with wrong key should fail."""
        settings = LicenseSettings(label="Test")
        encrypted = encrypt_license(settings, b"correct-key")

        with pytest.raises(LicenseDecryptionError):
            decrypt_license(encrypted, b"wrong-key")

    def test_encrypted_is_bytes(self) -> None:
        """encrypt_license should return bytes."""
        settings = LicenseSettings()
        encrypted = encrypt_license(settings, b"key")

        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 0

    def test_settings_with_all_fields(self) -> None:
        """Should handle settings with all fields set."""
        original = LicenseSettings(
            label="Enterprise",
            organization="Test Org",
            max_cores=32,
            max_memory_gb=128,
            max_throughput_mbps=10000,
            max_container_throughput_mbps=1000,
            max_nodes=100,
            expires_at="2027-01-01T00:00:00Z",
            issued_at="2025-01-01T00:00:00Z",
            signature="test-sig",
            features={"a": True, "b": "value", "c": 123},
            is_default=False,
        )
        key = b"full-test-key"

        encrypted = encrypt_license(original, key)
        decrypted = decrypt_license(encrypted, key)

        assert decrypted.label == original.label
        assert decrypted.organization == original.organization
        assert decrypted.max_cores == original.max_cores
        assert decrypted.max_memory_gb == original.max_memory_gb
        assert decrypted.max_throughput_mbps == original.max_throughput_mbps
        assert decrypted.max_container_throughput_mbps == original.max_container_throughput_mbps
        assert decrypted.max_nodes == original.max_nodes
        assert decrypted.expires_at == original.expires_at
        assert decrypted.issued_at == original.issued_at
        assert decrypted.signature == original.signature
        assert decrypted.features == original.features
        assert decrypted.is_default == original.is_default


class TestLicenseLoadCascade:
    """Tests for license loading cascade."""

    def test_explicit_path_takes_priority(self, tmp_path: Path) -> None:
        """Explicit path should be used even if env var is set."""
        # Create two license files
        settings1 = LicenseSettings(label="Explicit", is_default=False)
        settings2 = LicenseSettings(label="EnvVar", is_default=False)
        key = b"test"

        explicit_file = tmp_path / "explicit.enc"
        explicit_file.write_bytes(encrypt_license(settings1, key))

        env_file = tmp_path / "env.enc"
        env_file.write_bytes(encrypt_license(settings2, key))

        import os

        old_env = os.environ.get("HYPERI_LICENSE_PATH")
        try:
            os.environ["HYPERI_LICENSE_PATH"] = str(env_file)

            opts = LicenseOptions(
                license_path=explicit_file,
                verify_signature=False,
                custom_key=key,
            )
            license_obj = License.load(opts)

            assert license_obj.settings.label == "Explicit"
        finally:
            if old_env is not None:
                os.environ["HYPERI_LICENSE_PATH"] = old_env
            else:
                os.environ.pop("HYPERI_LICENSE_PATH", None)

    def test_env_var_used_when_no_explicit_path(self, tmp_path: Path) -> None:
        """HYPERI_LICENSE_PATH env var should be used."""
        settings = LicenseSettings(label="FromEnv", is_default=False)
        key = b"test"

        env_file = tmp_path / "env.enc"
        env_file.write_bytes(encrypt_license(settings, key))

        import os

        old_env = os.environ.get("HYPERI_LICENSE_PATH")
        try:
            os.environ["HYPERI_LICENSE_PATH"] = str(env_file)

            opts = LicenseOptions(
                verify_signature=False,
                custom_key=key,
            )
            license_obj = License.load(opts)

            assert license_obj.settings.label == "FromEnv"
        finally:
            if old_env is not None:
                os.environ["HYPERI_LICENSE_PATH"] = old_env
            else:
                os.environ.pop("HYPERI_LICENSE_PATH", None)

    def test_falls_back_to_default(self) -> None:
        """Should fall back to default when no file found."""
        import os

        old_env = os.environ.get("HYPERI_LICENSE_PATH")
        try:
            os.environ.pop("HYPERI_LICENSE_PATH", None)

            opts = LicenseOptions(verify_signature=False)
            license_obj = License.load(opts)

            assert license_obj.settings.is_default is True
            assert license_obj.source == LicenseSource.DEFAULT
        finally:
            if old_env is not None:
                os.environ["HYPERI_LICENSE_PATH"] = old_env
