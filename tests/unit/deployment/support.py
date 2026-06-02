# Project:   hyperi-pylib
# File:      tests/unit/deployment/support.py
# Purpose:   Shared Python deployment-contract fixture for generator tests
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Canonical Python ``DeploymentContract`` used by golden + validate tests."""

from __future__ import annotations

from hyperi_pylib.deployment import DeploymentContract, HealthContract, OciLabels


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
        entrypoint_args=["run"],
        oci_labels=OciLabels(title="dfe-api", description="DFE engine API"),
    )
