# Project:   scalo
# File:      deployment/emit.py
# Purpose:   Emit + drift-check reflectable config artefacts (scalo-py#3)
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Emission of the reflectable config artefacts (Python side).

Mirrors ``scalo::deployment::emit`` in scalo-rs. Given a ``DeploymentContract``
carrying ``config_schema`` and/or ``capabilities``, write the four artefact
files (same names + shape as the Rust side):

    config-schema.json / .yaml       -- derived JSON Schema of the app Config
    capability-catalog.json / .yaml  -- the hand-authored capability catalog

Output is deterministic (stable key order, no timestamps) so a committed copy
can be drift-checked against a fresh regeneration. See
``docs/reflectable-config-shape.md`` in scalo-rs for the cross-language shape.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .errors import DeploymentError

if TYPE_CHECKING:
    from pydantic import BaseModel

    from .contract import DeploymentContract


_SECRET_MARKER = "x-scalo-secret"  # noqa: S105 - a schema keyword, not a credential
"""The schema keyword that marks a field as credential material."""

DIAL_KEYWORD = "x-scalo-dial"
"""The schema keyword that marks a config setting as an operator dial, set with ``json_schema_extra``."""

DIAL_TIERS = ("big", "small")
"""The values ``DIAL_KEYWORD`` takes: a setting most deployments tune, and one a few do."""


def config_schema_json(model: type[BaseModel]) -> dict[str, Any]:
    """Derive a JSON Schema (draft 2020-12) for a pydantic config model.

    Secret fields are marked ``x-scalo-secret`` so the control plane masks them
    and routes them through the secrets seam. A field is treated as secret when
    it uses pydantic ``SecretStr`` (schema ``format: password``) or carries an
    explicit ``json_schema_extra={"x-scalo-secret": True}``. A secret field ends
    ``"x-scalo-secret": true, "writeOnly": true``, the keys and order scalo-rs's
    ``SensitiveString`` emits.
    """
    schema = model.model_json_schema()
    _mark_secrets(schema)
    return schema


def _mark_secrets(node: Any) -> None:
    """Recursively end every secret field with the marker and ``writeOnly``."""
    if isinstance(node, dict):
        is_secret = node.get("format") == "password" or node.get(_SECRET_MARKER) is True
        if is_secret:
            for key in (_SECRET_MARKER, "writeOnly"):
                node.pop(key, None)
                node[key] = True
        for value in node.values():
            _mark_secrets(value)
    elif isinstance(node, list):
        for item in node:
            _mark_secrets(item)


def _render(contract: DeploymentContract) -> list[tuple[str, str]]:
    """Render the (filename, content) pairs a contract would emit.

    Shared by :func:`emit_config_artifacts` and the drift check so the two never
    diverge. Only emits schema files when ``config_schema`` is set, and catalog
    files when ``capabilities`` is non-empty.
    """
    out: list[tuple[str, str]] = []

    schema = getattr(contract, "config_schema", None)
    if schema is not None:
        out.append(("config-schema.json", _to_json(schema)))
        out.append(("config-schema.yaml", _to_yaml(schema)))

    capabilities = getattr(contract, "capabilities", None) or []
    if capabilities:
        cap_dicts = [c.model_dump() for c in capabilities]
        out.append(("capability-catalog.json", _to_json(cap_dicts)))
        out.append(("capability-catalog.yaml", _to_yaml(cap_dicts)))

    return out


def _to_json(value: Any) -> str:
    """Pretty JSON with a single trailing newline (POSIX text file); NaN and Infinity raise, since no JSON reader takes them."""
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False, allow_nan=False) + "\n"


def _to_yaml(value: Any) -> str:
    """Deterministic YAML (insertion order preserved, no aliases)."""
    return yaml.safe_dump(value, sort_keys=False, default_flow_style=False, allow_unicode=True)


def emit_config_artifacts(contract: DeploymentContract, out_dir: str | Path) -> list[Path]:
    """Emit the reflectable config artefacts for ``contract`` into ``out_dir``.

    Creates ``out_dir`` if needed. Returns the paths written (0, 2, or 4 files).

    Raises:
        DeploymentError: if the directory cannot be created or a file written.
    """
    directory = Path(out_dir)
    artefacts = _render(contract)
    if not artefacts:
        return []

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover -- fs failure
        raise DeploymentError(f"failed to create directory {directory}: {exc}") from exc

    written: list[Path] = []
    for name, content in artefacts:
        path = directory / name
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:  # pragma: no cover -- fs failure
            raise DeploymentError(f"failed to write {path}: {exc}") from exc
        written.append(path)
    return written


def check_config_artifact_drift(contract: DeploymentContract, out_dir: str | Path) -> None:
    """Assert the committed artefacts under ``out_dir`` match a fresh regen.

    Use in an app's test suite so the normal test job fails if the checked-in
    ``config-schema.*`` / ``capability-catalog.*`` drift from the current Config
    / catalog.

    Raises:
        DeploymentError: if a committed file is missing or its bytes differ.
    """
    directory = Path(out_dir)
    for name, content in _render(contract):
        path = directory / name
        if not path.exists():
            raise DeploymentError(
                f"config artefact drift in {path}: missing -- run the app's "
                f"config-schema/generate-artefacts command and commit the output"
            )
        committed = path.read_text(encoding="utf-8")
        if committed != content:
            raise DeploymentError(
                f"config artefact drift in {path}: committed content differs from the "
                f"generated output ({len(committed)} vs {len(content)} bytes). "
                f"Regenerate and commit."
            )


assert_no_config_artifact_drift = check_config_artifact_drift


__all__ = [
    "DIAL_KEYWORD",
    "DIAL_TIERS",
    "assert_no_config_artifact_drift",
    "check_config_artifact_drift",
    "config_schema_json",
    "emit_config_artifacts",
]
