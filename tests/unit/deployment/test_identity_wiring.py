# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_identity_wiring.py
# Purpose:   Verify ContractIdentity wiring into the five deployment generators
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Wiring tests for Contract Identity v1.

For each of the five generators (`generate_runtime_stage`,
`generate_container_manifest`, `generate_dockerfile`, `generate_chart`,
`generate_argocd_application`):

- ``identity=None`` -> output byte-for-byte unchanged from the
  pre-identity baseline (opt-in safety).
- ``identity=<id>`` -> the three ``io.hyperi.contract.*`` keys land in
  the expected location.

A cross-surface grep invariant ensures every artefact carries the
canonical key prefix when identity is supplied.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from hyperi_pylib.deployment import (
    ArgocdConfig,
    DeploymentContract,
    HealthContract,
    ImageProfile,
    KedaContract,
    NativeDepsContract,
    OciLabels,
    SecretEnvContract,
    SecretGroupContract,
    generate_argocd_application,
    generate_chart,
    generate_container_manifest,
    generate_dockerfile,
    generate_runtime_stage,
)
from hyperi_pylib.deployment.contract_identity import ContractIdentity

VALID_SHA = "0123456789abcdef0123456789abcdef01234567"
VALID_REF = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"


def _make_identity() -> ContractIdentity:
    return ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)


def _make_contract() -> DeploymentContract:
    return DeploymentContract(
        app_name="dfe-loader",
        binary_name="dfe-loader",
        description="High-performance Kafka to ClickHouse data loader",
        metrics_port=9090,
        health=HealthContract(),
        env_prefix="DFE_LOADER",
        metric_prefix="loader",
        config_mount_path="/etc/dfe/loader.yaml",
        image_registry="ghcr.io/hyperi-io",
        extra_ports=[],
        entrypoint_args=["--config", "/etc/dfe/loader.yaml"],
        secrets=[
            SecretGroupContract(
                group_name="kafka",
                env_vars=[
                    SecretEnvContract(
                        env_var="DFE_LOADER__KAFKA__USERNAME",
                        key_name="username",
                        secret_key="kafka-username",
                    ),
                ],
            ),
        ],
        depends_on=["kafka"],
        keda=KedaContract(),
        base_image="ubuntu:24.04",
        native_deps=NativeDepsContract(),
        image_profile=ImageProfile.PRODUCTION,
        oci_labels=OciLabels(),
        schema_version=2,
    )


def _make_argo() -> ArgocdConfig:
    return ArgocdConfig(
        repo_url="https://github.com/hyperi-io/dfe-loader",
        target_revision="main",
        chart_path="charts/dfe-loader",
    )


# ---------------------------------------------------------------------------
# generate_runtime_stage
# ---------------------------------------------------------------------------


def test_runtime_stage_identity_none_unchanged_from_baseline() -> None:
    c = _make_contract()
    # Baseline: explicit None must produce the same string as no-arg call
    assert generate_runtime_stage(c, identity=None) == generate_runtime_stage(c)


def test_runtime_stage_identity_none_has_no_contract_keys() -> None:
    out = generate_runtime_stage(_make_contract(), identity=None)
    assert "io.hyperi.contract" not in out


def test_runtime_stage_with_identity_emits_three_labels() -> None:
    out = generate_runtime_stage(_make_contract(), identity=_make_identity())
    assert f'LABEL io.hyperi.contract.version="v1"' in out
    assert f'LABEL io.hyperi.contract.source-commit="{VALID_SHA}"' in out
    assert f'LABEL io.hyperi.contract.image-ref="{VALID_REF}"' in out


def test_runtime_stage_with_identity_inserts_after_profile_label() -> None:
    out = generate_runtime_stage(_make_contract(), identity=_make_identity())
    profile_pos = out.index("LABEL io.hyperi.profile=")
    version_pos = out.index("LABEL io.hyperi.contract.version=")
    assert profile_pos < version_pos, "contract labels must appear after profile label"


# ---------------------------------------------------------------------------
# generate_container_manifest
# ---------------------------------------------------------------------------


def test_container_manifest_identity_none_unchanged() -> None:
    c = _make_contract()
    assert generate_container_manifest(c, identity=None) == generate_container_manifest(c)


def test_container_manifest_identity_none_has_no_contract_keys() -> None:
    out = generate_container_manifest(_make_contract(), identity=None)
    assert "io.hyperi.contract" not in out


def test_container_manifest_with_identity_emits_three_labels() -> None:
    out = generate_container_manifest(_make_contract(), identity=_make_identity())
    parsed = json.loads(out)
    labels = parsed["labels"]
    assert labels["io.hyperi.contract.version"] == "v1"
    assert labels["io.hyperi.contract.source-commit"] == VALID_SHA
    assert labels["io.hyperi.contract.image-ref"] == VALID_REF


