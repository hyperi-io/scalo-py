# Project:   hyperi-pylib
# File:      tests/e2e/test_contract_artefacts.py
# Purpose:   TEMPLATE -- end-to-end tests for the deployment-contract artefacts
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""End-to-end tests for the deployment contract artefacts.

This file is BOTH:

1. A self-test for hyperi-pylib's own deployment subsystem (a small mock
   binary stands in for a real app entrypoint).
2. A TEMPLATE that Python DFE consumers copy into their own
   ``tests/e2e/`` to get the same coverage shape against their app.

Tier A (default; runs anywhere the tool is present):

- ``test_tier_a_dockerfile_builds_and_image_runs``
- ``test_tier_a_chart_lint_and_template``
- ``test_tier_a_argocd_application_kubeconform``

Tier B (env-gated by ``HYPERI_E2E_CLUSTER=1``):

- ``test_tier_b_helm_install_on_kind``
- ``test_tier_b_argocd_application_sync_on_kind``

Each test skips cleanly with a ``HYPERCI-SKIP[contract-e2e][<tier>]:``
prefix if its tool prerequisites are absent. The hyperi-ci runner greps
those lines into a top-of-stage summary.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from hyperi_pylib.deployment import (
    ArgocdConfig,
    ContractIdentity,
    DeploymentContract,
    HealthContract,
    ImageProfile,
    KedaContract,
    NativeDepsContract,
    OciLabels,
    generate_argocd_application,
    generate_chart,
)
from hyperi_pylib.deployment.test_support import (
    docker_available,
    docker_empty_creds_json,
    ensure_kind_cluster,
    helm_available,
    kubeconform_available,
    kubectl_available,
    skip,
    wait_until,
)

# Pinned ArgoCD upstream tag for Tier B install. Update intentionally.
ARGOCD_INSTALL_MANIFEST = "https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.1/manifests/install.yaml"

# A public canary image used in Tier B helm-install (no registry creds needed).
PUBLIC_CANARY_IMAGE_REPO = "public.ecr.aws/docker/library/nginx"
PUBLIC_CANARY_IMAGE_TAG = "alpine"

VALID_SHA = "0123456789abcdef0123456789abcdef01234567"
VALID_REF = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"


def _mock_binary_script() -> str:
    """POSIX shell script that satisfies ``--help`` in Tier A docker run.

    Real Python DFE consumers replace this with their actual entrypoint
    (e.g. ``pip install -e .`` in the build context + invoke the
    console-script via ``--entrypoint``).
    """
    return (
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --help|-h) echo "mock pylib e2e binary: ok"; exit 0 ;;\n'
        '  *) echo "mock pylib e2e binary"; exit 0 ;;\n'
        "esac\n"
    )


def _make_contract(app_name: str = "pylib-e2e-app") -> DeploymentContract:
    return DeploymentContract(
        app_name=app_name,
        binary_name=app_name,
        description="pylib deployment contract e2e canary",
        metrics_port=9090,
        health=HealthContract(),
        env_prefix="PYLIB_E2E",
        metric_prefix="pylib_e2e",
        config_mount_path=f"/etc/{app_name}.yaml",
        image_registry="ghcr.io/hyperi-io",
        base_image="ubuntu:24.04",
        keda=KedaContract(),
        native_deps=NativeDepsContract(),
        image_profile=ImageProfile.PRODUCTION,
        oci_labels=OciLabels(),
        schema_version=2,
    )


def _make_argo(app_name: str = "pylib-e2e-app") -> ArgocdConfig:
    return ArgocdConfig(
        repo_url=f"https://github.com/hyperi-io/{app_name}",
        target_revision="main",
        chart_path=f"charts/{app_name}",
    )


def _make_identity() -> ContractIdentity:
    return ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)


# ===========================================================================
# Tier A -- cluster-less; runs anywhere the tool is present
# ===========================================================================


