# Project:   hyperi-pylib
# File:      deployment/topology/errors.py
# Purpose:   Typed exceptions for the topology subsystem
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""Topology subsystem exceptions."""

from __future__ import annotations


class TopologyError(Exception):
    """Base error for the deployment-topology subsystem."""


class TopologyValidationError(TopologyError):
    """Raised when topology.yaml fails schema validation."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        self.path = path
        if path is not None:
            super().__init__(f"{path}: {message}")
        else:
            super().__init__(message)


class VersionResolutionError(TopologyError):
    """Raised when a semver range cannot be resolved against OCI."""

    def __init__(
        self,
        message: str,
        *,
        chart: str,
        version_range: str,
    ) -> None:
        self.chart = chart
        self.version_range = version_range
        super().__init__(f"version resolution failed for {chart} ({version_range}): {message}")
