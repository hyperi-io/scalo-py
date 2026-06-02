# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_golden.py
# Purpose:   Golden-file snapshot + determinism tests for python artefacts
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Golden snapshots of the generated Python deployment artefacts.

Each generated artefact is diffed byte-for-byte against a committed fixture
under ``tests/fixtures/deployment/``. Drift fails the build -- regenerate the
fixtures (and review the diff) when the generator output legitimately changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .support import py_contract

try:
    from hyperi_pylib.deployment import (
        DEPLOYMENT_AVAILABLE,
        ArgocdConfig,
        generate_argocd_application,
        generate_builder_stage,
        generate_container_manifest,
        generate_runtime_stage,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False

pytestmark = pytest.mark.skipif(
    not deployment_importable,
    reason="hyperi_pylib.deployment requires the [deployment] extra",
)

GOLDEN = Path(__file__).parent.parent.parent / "fixtures" / "deployment"


def _check(name: str, text: str) -> None:
    expected = (GOLDEN / name).read_text(encoding="utf-8")
    assert text == expected, f"golden drift: {name} -- regenerate tests/fixtures/deployment/"


def test_runtime_stage_golden():
    _check("Dockerfile.runtime", generate_runtime_stage(py_contract()))


def test_builder_stage_golden():
    _check("Dockerfile.builder", generate_builder_stage(py_contract()))


def test_container_manifest_golden():
    _check("container-manifest.json", generate_container_manifest(py_contract()))


def test_argocd_golden():
    argo = ArgocdConfig(repo_url="https://github.com/hyperi-io/dfe-api")
    _check("argocd-application.yaml", generate_argocd_application(py_contract(), argo))


def test_runtime_stage_deterministic():
    assert generate_runtime_stage(py_contract()) == generate_runtime_stage(py_contract())


def test_container_manifest_deterministic():
    assert generate_container_manifest(py_contract()) == generate_container_manifest(py_contract())