# ---------------------------------------------------------------------------
# generate_dockerfile (passes through to runtime stage path)
# ---------------------------------------------------------------------------


def test_dockerfile_identity_none_unchanged() -> None:
    c = _make_contract()
    assert generate_dockerfile(c, identity=None) == generate_dockerfile(c)


def test_dockerfile_identity_none_has_no_contract_keys() -> None:
    out = generate_dockerfile(_make_contract(), identity=None)
    assert "io.hyperi.contract" not in out


def test_dockerfile_with_identity_emits_three_labels() -> None:
    out = generate_dockerfile(_make_contract(), identity=_make_identity())
    assert f'LABEL io.hyperi.contract.version="v1"' in out
    assert f'LABEL io.hyperi.contract.source-commit="{VALID_SHA}"' in out
    assert f'LABEL io.hyperi.contract.image-ref="{VALID_REF}"' in out


# ---------------------------------------------------------------------------
# generate_chart (writes Chart.yaml + values.yaml + templates)
# ---------------------------------------------------------------------------


def test_chart_identity_none_no_annotations_block_in_chart_yaml(tmp_path: Path) -> None:
    generate_chart(_make_contract(), tmp_path, identity=None)
    chart_text = (tmp_path / "Chart.yaml").read_text(encoding="utf-8")
    assert "io.hyperi.contract" not in chart_text


def test_chart_with_identity_emits_annotations_block(tmp_path: Path) -> None:
    generate_chart(_make_contract(), tmp_path, identity=_make_identity())
    chart_text = (tmp_path / "Chart.yaml").read_text(encoding="utf-8")
    chart = yaml.safe_load(chart_text)
    annotations = chart["annotations"]
    assert annotations["io.hyperi.contract.version"] == "v1"
    assert annotations["io.hyperi.contract.source-commit"] == VALID_SHA
    assert annotations["io.hyperi.contract.image-ref"] == VALID_REF


def test_chart_identity_none_byte_unchanged(tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    generate_chart(_make_contract(), out_a, identity=None)
    generate_chart(_make_contract(), out_b)
    assert (out_a / "Chart.yaml").read_text(encoding="utf-8") == (out_b / "Chart.yaml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# generate_argocd_application
# ---------------------------------------------------------------------------


def test_argocd_identity_none_unchanged() -> None:
    c = _make_contract()
    argo = _make_argo()
    assert generate_argocd_application(c, argo, identity=None) == generate_argocd_application(c, argo)


def test_argocd_identity_none_has_no_contract_keys() -> None:
    out = generate_argocd_application(_make_contract(), _make_argo(), identity=None)
    assert "io.hyperi.contract" not in out


def test_argocd_with_identity_emits_three_annotations_alongside_sync_wave() -> None:
    out = generate_argocd_application(_make_contract(), _make_argo(), identity=_make_identity())
    parsed = yaml.safe_load(out)
    annotations = parsed["metadata"]["annotations"]
    assert annotations["argocd.argoproj.io/sync-wave"] == "0"
    assert annotations["io.hyperi.contract.version"] == "v1"
    assert annotations["io.hyperi.contract.source-commit"] == VALID_SHA
    assert annotations["io.hyperi.contract.image-ref"] == VALID_REF


# ---------------------------------------------------------------------------
# Cross-surface grep invariant
# ---------------------------------------------------------------------------


def test_all_surfaces_grep_for_io_hyperi_contract(tmp_path: Path) -> None:
    c = _make_contract()
    argo = _make_argo()
    ident = _make_identity()

    pattern = re.compile(r"io\.hyperi\.contract")

    surfaces = {
        "dockerfile": generate_dockerfile(c, identity=ident),
        "runtime_stage": generate_runtime_stage(c, identity=ident),
        "container_manifest": generate_container_manifest(c, identity=ident),
        "argocd_application": generate_argocd_application(c, argo, identity=ident),
    }
    for name, text in surfaces.items():
        # Each surface must carry all three keys.
        assert len(pattern.findall(text)) >= 3, (
            f"{name}: expected >=3 occurrences of io.hyperi.contract, got {len(pattern.findall(text))}"
        )

    # Chart.yaml separately (writes to disk)
    chart_dir = tmp_path / "chart"
    generate_chart(c, chart_dir, identity=ident)
    chart_text = (chart_dir / "Chart.yaml").read_text(encoding="utf-8")
    assert len(pattern.findall(chart_text)) >= 3
