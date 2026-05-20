"""Tests for topology YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from hyperi_pylib.deployment.topology.errors import (
    TopologyError,
    TopologyValidationError,
)
from hyperi_pylib.deployment.topology.loader import load_topology
from hyperi_pylib.deployment.topology.model import DeploymentTopology

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_default():
    topo = load_topology(FIXTURES / "valid-default.yaml")
    assert isinstance(topo, DeploymentTopology)
    assert topo.metadata["name"] == "default"
    assert len(topo.spec.apps) == 3
    assert topo.spec.thirdParty[0].alias == "strimzi"
    assert topo.spec.argocd.syncWaves["dfe-loader"] == 0


def test_load_valid_minimal():
    topo = load_topology(FIXTURES / "valid-minimal.yaml")
    assert topo.metadata["name"] == "minimal"
    assert len(topo.spec.apps) == 2
    assert topo.spec.thirdParty == []


def test_load_invalid_no_apps_raises():
    with pytest.raises(TopologyValidationError) as ei:
        load_topology(FIXTURES / "invalid-no-apps.yaml")
    assert "apps" in str(ei.value).lower() or "thirdparty" in str(ei.value).lower()
    assert "invalid-no-apps.yaml" in str(ei.value)


def test_load_missing_file_raises():
    with pytest.raises(TopologyError) as ei:
        load_topology(FIXTURES / "does-not-exist.yaml")
    assert "not found" in str(ei.value).lower() or "no such" in str(ei.value).lower()


def test_load_directory_resolves_to_topology_yaml(tmp_path):
    d = tmp_path / "default"
    d.mkdir()
    (d / "topology.yaml").write_text((FIXTURES / "valid-minimal.yaml").read_text(), encoding="utf-8")
    topo = load_topology(d)
    assert topo.metadata["name"] == "minimal"


def test_load_malformed_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("this is: not [ valid: yaml", encoding="utf-8")
    with pytest.raises(TopologyValidationError):
        load_topology(bad)
