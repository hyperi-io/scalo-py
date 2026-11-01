# Project:   scalo
# File:      tests/e2e/test_contract_artefacts.py
# Purpose:   TEMPLATE -- end-to-end tests for the deployment-contract artefacts
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""End-to-end tests for the deployment contract artefacts.

This file is BOTH:

1. A self-test for scalo's own deployment subsystem (a small mock
   binary stands in for a real app entrypoint).
2. A TEMPLATE that Python DFE consumers copy into their own
   ``tests/e2e/`` to get the same coverage shape against their app.

Tier A (default; runs anywhere the tool is present):

- ``test_tier_a_dockerfile_builds_and_image_runs``

The Kubernetes objects come from the scalo-service library chart in
scalo-rs, which renders and validates them from the serialised contract.

The test skips cleanly with a ``HYPERCI-SKIP[contract-e2e][tier-a]:``
prefix if its tool prerequisites are absent. The hyperi-ci runner greps
those lines into a top-of-stage summary.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from scalo.deployment import (
    DEFAULT_LABEL_NAMESPACE,
    ContractIdentity,
)
from scalo.deployment.test_support import (
    docker_available,
    docker_build_cmd,
    docker_empty_creds_json,
    docker_env,
    skip,
)

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
        '  --help|-h) echo "mock scalo-py e2e binary: ok"; exit 0 ;;\n'
        '  *) echo "mock scalo-py e2e binary"; exit 0 ;;\n'
        "esac\n"
    )


def _make_identity() -> ContractIdentity:
    return ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)


# ===========================================================================
# Tier A -- cluster-less; runs anywhere the tool is present
# ===========================================================================


@pytest.mark.integration
@pytest.mark.full
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
    tag = f"scalo-py-e2e:{os.getpid()}"

    with tempfile.TemporaryDirectory() as tdir, tempfile.TemporaryDirectory() as docker_cfg_dir:
        build_dir = Path(tdir)
        dockerfile = (
            "FROM alpine:3.21\n"
            f"{identity.as_dockerfile_labels(DEFAULT_LABEL_NAMESPACE)}\n"
            "COPY mock-bin /usr/local/bin/mock-bin\n"
            "RUN chmod +x /usr/local/bin/mock-bin\n"
            'ENTRYPOINT ["/usr/local/bin/mock-bin"]\n'
        )
        (build_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8", newline="\n")
        (build_dir / "mock-bin").write_text(_mock_binary_script(), encoding="utf-8", newline="\n")
        (build_dir / "mock-bin").chmod(0o755)

        (Path(docker_cfg_dir) / "config.json").write_text(docker_empty_creds_json(), encoding="utf-8", newline="\n")
        build_env = docker_env(docker_cfg_dir)

        subprocess.run(
            docker_build_cmd(tag, no_cache=True),
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
            assert "mock scalo-py e2e binary: ok" in run_out.stdout

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
            assert labels["io.scalo.contract.version"] == "v1"
            assert labels["io.scalo.contract.source-commit"] == VALID_SHA
            assert labels["io.scalo.contract.image-ref"] == VALID_REF
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
