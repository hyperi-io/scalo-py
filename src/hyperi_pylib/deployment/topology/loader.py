# Project:   hyperi-pylib
# File:      deployment/topology/loader.py
# Purpose:   Load + validate topology.yaml into DeploymentTopology
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""YAML loader for DeploymentTopology declarations."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from hyperi_pylib.deployment.topology.errors import (
    TopologyError,
    TopologyValidationError,
)
from hyperi_pylib.deployment.topology.model import DeploymentTopology


def load_topology(path: Path | str) -> DeploymentTopology:
    """Load a topology.yaml file or directory.

    Args:
        path: Either a path to a ``topology.yaml`` file or a directory
            containing one.

    Returns:
        Parsed and validated ``DeploymentTopology``.

    Raises:
        TopologyError: file not found or unreadable.
        TopologyValidationError: malformed YAML or schema violation.
    """
    p = Path(path)
    if p.is_dir():
        p = p / "topology.yaml"
    if not p.exists():
        raise TopologyError(f"topology not found: {p}")

    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise TopologyError(f"failed to read {p}: {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise TopologyValidationError(
            f"malformed YAML: {exc}",
            path=str(p),
        ) from exc

    if not isinstance(data, dict):
        raise TopologyValidationError(
            "topology.yaml must be a mapping at the top level",
            path=str(p),
        )

    try:
        return DeploymentTopology.model_validate(data)
    except ValidationError as exc:
        raise TopologyValidationError(
            f"schema validation failed: {exc}",
            path=str(p),
        ) from exc
