"""Tests for topology Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hyperi_pylib.deployment.topology.model import (
    AppEntry,
    ArgocdHints,
    DeploymentTopology,
    GlueEntry,
    ThirdPartyEntry,
    TopologySpec,
    UmbrellaMeta,
)


def test_app_entry_minimal():
    entry = AppEntry(name="dfe-loader", version="^1.18")
    assert entry.name == "dfe-loader"
    assert entry.version == "^1.18"
    assert entry.enabled is True
    assert entry.condition == "dfe-loader.enabled"
    assert entry.alias is None


def test_app_entry_with_alias():
    entry = AppEntry(name="dfe-loader", version="^1.18", alias="loader")
    assert entry.alias == "loader"
    assert entry.condition == "loader.enabled"


def test_app_entry_disabled():
    entry = AppEntry(name="dfe-fetcher", version="^1.2", enabled=False)
    assert entry.enabled is False


def test_app_entry_rejects_uppercase_name():
    with pytest.raises(ValidationError) as ei:
        AppEntry(name="DFE-Loader", version="^1.0")
    assert "lowercase" in str(ei.value).lower() or "pattern" in str(ei.value).lower()


def test_app_entry_rejects_empty_version():
    with pytest.raises(ValidationError):
        AppEntry(name="dfe-loader", version="")


def test_third_party_entry_minimal():
    entry = ThirdPartyEntry(
        name="strimzi-kafka-operator",
        repository="oci://quay.io/strimzi-helm",
        version="0.45.0",
    )
    assert entry.name == "strimzi-kafka-operator"
    assert entry.repository == "oci://quay.io/strimzi-helm"
    assert entry.version == "0.45.0"
    assert entry.enabled is True


def test_third_party_entry_with_alias():
    entry = ThirdPartyEntry(
        name="strimzi-kafka-operator",
        repository="oci://quay.io/strimzi-helm",
        version="0.45.0",
        alias="strimzi",
    )
    assert entry.alias == "strimzi"


def test_glue_entry():
    glue = GlueEntry(name="kafka-cluster", file="glue/kafka-cluster.yaml")
    assert glue.name == "kafka-cluster"
    assert glue.file == "glue/kafka-cluster.yaml"


def test_glue_entry_rejects_absolute_path():
    with pytest.raises(ValidationError) as ei:
        GlueEntry(name="kafka", file="/abs/path.yaml")
    assert "relative" in str(ei.value).lower() or "must not" in str(ei.value).lower()


def test_umbrella_meta_required_fields():
    with pytest.raises(ValidationError):
        UmbrellaMeta()  # type: ignore[call-arg]


def test_umbrella_meta_full():
    meta = UmbrellaMeta(
        name="hyperi-deployment-default",
        description="default rollout",
        appVersion="1.0",
    )
    assert meta.name == "hyperi-deployment-default"
    assert meta.appVersion == "1.0"


def test_umbrella_meta_rejects_uppercase_name():
    with pytest.raises(ValidationError):
        UmbrellaMeta(
            name="Hyperi-Deployment",
            description="x",
            appVersion="1.0",
        )


def test_argocd_hints_defaults():
    hints = ArgocdHints()
    assert hints.appOfApps is False
    assert hints.appProject == "default"
    assert hints.syncWaves == {}


def test_argocd_hints_with_waves():
    hints = ArgocdHints(
        appOfApps=True,
        appProject="hyperi-platform",
        syncWaves={
            "strimzi-kafka-operator": -20,
            "dfe-loader": 0,
        },
    )
    assert hints.appOfApps is True
    assert hints.syncWaves["strimzi-kafka-operator"] == -20


def test_topology_spec_requires_umbrella():
    with pytest.raises(ValidationError):
        TopologySpec()  # type: ignore[call-arg]


def test_topology_spec_requires_at_least_one_app():
    with pytest.raises(ValidationError) as ei:
        TopologySpec(
            umbrella=UmbrellaMeta(name="hyperi-deployment-x", description="x", appVersion="1.0"),
        )
    assert "apps" in str(ei.value).lower() or "thirdParty" in str(ei.value)


def test_topology_spec_full():
    spec = TopologySpec(
        umbrella=UmbrellaMeta(
            name="hyperi-deployment-default",
            description="default rollout",
            appVersion="1.0",
        ),
        apps=[
            AppEntry(name="dfe-loader", version="^1.18"),
            AppEntry(name="dfe-receiver", version="^1.15"),
        ],
        thirdParty=[
            ThirdPartyEntry(
                name="strimzi-kafka-operator",
                repository="oci://quay.io/strimzi-helm",
                version="0.45.0",
            ),
        ],
        glue=[GlueEntry(name="kafka-cluster", file="glue/kafka-cluster.yaml")],
        argocd=ArgocdHints(appOfApps=True, appProject="hyperi-platform"),
    )
    assert len(spec.apps) == 2
    assert spec.argocd.appProject == "hyperi-platform"


def test_topology_spec_rejects_duplicate_app_names():
    with pytest.raises(ValidationError) as ei:
        TopologySpec(
            umbrella=UmbrellaMeta(name="hyperi-deployment-x", description="x", appVersion="1.0"),
            apps=[
                AppEntry(name="dfe-loader", version="^1.18"),
                AppEntry(name="dfe-loader", version="^1.19"),
            ],
        )
    assert "duplicate" in str(ei.value).lower()


def test_deployment_topology_minimal():
    topo = DeploymentTopology(
        metadata={"name": "default"},
        spec=TopologySpec(
            umbrella=UmbrellaMeta(name="hyperi-deployment-default", description="x", appVersion="1.0"),
            apps=[AppEntry(name="dfe-loader", version="^1.18")],
        ),
    )
    assert topo.apiVersion == "hyperi.io/v1"
    assert topo.kind == "DeploymentTopology"
    assert topo.metadata["name"] == "default"


def test_deployment_topology_rejects_wrong_kind():
    with pytest.raises(ValidationError):
        DeploymentTopology(
            kind="WrongKind",  # type: ignore[arg-type]
            spec=TopologySpec(
                umbrella=UmbrellaMeta(name="hyperi-deployment-x", description="x", appVersion="1.0"),
                apps=[AppEntry(name="dfe-loader", version="^1.18")],
            ),
        )


def test_deployment_topology_requires_metadata_name():
    with pytest.raises(ValidationError) as ei:
        DeploymentTopology(
            metadata={},
            spec=TopologySpec(
                umbrella=UmbrellaMeta(name="hyperi-deployment-x", description="x", appVersion="1.0"),
                apps=[AppEntry(name="dfe-loader", version="^1.18")],
            ),
        )
    assert "metadata.name" in str(ei.value) or "name" in str(ei.value)
