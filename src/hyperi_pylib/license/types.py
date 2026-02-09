# Project:   hyperi-pylib
# File:      src/hyperi_pylib/license/types.py
# Purpose:   License data structures
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""License data types and structures.

Direct port from hs-rustlib/src/license/types.rs for interoperability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass
class LicenseSettings:
    """License settings loaded from an encrypted license file.

    This structure contains all licensable parameters that can be
    dynamically configured via the license system.

    All fields match the Rust LicenseSettings struct for JSON interoperability.
    """

    # Human-readable license tier label (e.g., "Community", "Enterprise")
    label: str = "Community"

    # Organisation name the license is issued to
    organization: str | None = None

    # Maximum CPU cores allowed (None = unlimited)
    max_cores: int | None = None

    # Maximum memory in GB (None = unlimited)
    max_memory_gb: int | None = None

    # Maximum aggregate throughput in Mbps (None = unlimited)
    max_throughput_mbps: int | None = None

    # Maximum per-container throughput in Mbps (None = unlimited)
    max_container_throughput_mbps: int | None = None

    # Maximum number of nodes/instances (None = unlimited)
    max_nodes: int | None = None

    # License expiration timestamp (ISO 8601 format)
    # None means the license never expires
    expires_at: str | None = None

    # License issuance timestamp (ISO 8601 format)
    issued_at: str | None = None

    # Ed25519 signature over the license data (base64 encoded)
    # Used to verify the license was issued by HyperI
    signature: str | None = None

    # Feature flags - extensible key-value pairs for feature gating
    features: dict[str, Any] = field(default_factory=dict)

    # Whether this is a default/fallback license (not loaded from file)
    is_default: bool = False

    def has_feature(self, name: str) -> bool:
        """Check if a feature is enabled.

        Returns True if the feature exists and is truthy.
        """
        value = self.features.get(name)
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        return bool(value)

    def feature_string(self, name: str) -> str | None:
        """Get a feature value as a string."""
        value = self.features.get(name)
        if isinstance(value, str):
            return value
        return None

    def feature_int(self, name: str) -> int | None:
        """Get a feature value as an integer."""
        value = self.features.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None

    def is_expired(self) -> bool:
        """Check if the license has expired.

        Returns False if there's no expiration date.
        """
        if self.expires_at is None:
            return False

        # ISO 8601 string comparison works for UTC timestamps
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.expires_at < now

    def is_unlimited(self) -> bool:
        """Check if this is an unlimited license (enterprise tier)."""
        return self.max_cores is None and self.max_throughput_mbps is None and self.max_nodes is None

    def effective_cores(self, system_cores: int) -> int:
        """Get the effective core limit, with a fallback."""
        return self.max_cores if self.max_cores is not None else system_cores

    def effective_throughput_mbps(self, default: int) -> int:
        """Get the effective throughput limit in Mbps, with a fallback."""
        return self.max_throughput_mbps if self.max_throughput_mbps is not None else default

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialisation.

        Matches Rust serde behaviour: skip None values and empty dicts.
        """
        result: dict[str, Any] = {"label": self.label}

        if self.organization is not None:
            result["organization"] = self.organization
        if self.max_cores is not None:
            result["max_cores"] = self.max_cores
        if self.max_memory_gb is not None:
            result["max_memory_gb"] = self.max_memory_gb
        if self.max_throughput_mbps is not None:
            result["max_throughput_mbps"] = self.max_throughput_mbps
        if self.max_container_throughput_mbps is not None:
            result["max_container_throughput_mbps"] = self.max_container_throughput_mbps
        if self.max_nodes is not None:
            result["max_nodes"] = self.max_nodes
        if self.expires_at is not None:
            result["expires_at"] = self.expires_at
        if self.issued_at is not None:
            result["issued_at"] = self.issued_at
        if self.signature is not None:
            result["signature"] = self.signature
        if self.features:
            result["features"] = self.features
        if self.is_default:
            result["is_default"] = self.is_default

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LicenseSettings:
        """Create from dictionary (JSON deserialisation)."""
        return cls(
            label=data.get("label", "Community"),
            organization=data.get("organization"),
            max_cores=data.get("max_cores"),
            max_memory_gb=data.get("max_memory_gb"),
            max_throughput_mbps=data.get("max_throughput_mbps"),
            max_container_throughput_mbps=data.get("max_container_throughput_mbps"),
            max_nodes=data.get("max_nodes"),
            expires_at=data.get("expires_at"),
            issued_at=data.get("issued_at"),
            signature=data.get("signature"),
            features=data.get("features", {}),
            is_default=data.get("is_default", False),
        )


@dataclass
class LicenseOptions:
    """Options for license initialisation."""

    # Explicit path to the license file
    # If set, only this path is checked
    license_path: Path | None = None

    # URL to fetch the license from
    # Only used if license_path is not set and no local file is found
    license_url: str | None = None

    # Whether to verify the license signature
    # Set to False for development/testing only
    verify_signature: bool = True

    # Whether to allow expired licenses (with a warning)
    # Useful for grace periods
    allow_expired: bool = False

    # Custom decryption key (overrides compiled-in key)
    # Used for testing or multi-tenant deployments
    custom_key: bytes | None = None


class LicenseSource(Enum):
    """Where the license was loaded from."""

    FILE = "file"
    URL = "url"
    DEFAULT = "default"


@dataclass
class LicenseSourceInfo:
    """Detailed information about license source."""

    source: LicenseSource
    path: Path | None = None
    url: str | None = None
