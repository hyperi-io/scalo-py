# Project:   hyperi-pylib
# File:      deployment/validate.py
# Purpose:   Validate existing deployment artefacts against the contract
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Drift checks: compare a committed artefact against the contract.

A programmatic alternative to a hard regenerate-and-diff in CI -- useful when
the committed artefact intentionally deviates (e.g. CI prepends its own builder
stage). Each function returns a list of :class:`ContractMismatch`; an empty
list means no drift.
"""

from __future__ import annotations

from pathlib import Path

from .contract import DeploymentContract
from .errors import ContractMismatch


def validate_dockerfile(contract: DeploymentContract, path: Path | str) -> list[ContractMismatch]:
    """Check a runtime/full Dockerfile against the Python contract.

    Verifies the runtime base image, exposed metrics port, venv ``PATH``, and
    the console-script entrypoint. Returns one :class:`ContractMismatch` per
    discrepancy (empty list = clean).
    """
    text = Path(path).read_text(encoding="utf-8")
    issues: list[ContractMismatch] = []

    base = contract.effective_base_image()
    if f"FROM {base}" not in text:
        issues.append(ContractMismatch("base_image", f"FROM {base}", "absent"))

    port = str(contract.metrics_port)
    if not any(line.startswith("EXPOSE") and port in line.split() for line in text.splitlines()):
        issues.append(ContractMismatch("expose", f"EXPOSE {port}", "absent"))

    if 'ENV PATH="/app/.venv/bin:$PATH"' not in text:
        issues.append(ContractMismatch("venv_path", "/app/.venv/bin on PATH", "absent"))

    entrypoint = f'ENTRYPOINT ["{contract.binary()}"]'
    if entrypoint not in text:
        issues.append(ContractMismatch("entrypoint", entrypoint, "absent"))

    return issues


def validate_helm_values(contract: DeploymentContract, chart_dir: Path | str) -> list[ContractMismatch]:
    """Check a Helm chart's ``values.yaml`` against the contract.

    Verifies the image repository and the service (metrics) port. Returns one
    :class:`ContractMismatch` per discrepancy (empty list = clean).
    """
    import yaml

    values_path = Path(chart_dir) / "values.yaml"
    values = yaml.safe_load(values_path.read_text(encoding="utf-8")) or {}
    issues: list[ContractMismatch] = []

    want_repo = f"{contract.image_registry}/{contract.app_name}"
    got_repo = (values.get("image") or {}).get("repository")
    if got_repo != want_repo:
        issues.append(ContractMismatch("image.repository", want_repo, str(got_repo)))

    got_port = (values.get("service") or {}).get("port")
    if got_port != contract.metrics_port:
        issues.append(ContractMismatch("service.port", str(contract.metrics_port), str(got_port)))

    return issues


__all__ = ["validate_dockerfile", "validate_helm_values"]
