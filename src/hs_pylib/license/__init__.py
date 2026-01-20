# Project:   hs-pylib
# File:      src/hs_pylib/license/__init__.py
# Purpose:   License management with encrypted license files
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2026 HyperSec

"""License management with encrypted license files and anti-tampering.

This module provides a secure license system that:
- Loads encrypted license files (AES-256-GCM)
- Supports local files and HTTPS URLs
- Falls back to compiled-in defaults
- Verifies Ed25519 signatures
- Includes integrity checks

Direct port from hs-rustlib for cross-language interoperability.
License files encrypted by Rust can be decrypted by Python and vice versa.

Quick Start
-----------

.. code-block:: python

    from hs_pylib import license

    # Initialise with default search paths
    license.init()

    # Access license settings
    settings = license.get()
    print(f"License tier: {settings.label}")
    print(f"Max cores: {settings.max_cores}")

    # Check features
    if settings.has_feature("advanced_analytics"):
        # Enable advanced analytics
        pass

License File Format
-------------------

License files are encrypted JSON with the following structure:

.. code-block:: json

    {
      "label": "Enterprise",
      "organization": "Acme Corp",
      "max_cores": null,
      "max_throughput_mbps": 10000,
      "expires_at": "2027-01-01T00:00:00Z",
      "signature": "base64-ed25519-signature",
      "features": {
        "advanced_analytics": true,
        "custom_rules": true
      }
    }

The JSON is encrypted with AES-256-GCM before distribution.

Security Model
--------------

The protection aims to make casual tampering difficult:
- AES-256-GCM encryption for license files
- Ed25519 signature verification
- Runtime integrity checks (SHA-256)

**IMPORTANT:** Python source code cannot be obfuscated like Rust binaries.
Production deployments MUST use Nuitka compilation for meaningful protection
of the encryption key and default values.

A determined attacker with debugging tools can bypass these protections.
The goal is economic: make tampering cost more than a license.

Dependencies
------------

This module requires the ``cryptography`` library:

.. code-block:: bash

    pip install hs-pylib[license]

Or:

.. code-block:: bash

    pip install cryptography
"""

from __future__ import annotations

# Error types
from .error import (
    LicenseAlreadyInitializedError,
    LicenseDecryptionError,
    LicenseEncryptionError,
    LicenseError,
    LicenseExpiredError,
    LicenseFetchError,
    LicenseIntegrityError,
    LicenseLoadError,
    LicenseNotInitializedError,
    LicenseParseError,
    LicenseSignatureError,
)

# Manager and singleton API
from .manager import (
    License,
    decrypt_license,
    encrypt_license,
    get,
    get_license,
    has_feature,
    init,
    init_default,
    is_default,
    reset,
    try_get,
    verify_integrity,
)

# Types
from .types import (
    LicenseOptions,
    LicenseSettings,
    LicenseSource,
    LicenseSourceInfo,
)

__all__ = [
    # Types
    "LicenseSettings",
    "LicenseOptions",
    "LicenseSource",
    "LicenseSourceInfo",
    "License",
    # Singleton API
    "init",
    "init_default",
    "reset",
    "get",
    "try_get",
    "get_license",
    "verify_integrity",
    "is_default",
    "has_feature",
    # Utility functions
    "encrypt_license",
    "decrypt_license",
    # Errors
    "LicenseError",
    "LicenseLoadError",
    "LicenseFetchError",
    "LicenseDecryptionError",
    "LicenseEncryptionError",
    "LicenseParseError",
    "LicenseSignatureError",
    "LicenseExpiredError",
    "LicenseIntegrityError",
    "LicenseNotInitializedError",
    "LicenseAlreadyInitializedError",
]
