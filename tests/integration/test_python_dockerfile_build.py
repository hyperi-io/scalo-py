# Project:   hyperi-pylib
# File:      tests/integration/test_python_dockerfile_build.py
# Purpose:   Docker build smoke test for generated Python Dockerfiles (issue #22)
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Build smoke test for the generated Python deployment Dockerfile.

Lays down a minimal real ``uv`` app, writes the composed Dockerfile
(``generate_dockerfile`` = Astral uv builder + venv runtime), runs
``docker build``, and runs the entrypoint. Proves the generated artefact is
buildable end to end.

Skipped unless docker + uv are available (release CI provides both).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

try:
    from hyperi_pylib.deployment import (
        DEPLOYMENT_AVAILABLE,
        DeploymentContract,
        HealthContract,
        generate_dockerfile,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not deployment_importable, reason="requires the [deployment] extra"),
    pytest.mark.skipif(shutil.which("uv") is None, reason="requires uv"),
    pytest.mark.skipif(not _docker_available(), reason="requires a running docker daemon"),
]


def _write_minimal_uv_app(root: Path, binary: str) -> None:
    """Lay down a buildable zero-dependency uv app with a console script."""
    pkg = binary.replace("-", "_")
    pkg_dir = root / "src" / pkg
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("def main() -> None:\n    print('ok')\n", encoding="utf-8", newline="\n")
    (root / "pyproject.toml").write_text(
        f"[project]\n"
        f'name = "{binary}"\n'
        f'version = "0.0.0"\n'
        f'requires-python = ">=3.12"\n'
        f"dependencies = []\n"
        f"\n"
        f"[project.scripts]\n"
        f'{binary} = "{pkg}:main"\n'
        f"\n"
        f"[build-system]\n"
        f'requires = ["uv_build>=0.8.0,<1"]\n'
        f'build-backend = "uv_build"\n',
        encoding="utf-8",
        newline="\n",
    )
    subprocess.run(["uv", "lock"], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8")


def test_generated_python_dockerfile_builds(tmp_path: Path) -> None:
    binary = "smoke-app"
    _write_minimal_uv_app(tmp_path, binary)

    contract = DeploymentContract(
        app_name=binary,
        binary_name=binary,
        metrics_port=8000,
        health=HealthContract(),
        env_prefix="SMOKE",
        metric_prefix="smoke",
        config_mount_path="/etc/smoke/app.yaml",
        entrypoint_args=["run"],
    )
    (tmp_path / "Dockerfile").write_text(generate_dockerfile(contract), encoding="utf-8", newline="\n")

    # Clean docker config so the public base images pull anonymously,
    # regardless of any credential helper configured on the host.
    docker_cfg = tmp_path / "dockercfg"
    docker_cfg.mkdir()
    (docker_cfg / "config.json").write_text("{}", encoding="utf-8", newline="\n")
    env = {**os.environ, "DOCKER_CONFIG": str(docker_cfg)}

    tag = "hyperi-pylib-smoke-py:test"
    build = subprocess.run(
        ["docker", "build", "-t", tag, "-f", "Dockerfile", "."],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env=env,
    )
    try:
        assert build.returncode == 0, f"docker build failed:\n{build.stdout}\n{build.stderr}"
        run = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", binary, tag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=env,
        )
        assert run.returncode == 0, f"entrypoint failed:\n{run.stdout}\n{run.stderr}"
        assert "ok" in run.stdout
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, env=env)
