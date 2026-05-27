# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_cli_generate_artefacts.py
# Purpose:   CLI integration test for the generate-artefacts subcommand
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Test the generate-artefacts CLI subcommand wired into DfeApp."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from hyperi_pylib.deployment import (
        DEPLOYMENT_AVAILABLE,
        DeploymentContract,
        HealthContract,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False


pytestmark = pytest.mark.skipif(
    not deployment_importable,
    reason="hyperi_pylib.deployment requires the [deployment] extra",
)


def _build_app_class(contract_factory):
    """Build a one-off DfeApp subclass that returns the given contract factory."""
    from hyperi_pylib.cli import DfeApp, VersionInfo

    class _TestApp(DfeApp):
        name = "test-deploy-app"
        env_prefix = "TEST_DEPLOY"

        def version_info(self) -> VersionInfo:
            return VersionInfo(self.name, "0.1.0")

        def run_service(self, config) -> None:  # pragma: no cover - never called
            pass

        def deployment_contract(self):
            return contract_factory()

    return _TestApp


def _sample_contract() -> DeploymentContract:
    return DeploymentContract(
        app_name="test-deploy-app",
        binary_name="test-deploy-app",
        description="CLI smoke",
        metrics_port=9091,
        health=HealthContract(),
        env_prefix="TEST_DEPLOY",
        metric_prefix="test",
        config_mount_path="/etc/test/app.yaml",
        entrypoint_args=["--config", "/etc/test/app.yaml"],
    )


class TestGenerateArtefactsHookDefault:
    """Default DfeApp.deployment_contract() returns None."""

    def test_default_returns_none(self):
        from hyperi_pylib.cli import DfeApp, VersionInfo

        class _Bare(DfeApp):
            name = "bare"
            env_prefix = "BARE"

            def version_info(self):
                return VersionInfo(self.name, "0.0.1")

            def run_service(self, config):
                pass

        assert _Bare().deployment_contract() is None


class TestGenerateArtefactsCli:
    """Invoke the generate-artefacts subcommand and check output files."""

    def test_writes_all_artefacts(self, tmp_path: Path):
        AppCls = _build_app_class(_sample_contract)
        app = AppCls()
        # Typer always sys.exit()s in standalone mode -- catch the success exit.
        with pytest.raises(SystemExit) as exc_info:
            app.cli(["generate-artefacts", "--output-dir", str(tmp_path)])
        assert exc_info.value.code == 0

        # All four artefacts present
        contract_path = tmp_path / "deployment-contract.json"
        manifest_path = tmp_path / "container-manifest.json"
        runtime_path = tmp_path / "Dockerfile.runtime"
        argo_path = tmp_path / "argocd-application.yaml"

        assert contract_path.exists()
        assert manifest_path.exists()
        assert runtime_path.exists()
        assert argo_path.exists()

        # Contract JSON round-trips
        contract = DeploymentContract.from_json(contract_path.read_text())
        assert contract.app_name == "test-deploy-app"

        # Manifest is valid JSON with the right shape
        manifest = json.loads(manifest_path.read_text())
        assert manifest["app_name"] == "test-deploy-app"
        assert manifest["binary_name"] == "test-deploy-app"

        # Runtime Dockerfile has expected fragment markers
        runtime = runtime_path.read_text()
        assert "AS runtime" in runtime
        assert "ARG OCI_SOURCE=" in runtime

        # ArgoCD application points at the cascade-derived repo URL
        argo = argo_path.read_text()
        assert "kind: Application" in argo
        assert "name: test-deploy-app" in argo
        assert "repoURL: https://github.com/hyperi-io/test-deploy-app" in argo

    def test_warns_when_contract_is_none(self, tmp_path: Path, capsys):
        from hyperi_pylib.cli import DfeApp, VersionInfo

        class _NoContract(DfeApp):
            name = "no-contract-app"
            env_prefix = "NCA"

            def version_info(self):
                return VersionInfo(self.name, "0.0.1")

            def run_service(self, config):
                pass

        with pytest.raises(SystemExit) as exc_info:
            _NoContract().cli(["generate-artefacts", "--output-dir", str(tmp_path)])
        assert exc_info.value.code == 0

        # Output directory was created but no artefacts written
        assert tmp_path.exists()
        assert not (tmp_path / "deployment-contract.json").exists()
        assert not (tmp_path / "argocd-application.yaml").exists()

        # Warning printed to stderr
        err = capsys.readouterr().err
        assert "deployment_contract()" in err
        assert "no-contract-app" in err
