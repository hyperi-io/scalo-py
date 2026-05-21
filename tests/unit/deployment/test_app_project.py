# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_app_project.py
# Purpose:   Tests for ArgoCD AppProject generator
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""Tests for ArgoCD AppProject generator."""

from __future__ import annotations

from hyperi_pylib.deployment.app_project import (
    AppProjectContract,
    AppProjectDestination,
    generate_argocd_app_project,
)


def _sample_project() -> AppProjectContract:
    return AppProjectContract(
        name="hyperi-platform",
        description="HyperI platform team",
        source_repos=[
            "https://github.com/hyperi-io/gitops",
            "oci://ghcr.io/hyperi-io/helm-charts",
        ],
        destinations=[
            AppProjectDestination(
                server="https://kubernetes.default.svc",
                namespace="hyperi-dfe",
            )
        ],
        cluster_resource_allow=["kafka.strimzi.io:KafkaTopic"],
        namespace_resource_allow=["*:*"],
    )


def test_generate_produces_appproject_yaml():
    yaml = generate_argocd_app_project(_sample_project())
    assert "kind: AppProject" in yaml
    assert "name: hyperi-platform" in yaml


def test_includes_source_repos():
    yaml = generate_argocd_app_project(_sample_project())
    assert "https://github.com/hyperi-io/gitops" in yaml
    assert "oci://ghcr.io/hyperi-io/helm-charts" in yaml


def test_includes_destinations():
    yaml = generate_argocd_app_project(_sample_project())
    assert "server: https://kubernetes.default.svc" in yaml
    assert "namespace: hyperi-dfe" in yaml


def test_cluster_resource_allow_splits_group_kind():
    yaml = generate_argocd_app_project(_sample_project())
    assert "group: kafka.strimzi.io" in yaml
    assert "kind: KafkaTopic" in yaml


def test_star_kind_split_handles_namespace_wildcards():
    yaml = generate_argocd_app_project(_sample_project())
    assert "group: *" in yaml
    assert "kind: *" in yaml


def test_default_contract_yields_unrestricted_project():
    default = AppProjectContract()
    assert default.source_repos == ["*"]
    assert default.cluster_resource_allow == ["*:*"]


def test_description_with_colon_is_quoted():
    project = _sample_project()
    project.description = "Team: platform"
    yaml = generate_argocd_app_project(project)
    assert 'description: "Team: platform"' in yaml


def test_empty_description_is_quoted():
    project = _sample_project()
    project.description = ""
    yaml = generate_argocd_app_project(project)
    assert 'description: ""' in yaml


def test_multiple_destinations_all_present():
    project = _sample_project()
    project.destinations = [
        AppProjectDestination(server="https://cluster-a.example", namespace="ns-a"),
        AppProjectDestination(server="https://cluster-b.example", namespace="ns-b"),
    ]
    yaml = generate_argocd_app_project(project)
    assert "https://cluster-a.example" in yaml
    assert "https://cluster-b.example" in yaml
    assert "ns-a" in yaml
    assert "ns-b" in yaml
