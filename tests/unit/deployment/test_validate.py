# Project:   scalo
# File:      tests/unit/deployment/test_validate.py
# Purpose:   Tests for validate_dockerfile / validate_helm_values drift checks
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Drift-detection tests for the deployment validate_* functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from .support import py_contract

try:
    from scalo.deployment import (
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
    reason="scalo.deployment requires the [deployment] extra",
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


def test_validate_dockerfile_accepts_arg_parameterised_base(tmp_path: Path):
    # The container standard's parameterise-the-base pattern: `ARG BASE_IMAGE=<pinned>`
    # + `FROM ${BASE_IMAGE}`. The resolved base equals the contract base, so a
    # substring search for `FROM <pinned>` would wrongly flag drift - it must not.
    base = py_contract().effective_base_image()
    runtime = generate_runtime_stage(py_contract()).replace(f"FROM {base} AS runtime", "FROM ${BASE_IMAGE} AS runtime")
    p = tmp_path / "Dockerfile.runtime"
    p.write_text(f"ARG BASE_IMAGE={base}\n{runtime}", encoding="utf-8")
    assert not any(m.field == "base_image" for m in validate_dockerfile(py_contract(), p))


def test_validate_dockerfile_flags_arg_default_that_drifts(tmp_path: Path):
    # ARG resolution must not paper over a genuinely wrong pin: an ARG default
    # that resolves to a different base is still drift.
    base = py_contract().effective_base_image()
    runtime = generate_runtime_stage(py_contract()).replace(f"FROM {base} AS runtime", "FROM ${BASE_IMAGE} AS runtime")
    p = tmp_path / "Dockerfile.runtime"
    p.write_text(f"ARG BASE_IMAGE=ubuntu:24.04\n{runtime}", encoding="utf-8")
    assert any(m.field == "base_image" for m in validate_dockerfile(py_contract(), p))


def test_validate_helm_values_clean(tmp_path: Path):
    generate_chart(py_contract(), tmp_path)
    assert validate_helm_values(py_contract(), tmp_path) == []
