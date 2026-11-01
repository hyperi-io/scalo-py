# Project:   scalo
# File:      tests/unit/deployment/support.py
# Purpose:   Shared Python deployment-contract fixture for generator tests
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Canonical Python ``DeploymentContract`` used by golden + validate tests."""

from __future__ import annotations

from scalo.deployment import (
    DEFAULT_DISTRO_CODENAME,
    AptRepoContract,
    DeploymentContract,
    HealthContract,
    NativeDepsContract,
    OciLabels,
)

VENDOR_FINGERPRINT = "0123456789ABCDEF0123456789ABCDEF01234567"


def py_contract() -> DeploymentContract:
    """A representative Python app contract (dfe-api-like, deterministic)."""
    return DeploymentContract(
        app_name="dfe-api",
        binary_name="dfe-api",
        description="DFE engine API",
        metrics_port=8000,
        health=HealthContract(),
        env_prefix="DFE",
        metric_prefix="engine",
        config_mount_path="/etc/dfe/api.yaml",
        image_registry="ghcr.io/hyperi-io",
        entrypoint_args=["run"],
        oci_labels=OciLabels(title="dfe-api", description="DFE engine API"),
    )


def deps_with_repo(base_image: str, *, distro_codename: str = DEFAULT_DISTRO_CODENAME) -> NativeDepsContract:
    """A distro package plus a signed vendor repo with no codename of its own: every step of the apt block."""
    deps = NativeDepsContract.for_scalo_features(["directory-config-git"], base_image, distro_codename=distro_codename)
    deps.apt_repos.append(
        AptRepoContract(
            key_url="https://apt.vendor.example/archive.key",
            keyring="/usr/share/keyrings/vendor.gpg",
            url="https://apt.vendor.example/deb",
            key_fingerprint=VENDOR_FINGERPRINT,
            packages=["vendor-runtime"],
        )
    )
    return deps