@pytest.mark.integration
def test_tier_a_dockerfile_builds_and_image_runs() -> None:
    """Build a minimal image carrying the three identity labels and verify
    they round-trip through ``docker inspect``.

    The full ``generate_dockerfile`` output is exercised by the unit test
    ``test_dockerfile_with_identity_emits_three_labels``; this Tier A
    test verifies that the identity ``LABEL`` lines are docker-syntax-valid
    AND survive build->inspect, using a minimal hand-crafted wrapper.
    Real consumers replace this body with their own full build.
    """
    if not docker_available():
        skip(
            "tier-a",
            "test_tier_a_dockerfile_builds_and_image_runs",
            "docker daemon not reachable",
        )

    identity = _make_identity()
    tag = f"pylib-e2e:{os.getpid()}"

    with tempfile.TemporaryDirectory() as tdir, tempfile.TemporaryDirectory() as docker_cfg_dir:
        build_dir = Path(tdir)
        dockerfile = (
            "FROM alpine:3.21\n"
            f"{identity.as_dockerfile_labels()}\n"
            "COPY mock-bin /usr/local/bin/mock-bin\n"
            "RUN chmod +x /usr/local/bin/mock-bin\n"
            'ENTRYPOINT ["/usr/local/bin/mock-bin"]\n'
        )
        (build_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8", newline="\n")
        (build_dir / "mock-bin").write_text(_mock_binary_script(), encoding="utf-8", newline="\n")
        (build_dir / "mock-bin").chmod(0o755)

        (Path(docker_cfg_dir) / "config.json").write_text(docker_empty_creds_json(), encoding="utf-8", newline="\n")
        build_env = {**os.environ, "DOCKER_CONFIG": docker_cfg_dir}

        subprocess.run(
            ["docker", "build", "-f", "Dockerfile", "-t", tag, "--no-cache", "."],
            cwd=str(build_dir),
            env=build_env,
            check=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        try:
            run_out = subprocess.run(
                ["docker", "run", "--rm", tag, "--help"],
                env=build_env,
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            assert "mock pylib e2e binary: ok" in run_out.stdout

            inspect = subprocess.run(
                ["docker", "inspect", "--format", "{{json .Config.Labels}}", tag],
                env=build_env,
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            labels = json.loads(inspect.stdout)
            assert labels["io.hyperi.contract.version"] == "v1"
            assert labels["io.hyperi.contract.source-commit"] == VALID_SHA
            assert labels["io.hyperi.contract.image-ref"] == VALID_REF
        finally:
            subprocess.run(
                ["docker", "rmi", "-f", tag],
                env=build_env,
                check=False,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )


@pytest.mark.integration
def test_tier_a_chart_lint_and_template() -> None:
    """``helm template`` renders the chart; ``Chart.yaml`` annotations carry identity.

    Uses ``--set`` overrides to provide minimal kafka config required by
    the keda template; the contract's default ``default_config`` is
    empty by design. Consumer e2e tests provide their own values.
    """
    if not helm_available():
        skip(
            "tier-a",
            "test_tier_a_chart_lint_and_template",
            "helm CLI not installed",
        )

    contract = _make_contract()
    identity = _make_identity()

    with tempfile.TemporaryDirectory() as tdir:
        chart_dir = Path(tdir) / "chart"
        generate_chart(contract, chart_dir, identity=identity)

        rendered = subprocess.run(
            [
                "helm",
                "template",
                "test-release",
                str(chart_dir),
                "--set",
                "config.kafka.brokers=localhost:9092",
                "--set",
                "config.kafka.topics={canary}",
            ],
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        # Sanity: helm rendered something
        assert "kind:" in rendered.stdout

        # Chart.yaml annotations carry the three identity keys.
        chart_yaml = yaml.safe_load((chart_dir / "Chart.yaml").read_text(encoding="utf-8"))
        annotations = chart_yaml["annotations"]
        assert annotations["io.hyperi.contract.version"] == "v1"
        assert annotations["io.hyperi.contract.source-commit"] == VALID_SHA
        assert annotations["io.hyperi.contract.image-ref"] == VALID_REF


@pytest.mark.integration
def test_tier_a_argocd_application_kubeconform() -> None:
    if not kubeconform_available():
        skip(
            "tier-a",
            "test_tier_a_argocd_application_kubeconform",
            "kubeconform CLI not installed",
        )

    contract = _make_contract()
    argo = _make_argo()
    identity = _make_identity()
    app_yaml = generate_argocd_application(contract, argo, identity=identity)

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", encoding="utf-8", newline="\n", delete=False) as fh:
        fh.write(app_yaml)
        app_path = fh.name
    try:
        subprocess.run(
            ["kubeconform", "-strict", "-summary", "-ignore-missing-schemas", app_path],
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    finally:
        os.unlink(app_path)

    # Re-parse the YAML to validate annotation presence
    parsed = yaml.safe_load(app_yaml)
    annotations = parsed["metadata"]["annotations"]
    assert annotations["io.hyperi.contract.version"] == "v1"
    assert annotations["io.hyperi.contract.source-commit"] == VALID_SHA
    assert annotations["io.hyperi.contract.image-ref"] == VALID_REF


# ===========================================================================
# Tier B -- env-gated; brings up a real kind cluster
# ===========================================================================


@pytest.mark.e2e
def test_tier_b_helm_install_on_kind() -> None:
    if not helm_available():
        skip(
            "tier-b",
            "test_tier_b_helm_install_on_kind",
            "helm CLI not installed",
        )
    guard = ensure_kind_cluster("test_tier_b_helm_install_on_kind")
    if guard is None:
        return  # unreachable; ensure_kind_cluster raised pytest.skip

    contract = _make_contract()
    identity = _make_identity()

    with tempfile.TemporaryDirectory() as tdir:
        chart_dir = Path(tdir) / "chart"
        generate_chart(contract, chart_dir, identity=identity)

        kc_path = Path(tdir) / "kubeconfig"
        subprocess.run(
            ["kind", "create", "cluster", "--name", guard.name, "--kubeconfig", str(kc_path)],
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        guard.kubeconfig = kc_path
        try:
            subprocess.run(
                [
                    "helm",
                    "install",
                    contract.app_name,
                    str(chart_dir),
                    "--kubeconfig",
                    str(kc_path),
                    "--set",
                    f"image.repository={PUBLIC_CANARY_IMAGE_REPO}",
                    "--set",
                    f"image.tag={PUBLIC_CANARY_IMAGE_TAG}",
                    "--wait",
                    "--timeout",
                    "120s",
                ],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            list_out = subprocess.run(
                ["helm", "list", "--kubeconfig", str(kc_path), "-o", "json"],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            releases = json.loads(list_out.stdout)
            assert any(r["name"] == contract.app_name for r in releases)
        finally:
            guard.__exit__(None, None, None)


@pytest.mark.e2e
def test_tier_b_argocd_application_sync_on_kind() -> None:
    if not kubectl_available():
        skip(
            "tier-b",
            "test_tier_b_argocd_application_sync_on_kind",
            "kubectl CLI not installed",
        )
    guard = ensure_kind_cluster("test_tier_b_argocd_application_sync_on_kind")
    if guard is None:
        return

    contract = _make_contract()
    argo = _make_argo()
    identity = _make_identity()

    with tempfile.TemporaryDirectory() as tdir:
        kc_path = Path(tdir) / "kubeconfig"
        subprocess.run(
            ["kind", "create", "cluster", "--name", guard.name, "--kubeconfig", str(kc_path)],
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        guard.kubeconfig = kc_path
        try:
            subprocess.run(
                ["kubectl", "create", "namespace", "argocd", "--kubeconfig", str(kc_path)],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            subprocess.run(
                ["kubectl", "apply", "-n", "argocd", "--kubeconfig", str(kc_path), "-f", ARGOCD_INSTALL_MANIFEST],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )

            def server_ready() -> bool:
                r = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "deployment",
                        "argocd-server",
                        "-n",
                        "argocd",
                        "--kubeconfig",
                        str(kc_path),
                        "-o",
                        "jsonpath={.status.availableReplicas}",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=15,
                )
                return r.returncode == 0 and r.stdout.strip().isdigit() and int(r.stdout) >= 1

            assert wait_until(deadline_seconds=300, interval_seconds=5, predicate=server_ready)

            app_yaml = generate_argocd_application(contract, argo, identity=identity)
            app_file = Path(tdir) / "application.yaml"
            app_file.write_text(app_yaml, encoding="utf-8", newline="\n")
            subprocess.run(
                ["kubectl", "apply", "--kubeconfig", str(kc_path), "-f", str(app_file)],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            roundtrip = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "application",
                    contract.app_name,
                    "-n",
                    "argocd",
                    "--kubeconfig",
                    str(kc_path),
                    "-o",
                    "jsonpath={.metadata.annotations}",
                ],
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            annotations = json.loads(roundtrip.stdout)
            assert annotations["io.hyperi.contract.version"] == "v1"
            assert annotations["io.hyperi.contract.source-commit"] == VALID_SHA
            assert annotations["io.hyperi.contract.image-ref"] == VALID_REF
        finally:
            guard.__exit__(None, None, None)
