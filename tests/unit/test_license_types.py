# Project:   hs-pylib
# File:      tests/unit/test_license_types.py
# Purpose:   Unit tests for license types
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2026 HyperSec

"""Unit tests for hs_pylib.license.types module."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from hs_pylib.license.types import (
    LicenseOptions,
    LicenseSettings,
    LicenseSource,
    LicenseSourceInfo,
)


class TestLicenseSettings:
    """Tests for LicenseSettings dataclass."""

    def test_default_values(self) -> None:
        """Default settings should have Community label."""
        settings = LicenseSettings()
        assert settings.label == "Community"
        assert settings.organization is None
        assert settings.max_cores is None
        assert settings.is_default is False

    def test_has_feature_true(self) -> None:
        """has_feature should return True for enabled features."""
        settings = LicenseSettings(features={"test_feature": True})
        assert settings.has_feature("test_feature") is True

    def test_has_feature_false(self) -> None:
        """has_feature should return False for disabled features."""
        settings = LicenseSettings(features={"disabled": False})
        assert settings.has_feature("disabled") is False

    def test_has_feature_missing(self) -> None:
        """has_feature should return False for missing features."""
        settings = LicenseSettings()
        assert settings.has_feature("nonexistent") is False

    def test_feature_string(self) -> None:
        """feature_string should return string values."""
        settings = LicenseSettings(features={"mode": "advanced"})
        assert settings.feature_string("mode") == "advanced"
        assert settings.feature_string("missing") is None
        assert settings.feature_string("bool") is None

    def test_feature_int(self) -> None:
        """feature_int should return integer values."""
        settings = LicenseSettings(features={"limit": 100})
        assert settings.feature_int("limit") == 100
        assert settings.feature_int("missing") is None

    def test_feature_int_excludes_bool(self) -> None:
        """feature_int should not return bool as int."""
        settings = LicenseSettings(features={"flag": True})
        assert settings.feature_int("flag") is None

    def test_is_expired_no_expiry(self) -> None:
        """is_expired should return False when no expiry date."""
        settings = LicenseSettings()
        assert settings.is_expired() is False

    def test_is_expired_future_date(self) -> None:
        """is_expired should return False for future dates."""
        settings = LicenseSettings(expires_at="2099-12-31T23:59:59Z")
        assert settings.is_expired() is False

    def test_is_expired_past_date(self) -> None:
        """is_expired should return True for past dates."""
        settings = LicenseSettings(expires_at="2020-01-01T00:00:00Z")
        assert settings.is_expired() is True

    def test_is_unlimited_with_limits(self) -> None:
        """is_unlimited should return False when limits are set."""
        settings = LicenseSettings(max_cores=4)
        assert settings.is_unlimited() is False

    def test_is_unlimited_without_limits(self) -> None:
        """is_unlimited should return True when no limits."""
        settings = LicenseSettings(
            max_cores=None,
            max_throughput_mbps=None,
            max_nodes=None,
        )
        assert settings.is_unlimited() is True

    def test_effective_cores_with_limit(self) -> None:
        """effective_cores should return limit when set."""
        settings = LicenseSettings(max_cores=4)
        assert settings.effective_cores(16) == 4

    def test_effective_cores_without_limit(self) -> None:
        """effective_cores should return system cores when no limit."""
        settings = LicenseSettings(max_cores=None)
        assert settings.effective_cores(16) == 16

    def test_effective_throughput_mbps_with_limit(self) -> None:
        """effective_throughput_mbps should return limit when set."""
        settings = LicenseSettings(max_throughput_mbps=100)
        assert settings.effective_throughput_mbps(1000) == 100

    def test_effective_throughput_mbps_without_limit(self) -> None:
        """effective_throughput_mbps should return default when no limit."""
        settings = LicenseSettings(max_throughput_mbps=None)
        assert settings.effective_throughput_mbps(1000) == 1000

    def test_to_dict_minimal(self) -> None:
        """to_dict should include only set fields."""
        settings = LicenseSettings(label="Test")
        data = settings.to_dict()
        assert data == {"label": "Test"}
        assert "organization" not in data
        assert "features" not in data

    def test_to_dict_full(self) -> None:
        """to_dict should include all set fields."""
        settings = LicenseSettings(
            label="Enterprise",
            organization="Acme Corp",
            max_cores=8,
            features={"advanced": True},
            is_default=True,
        )
        data = settings.to_dict()
        assert data["label"] == "Enterprise"
        assert data["organization"] == "Acme Corp"
        assert data["max_cores"] == 8
        assert data["features"] == {"advanced": True}
        assert data["is_default"] is True

    def test_from_dict_minimal(self) -> None:
        """from_dict should handle minimal data."""
        data = {"label": "Test"}
        settings = LicenseSettings.from_dict(data)
        assert settings.label == "Test"
        assert settings.organization is None
        assert settings.features == {}

    def test_from_dict_full(self) -> None:
        """from_dict should handle full data."""
        data = {
            "label": "Enterprise",
            "organization": "Acme Corp",
            "max_cores": 8,
            "max_memory_gb": 64,
            "max_throughput_mbps": 10000,
            "max_container_throughput_mbps": 1000,
            "max_nodes": 100,
            "expires_at": "2027-01-01T00:00:00Z",
            "issued_at": "2025-01-01T00:00:00Z",
            "signature": "base64signature",
            "features": {"advanced": True},
            "is_default": False,
        }
        settings = LicenseSettings.from_dict(data)
        assert settings.label == "Enterprise"
        assert settings.organization == "Acme Corp"
        assert settings.max_cores == 8
        assert settings.max_memory_gb == 64
        assert settings.max_throughput_mbps == 10000
        assert settings.max_container_throughput_mbps == 1000
        assert settings.max_nodes == 100
        assert settings.expires_at == "2027-01-01T00:00:00Z"
        assert settings.issued_at == "2025-01-01T00:00:00Z"
        assert settings.signature == "base64signature"
        assert settings.features == {"advanced": True}
        assert settings.is_default is False

    def test_roundtrip_serialization(self) -> None:
        """to_dict and from_dict should be inverse operations."""
        original = LicenseSettings(
            label="Enterprise",
            organization="Test Org",
            max_cores=16,
            features={"feature1": True, "feature2": "value"},
        )
        data = original.to_dict()
        restored = LicenseSettings.from_dict(data)
        assert restored.label == original.label
        assert restored.organization == original.organization
        assert restored.max_cores == original.max_cores
        assert restored.features == original.features

    def test_json_serialization(self) -> None:
        """Settings should serialize to valid JSON."""
        settings = LicenseSettings(
            label="Test",
            max_cores=4,
            features={"enabled": True},
        )
        json_str = json.dumps(settings.to_dict())
        parsed = json.loads(json_str)
        assert parsed["label"] == "Test"
        assert parsed["max_cores"] == 4


class TestLicenseOptions:
    """Tests for LicenseOptions dataclass."""

    def test_default_values(self) -> None:
        """Default options should have sensible defaults."""
        opts = LicenseOptions()
        assert opts.license_path is None
        assert opts.license_url is None
        assert opts.verify_signature is True
        assert opts.allow_expired is False
        assert opts.custom_key is None


class TestLicenseSource:
    """Tests for LicenseSource enum."""

    def test_values(self) -> None:
        """LicenseSource should have expected values."""
        assert LicenseSource.FILE.value == "file"
        assert LicenseSource.URL.value == "url"
        assert LicenseSource.DEFAULT.value == "default"


class TestLicenseSourceInfo:
    """Tests for LicenseSourceInfo dataclass."""

    def test_file_source(self) -> None:
        """File source should have path."""
        from pathlib import Path

        info = LicenseSourceInfo(
            source=LicenseSource.FILE,
            path=Path("/etc/hypersec/license.enc"),
        )
        assert info.source == LicenseSource.FILE
        assert info.path == Path("/etc/hypersec/license.enc")
        assert info.url is None

    def test_url_source(self) -> None:
        """URL source should have url."""
        info = LicenseSourceInfo(
            source=LicenseSource.URL,
            url="https://example.com/license.enc",
        )
        assert info.source == LicenseSource.URL
        assert info.url == "https://example.com/license.enc"
        assert info.path is None

    def test_default_source(self) -> None:
        """Default source should have neither path nor url."""
        info = LicenseSourceInfo(source=LicenseSource.DEFAULT)
        assert info.source == LicenseSource.DEFAULT
        assert info.path is None
        assert info.url is None
