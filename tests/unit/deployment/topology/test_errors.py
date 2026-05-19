"""Tests for topology errors module."""

from __future__ import annotations

import pytest

from hyperi_pylib.deployment.topology.errors import (
    TopologyError,
    TopologyValidationError,
    VersionResolutionError,
)


def test_topology_error_is_exception():
    assert issubclass(TopologyError, Exception)


def test_validation_error_is_topology_error():
    assert issubclass(TopologyValidationError, TopologyError)


def test_version_resolution_error_is_topology_error():
    assert issubclass(VersionResolutionError, TopologyError)


def test_validation_error_carries_path():
    err = TopologyValidationError("bad schema", path="topologies/x/topology.yaml")
    assert err.path == "topologies/x/topology.yaml"
    assert "topologies/x/topology.yaml" in str(err)


def test_version_resolution_error_carries_chart_and_range():
    err = VersionResolutionError(
        "no match",
        chart="dfe-loader",
        version_range="^1.18",
    )
    assert err.chart == "dfe-loader"
    assert err.version_range == "^1.18"
