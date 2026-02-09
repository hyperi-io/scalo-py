# Project:   hyperi-pylib
# File:      src/hyperi_pylib/license/defaults.py
# Purpose:   Default license settings
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Default license settings.

These defaults are used when no license file is available.

SECURITY NOTE:
--------------
Unlike the Rust implementation which uses compile-time obfuscation (obfstr!),
Python source code cannot be meaningfully obfuscated at the source level.

**Production deployments MUST use Nuitka compilation** for any protection
of these values. The Nuitka compiler will:
- Compile Python to C and then to machine code
- Embed strings in the binary (not trivially extractable)
- Apply additional obfuscation options if configured

Without Nuitka compilation, these values are visible in plain text.
This is acceptable for development but NOT for production distribution.

Direct port from hs-rustlib/src/license/defaults.rs for interoperability.
"""

from __future__ import annotations

from .types import LicenseSettings

# The encryption key used to decrypt license files.
# This key MUST match the Rust implementation exactly for interoperability.
#
# SECURITY: Change this key before production deployment.
# This value is plaintext in Python source - use Nuitka for protection.
_DEFAULT_KEY = b"hyperi-default-license-key-v1-change-me"


def get_decryption_key() -> bytes:
    """Get the default decryption key.

    Returns the compiled-in key used to decrypt license files.
    For testing or multi-tenant deployments, use LicenseOptions.custom_key instead.
    """
    return _DEFAULT_KEY


def get_default_settings() -> LicenseSettings:
    """Get the default license settings (Community tier).

    These settings are used when:
    - No license file is found
    - License file decryption fails
    - License has expired (fallback)

    Returns:
        LicenseSettings with Community tier limits.
    """
    return LicenseSettings(
        label="Community",
        organization=None,
        # Resource limits for community tier
        max_cores=4,
        max_memory_gb=8,
        max_throughput_mbps=100,
        max_container_throughput_mbps=25,
        max_nodes=1,
        # No expiry for defaults (perpetual community license)
        expires_at=None,
        issued_at=None,
        # No signature for compiled defaults
        signature=None,
        # Empty feature flags
        features={},
        # Mark as default/fallback
        is_default=True,
    )


def get_test_enterprise_settings() -> LicenseSettings:
    """Get enterprise settings for testing/development.

    NOT for production use - only for unit tests and development.

    Returns:
        LicenseSettings with unlimited Enterprise tier.
    """
    return LicenseSettings(
        label="Enterprise",
        organization="Test Organization",
        # Unlimited
        max_cores=None,
        max_memory_gb=None,
        max_throughput_mbps=None,
        max_container_throughput_mbps=None,
        max_nodes=None,
        # No expiry
        expires_at=None,
        issued_at="2025-01-01T00:00:00Z",
        # No signature for test settings
        signature=None,
        # Enterprise features
        features={
            "advanced_analytics": True,
            "custom_rules": True,
            "multi_tenant": True,
        },
        is_default=False,
    )
