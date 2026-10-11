# Project:   scalo
# File:      tests/unit/deployment/test_identity_wiring.py
# Purpose:   Verify ContractIdentity wiring into the three image generators
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Wiring tests for Contract Identity v1.

For each of the three generators (`generate_runtime_stage`,
`generate_container_manifest`, `generate_dockerfile`):

- ``identity=None`` -> output byte-for-byte unchanged from the
  pre-identity baseline (opt-in safety).
- ``identity=<id>`` -> the three ``<namespace>.contract.*`` keys land in
  the expected location, ``io.scalo`` unless the contract names its own.

A cross-surface grep invariant ensures every artefact carries the
canonical key prefix when identity is supplied.
"""

import json
import re

from scalo.deployment import (
    DeploymentContract,
    HealthContract,
    ImageProfile,
    KedaContract,
    NativeDepsContract,
    OciLabels,
    SecretEnvContract,
    SecretGroupContract,
    generate_container_manifest,
    generate_dockerfile,
    generate_runtime_stage,
)
from scalo.deployment.contract_identity import ContractIdentity

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


# ---------------------------------------------------------------------------
# generate_runtime_stage
# ---------------------------------------------------------------------------


def test_runtime_stage_identity_none_unchanged_from_baseline() -> None:
    c = _make_contract()
    # Baseline: explicit None must produce the same string as no-arg call
    assert generate_runtime_stage(c, identity=None) == generate_runtime_stage(c)


def test_runtime_stage_identity_none_has_no_contract_keys() -> None:
    out = generate_runtime_stage(_make_contract(), identity=None)
    assert "io.scalo.contract" not in out


def test_runtime_stage_with_identity_emits_three_labels() -> None:
    out = generate_runtime_stage(_make_contract(), identity=_make_identity())
    assert f'LABEL io.scalo.contract.version="v1"' in out
    assert f'LABEL io.scalo.contract.source-commit="{VALID_SHA}"' in out
    assert f'LABEL io.scalo.contract.image-ref="{VALID_REF}"' in out


def test_runtime_stage_with_identity_inserts_after_profile_label() -> None:
    out = generate_runtime_stage(_make_contract(), identity=_make_identity())
    profile_pos = out.index("LABEL io.scalo.profile=")
    version_pos = out.index("LABEL io.scalo.contract.version=")
    assert profile_pos < version_pos, "contract labels must appear after profile label"


# ---------------------------------------------------------------------------
# generate_container_manifest
# ---------------------------------------------------------------------------


def test_container_manifest_identity_none_unchanged() -> None:
    c = _make_contract()
    assert generate_container_manifest(c, identity=None) == generate_container_manifest(c)


def test_container_manifest_identity_none_has_no_contract_keys() -> None:
    out = generate_container_manifest(_make_contract(), identity=None)
    assert "io.scalo.contract" not in out


def test_container_manifest_with_identity_emits_three_labels() -> None:
    out = generate_container_manifest(_make_contract(), identity=_make_identity())
    parsed = json.loads(out)
    labels = parsed["labels"]
    assert labels["io.scalo.contract.version"] == "v1"
    assert labels["io.scalo.contract.source-commit"] == VALID_SHA
    assert labels["io.scalo.contract.image-ref"] == VALID_REF


# ---------------------------------------------------------------------------
# generate_dockerfile (passes through to runtime stage path)
# ---------------------------------------------------------------------------


def test_dockerfile_identity_none_unchanged() -> None:
    c = _make_contract()
    assert generate_dockerfile(c, identity=None) == generate_dockerfile(c)


def test_dockerfile_identity_none_has_no_contract_keys() -> None:
    out = generate_dockerfile(_make_contract(), identity=None)
    assert "io.scalo.contract" not in out


def test_dockerfile_with_identity_emits_three_labels() -> None:
    out = generate_dockerfile(_make_contract(), identity=_make_identity())
    assert f'LABEL io.scalo.contract.version="v1"' in out
    assert f'LABEL io.scalo.contract.source-commit="{VALID_SHA}"' in out
    assert f'LABEL io.scalo.contract.image-ref="{VALID_REF}"' in out


# ---------------------------------------------------------------------------
# Cross-surface grep invariant
# ---------------------------------------------------------------------------


def test_every_scalo_key_follows_the_label_namespace() -> None:
    """Every key scalo stamps itself moves with label_namespace, and no default key is left behind."""
    c = _make_contract().model_copy(update={"oci_labels": OciLabels(label_namespace="com.example")})
    ident = _make_identity()

    surfaces = {
        "dockerfile": generate_dockerfile(c, identity=ident),
        "runtime_stage": generate_runtime_stage(c, identity=ident),
        "container_manifest": generate_container_manifest(c, identity=ident),
    }
    for name, text in surfaces.items():
        assert text.count("com.example.contract.") == 3, f"{name}:\n{text}"
        assert "io.scalo" not in text, f"{name} kept a default key:\n{text}"
    assert 'LABEL com.example.profile="production"' in surfaces["dockerfile"]
    assert 'LABEL com.example.profile="production"' in surfaces["runtime_stage"]
    labels = json.loads(surfaces["container_manifest"])["labels"]
    assert labels["com.example.profile"] == "production"
    assert labels["com.example.app"] == "dfe-loader"
    assert labels["com.example.metrics_port"] == "9090"


def test_all_surfaces_grep_for_io_scalo_contract() -> None:
    c = _make_contract()
    ident = _make_identity()

    pattern = re.compile(r"io\.scalo\.contract")

    surfaces = {
        "dockerfile": generate_dockerfile(c, identity=ident),
        "runtime_stage": generate_runtime_stage(c, identity=ident),
        "container_manifest": generate_container_manifest(c, identity=ident),
    }
    for name, text in surfaces.items():
        # Each surface must carry all three keys.
        assert len(pattern.findall(text)) >= 3, (
            f"{name}: expected >=3 occurrences of io.scalo.contract, got {len(pattern.findall(text))}"
        )
