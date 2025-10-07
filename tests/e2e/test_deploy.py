import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _which(cmd: str) -> bool:
    from shutil import which

    return which(cmd) is not None


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=True)


def _venv_bin(venv_dir: Path, exe: str) -> Path:
    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    return bin_dir / exe


@pytest.mark.e2e
@pytest.mark.parametrize("license_id", ["hypersec-eula", "apache-2.0"])
@pytest.mark.parametrize("enable_gha", [False, True])
def test_template_deploy_flow(license_id: str, enable_gha: bool) -> None:
    # Opt-in to heavy e2e by setting RUN_E2E=1
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("Set RUN_E2E=1 to run e2e deployment tests")

    if not _which("copier"):
        pytest.skip("copier CLI not found in PATH")

    # Layout
    repo_root = Path(__file__).resolve().parents[1]
    template_src = repo_root
    base_dir = Path("/projects/test-templates")
    base_dir.mkdir(parents=True, exist_ok=True)
    project_name = "test_hypersec_forge_tpl_python_pkg"
    package_name = "test_hypersec_forge_tpl_python_pkg"
    dest = base_dir / project_name

    # Clean up existing test project
    if dest.exists():
        shutil.rmtree(dest)

    # Render with Copier
    copier_cmd = [
        "copier",
        "copy",
        "-f",
        "--trust",
        "--defaults",
        "-r",
        "HEAD",
        "-d",
        f"project_name={project_name}",
        "-d",
        f"package_name={package_name}",
        "-d",
        "description=E2E Deployment Test",
        "-d",
        "author_name=E2E Runner",
        "-d",
        "author_email=e2e@example.com",
        "-d",
        "github_org=hypersec-io",
        "-d",
        f"license={license_id}",
        "-d",
        f"enable_github_actions={'true' if enable_gha else 'false'}",
        str(template_src),
        str(dest),
    ]
    _run(copier_cmd)

    # Build the project
    build_venv = dest / ".venv-build"
    _run([sys.executable, "-m", "venv", str(build_venv)])
    python_build = str(_venv_bin(build_venv, "python"))
    pip_build = str(_venv_bin(build_venv, "pip"))
    _run([pip_build, "install", "-q", "build"])  # tooling only
    _run([python_build, "-m", "build"], cwd=dest)
    dist_dir = dest / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    sdists = list(dist_dir.glob("*.tar.gz"))
    assert wheels, "wheel not built"
    assert sdists, "sdist not built"

    # Install the built wheel in a fresh venv and import
    install_venv = dest / ".venv-install"
    _run([sys.executable, "-m", "venv", str(install_venv)])
    python_install = str(_venv_bin(install_venv, "python"))
    pip_install = str(_venv_bin(install_venv, "pip"))
    _run([pip_install, "install", "-q", str(wheels[0])])
    _run([python_install, "-c", f"import {package_name}; print({package_name}.__name__)"], cwd=dest)

    # Verify GitHub Actions workflow for JFrog deployment (e2e only)
    if os.environ.get("RUN_E2E") == "1" and enable_gha:
        # Verify that JFrog workflow is properly configured
        workflow_path = dest / ".github" / "workflows" / "jfrog-publish.yml"
        workflows_disabled_path = dest / ".github" / "workflows-disabled" / "jfrog-publish.yml"

        if workflow_path.exists():
            print("[OK] JFrog deployment workflow enabled at .github/workflows/")
            # Verify the workflow uses GitHub secrets
            workflow_content = workflow_path.read_text()
            required_secrets = [
                "secrets.ARTIFACTORY_USERNAME",
                "secrets.ARTIFACTORY_PASSWORD",
                "secrets.ARTIFACTORY_REPO_URL",
            ]
            for secret in required_secrets:
                assert secret in workflow_content, f"Missing required secret: {secret}"
            print("[OK] JFrog workflow correctly configured to use GitHub Secrets")

            # Verify the workflow has verification step
            assert "Verify package in JFrog Artifactory" in workflow_content, "Missing verification step"
            assert "pip install --no-cache-dir" in workflow_content, "Missing package installation verification"
            print("[OK] JFrog workflow includes post-publish verification step")
        else:
            assert workflows_disabled_path.exists(), "JFrog workflow not found in either location"
            print("[OK] JFrog deployment workflow disabled (in .github/workflows-disabled/)")

        # Verify local CI stays local
        local_ci_disabled = dest / ".github" / "workflows-disabled" / "local-ci.yml"
        local_ci_enabled = dest / ".github" / "workflows" / "local-ci.yml"
        assert local_ci_disabled.exists(), "Local CI workflow should remain in workflows-disabled"
        assert not local_ci_enabled.exists(), "Local CI should not be in workflows (runs locally via scripts/ci)"
        print("[OK] Local CI correctly configured to run locally (not via GitHub Actions)")

    # Optionally exercise local CI inside the rendered project
    if os.environ.get("RUN_E2E_CI") == "1":
        ci_script = dest / "scripts" / "ci"
        if ci_script.exists():
            ci_script.chmod(0o755)
            _run(["bash", str(ci_script)], cwd=dest)

    # GitHub Actions toggle (best-effort assertions)
    gh_disabled = dest / ".github" / "workflows-disabled"
    gh_enabled = dest / ".github" / "workflows"
    if gh_disabled.exists() or gh_enabled.exists():
        if enable_gha:
            assert gh_enabled.exists() or (not gh_disabled.exists()), "Expected workflows enabled or disabled removed"
        else:
            assert (
                not gh_enabled.exists() or gh_disabled.exists()
            ), "Expected workflows to remain disabled when not enabled"
