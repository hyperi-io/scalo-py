# Project:   scalo
# File:      tests/unit/deployment/test_cli_generate_artefacts.py
# Purpose:   CLI integration test for the generate-artefacts subcommand
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Test the generate-artefacts CLI subcommand wired into ServiceApp."""

import json
from pathlib import Path

import pytest

try:
    from scalo.deployment import (
        DEPLOYMENT_AVAILABLE,
        DeploymentContract,
        HealthContract,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False


pytestmark = pytest.mark.skipif(
    not deployment_importable,
    reason="scalo.deployment requires the [deployment] extra",
)


def _build_app_class(contract_factory):
    """Build a one-off ServiceApp subclass that returns the given contract factory."""
    from scalo.cli import ServiceApp, VersionInfo

    class _TestApp(ServiceApp):
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
        image_registry="registry.example.com",
        entrypoint_args=["--config", "/etc/test/app.yaml"],
    )


@pytest.fixture
def argocd_cascade():
    """Set the retired ArgoCD source and namespace keys in the cascade for one test."""
    from scalo.config import settings

    settings.set("deployment.argocd.repo_url", "https://git.example.com/team/test-deploy-app")
    settings.set("deployment.argocd.dest_namespace", "probes")
    yield
    settings.unset("DEPLOYMENT")


class TestGenerateArtefactsHookDefault:
    """Default ServiceApp.deployment_contract() returns None."""

    def test_default_returns_none(self):
        from scalo.cli import ServiceApp, VersionInfo

        class _Bare(ServiceApp):
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

        # All artefacts present, and nothing else
        contract_path = tmp_path / "deployment-contract.json"
        manifest_path = tmp_path / "container-manifest.json"
        runtime_path = tmp_path / "Dockerfile.runtime"

        assert sorted(p.name for p in tmp_path.iterdir()) == [
            ".dockerignore",
            "Dockerfile.runtime",
            "container-manifest.json",
            "deployment-contract.json",
        ]

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

    def test_writes_no_argocd_application(self, tmp_path: Path, capsys, argocd_cascade):
        """A cascade that still names an ArgoCD repo gets no Application and no word about one."""
        AppCls = _build_app_class(_sample_contract)
        with pytest.raises(SystemExit) as exc_info:
            AppCls().cli(["generate-artefacts", "--output-dir", str(tmp_path)])
        assert exc_info.value.code == 0

        assert not (tmp_path / "argocd-application.yaml").exists()
        assert (tmp_path / "deployment-contract.json").is_file()
        err = capsys.readouterr().err
        assert "  Dockerfile.runtime" in err
        assert "argocd" not in err.lower()

    def test_help_claims_no_chart_or_application(self, capsys):
        # Issue #23: generate-artefacts emits no Helm chart or ArgoCD Application; help must not claim one.
        AppCls = _build_app_class(_sample_contract)
        with pytest.raises(SystemExit):
            AppCls().cli(["generate-artefacts", "--help"])
        out = capsys.readouterr().out
        assert "Helm" not in out
        assert "ArgoCD" not in out

    def test_warns_when_contract_is_none(self, tmp_path: Path, capsys):
        from scalo.cli import ServiceApp, VersionInfo

        class _NoContract(ServiceApp):
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
        assert not any(tmp_path.iterdir())

        # Warning printed to stderr
        err = capsys.readouterr().err
        assert "deployment_contract()" in err
        assert "no-contract-app" in err
        assert "argocd" not in err.lower()
