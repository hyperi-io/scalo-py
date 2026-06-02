# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_validate.py
# Purpose:   Tests for validate_dockerfile / validate_helm_values drift checks
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Drift-detection tests for the deployment validate_* functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from .support import py_contract

try:
    from hyperi_pylib.deployment import (
        DEPLOYMENT_AVAILABLE,
        generate_chart,
        generate_runtime_stage,
        validate_dockerfile,
        validate_helm_values,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False

pytestmark = pytest.mark.skipif(
    not deployment_importable,
    reason="hyperi_pylib.deployment requires the [deployment] extra",
)


def test_validate_dockerfile_clean(tmp_path: Path):
    p = tmp_path / "Dockerfile.runtime"
    p.write_text(generate_runtime_stage(py_contract()), encoding="utf-8")
    assert validate_dockerfile(py_contract(), p) == []


def test_validate_dockerfile_flags_wrong_expose(tmp_path: Path):
    p = tmp_path / "Dockerfile.runtime"
    p.write_text(generate_runtime_stage(py_contract()).replace("EXPOSE 8000", "EXPOSE 9999"), encoding="utf-8")
    issues = validate_dockerfile(py_contract(), p)
    assert any(m.field == "expose" for m in issues)


def test_validate_dockerfile_flags_wrong_base(tmp_path: Path):
    p = tmp_path / "Dockerfile.runtime"
    p.write_text(
        generate_runtime_stage(py_contract()).replace(
            "FROM python:3.12-slim AS runtime", "FROM ubuntu:24.04 AS runtime"
        ),
        encoding="utf-8",
    )
    issues = validate_dockerfile(py_contract(), p)
    assert any(m.field == "base_image" for m in issues)


def test_validate_helm_values_clean(tmp_path: Path):
    generate_chart(py_contract(), tmp_path)
    assert validate_helm_values(py_contract(), tmp_path) == []
