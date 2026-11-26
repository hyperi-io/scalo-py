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
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .errors import DeploymentError

if TYPE_CHECKING:
    from pydantic import BaseModel

    from .capability import Capability, FieldSpec
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
    and reads them through the secrets provider. A field is treated as secret when
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
    / catalog, or if the catalogue and the schema disagree (see
    :func:`check_catalogue_against_schema`).

    Raises:
        DeploymentError: if the catalogue and schema disagree, or a committed
            file is missing or its bytes differ.
    """
    directory = Path(out_dir)
    if findings := check_catalogue_against_schema(contract):
        lines = "\n".join(f"  {finding}" for finding in findings)
        raise DeploymentError(
            f"config artefact drift in {directory / 'capability-catalog.json'}: the capability "
            f"catalogue and the config schema disagree. Set each field's schema_path to the "
            f"dotted path of the config option it describes, and make a closed-set option an "
            f"enum in the Config so the schema allows exactly the field's enum_values. Then "
            f"regenerate with the app's config-schema/generate-artefacts command into "
            f"{directory} and commit the result.\n{lines}"
        )
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


_MAX_SCHEMA_DEPTH = 32
"""How many ``$ref`` and ``allOf`` / ``anyOf`` / ``oneOf`` steps one lookup takes before it gives up, so definitions that refer to each other can't loop."""

_STEP_TOKENS = ("[]", "{}")
"""The suffixes a ``schema_path`` segment takes after its name: an array's items and a map's values."""


def check_catalogue_against_schema(contract: DeploymentContract) -> list[str]:
    """Check every catalogue field against the config option it describes.

    A field's ``schema_path`` must name an option in ``contract.config_schema``.
    A field with ``enum_values`` needs a ``schema_path``, and that option must
    allow the same set of values, as ``enum`` or ``const``. A field with neither
    isn't checked. Walks every capability and its children.
    ``docs/reflectable-config-shape.md`` in scalo-rs has the rules a path
    resolves by.

    Args:
        contract: The contract whose catalogue and schema are compared.

    Returns:
        One line per finding, in catalogue order. Empty when the two agree.
    """
    findings: list[str] = []
    for capability in getattr(contract, "capabilities", None) or []:
        _check_capability(getattr(contract, "config_schema", None), capability, "", findings)
    return findings


def _check_capability(schema: Any, capability: Capability, parent: str, findings: list[str]) -> None:
    """Append a finding for each field of ``capability`` and its children that disagrees with ``schema``."""
    location = f"{parent}/{capability.name}" if parent else capability.name
    for field in capability.fields:
        if finding := _check_field(schema, field):
            findings.append(f"capability {location}, field {field.name}: {finding}")
    for child in capability.children:
        _check_capability(schema, child, location, findings)


def _check_field(schema: Any, field: FieldSpec) -> str | None:
    """What disagrees between ``field`` and ``schema``, if anything."""
    want = set(field.enum_values)
    path = field.schema_path
    if path is None:
        if want:
            return f"enum_values {_listed(want)} but no schema_path, so the schema can't be checked to allow them"
        return None
    if schema is None:
        return f'schema_path "{path}" is set but the contract has no config_schema'
    try:
        node = _resolve_path(schema, path)
    except _PathError as exc:
        return f'schema_path "{path}" names no option in the config schema ({exc})'
    if not want:
        return None
    have = _closed_set(schema, node, 0)
    if have is None:
        return f'enum_values {_listed(want)} but "{path}" in the schema has no enum'
    if have != want:
        return f'enum_values {_listed(want)} but "{path}" in the schema allows {_listed(have)}'
    return None


def _listed(values: set[str]) -> str:
    """``values`` sorted, as a bracketed list of quoted strings."""
    return "[" + ", ".join(json.dumps(value, ensure_ascii=False) for value in sorted(values)) + "]"


class _PathError(ValueError):
    """Why a ``schema_path`` names no option."""


def _parse_segment(segment: str) -> tuple[str, list[str]] | None:
    """A segment's name and the ``[]`` / ``{}`` tokens after it, or ``None`` when it is not a name followed only by those."""
    cut = next((i for i, char in enumerate(segment) if char in "[{"), len(segment))
    name, rest = segment[:cut], segment[cut:]
    if not name:
        return None
    steps: list[str] = []
    while rest:
        step = rest[:2]
        if step not in _STEP_TOKENS:
            return None
        steps.append(step)
        rest = rest[2:]
    return name, steps


def _resolve_path(root: Any, path: str) -> Any:
    """The schema node at dotted ``path`` under ``root``.

    Raises:
        _PathError: with the reason there is no such node.
    """
    node = root
    walked = ""
    for segment in path.split("."):
        if not segment:
            raise _PathError("the path has an empty segment")
        parsed = _parse_segment(segment)
        if parsed is None:
            raise _PathError(f'segment "{segment}" is not a name followed by any of [] and {{}}')
        name, steps = parsed
        found = _find(root, node, lambda n, name=name: _property(n, name), 0)
        if found is None:
            where = f'under "{walked}"' if walked else "at the top level"
            raise _PathError(f'no "{name}" {where}')
        node = found
        walked = f"{walked}.{name}" if walked else name
        for step in steps:
            found = _take_step(root, node, step)
            if found is None:
                raise _PathError(_step_failure(root, node, step, walked, segment))
            node = found
            walked += step
    return node


def _step_failure(root: Any, node: Any, step: str, walked: str, segment: str) -> str:
    """Why ``step`` can't step into ``node``."""
    if step == "[]":
        if _find(root, node, lambda n: n.get("prefixItems"), 0) is not None:
            return f'"{walked}" is a tuple (prefixItems), which [] can\'t step into (segment "{segment}")'
        return f'"{walked}" is not an array (segment "{segment}")'
    return f'"{walked}" is not a map (segment "{segment}")'


def _property(node: dict[str, Any], name: str) -> Any:
    """The ``properties`` entry ``name`` of ``node``, if it has one."""
    properties = node.get("properties")
    return properties.get(name) if isinstance(properties, dict) else None


def _array_items(node: dict[str, Any]) -> Any:
    """An array's object ``items``."""
    items = node.get("items")
    return items if isinstance(items, dict) else None


def _map_values(node: dict[str, Any]) -> Any:
    """A map's value schema: its object ``additionalProperties``, else its one ``patternProperties`` value."""
    extra = node.get("additionalProperties")
    if isinstance(extra, dict):
        return extra
    patterns = node.get("patternProperties")
    if isinstance(patterns, dict) and len(patterns) == 1:
        return next(iter(patterns.values()))
    return None


def _take_step(root: Any, node: Any, step: str) -> Any:
    """The schema ``step`` leads to from ``node``: an array's items or a map's values."""
    return _find(root, node, _array_items if step == "[]" else _map_values, 0)


def _find(root: Any, node: Any, select: Callable[[dict[str, Any]], Any], depth: int) -> Any:
    """The first subschema ``select`` picks from ``node``, looked up through ``$ref`` and every ``allOf`` / ``anyOf`` / ``oneOf`` arm."""
    if depth > _MAX_SCHEMA_DEPTH or not isinstance(node, dict):
        return None
    if (found := select(node)) is not None:
        return found
    if (target := _follow_ref(root, node)) is not None and (
        found := _find(root, target, select, depth + 1)
    ) is not None:
        return found
    for key in ("allOf", "anyOf", "oneOf"):
        arms = node.get(key)
        if isinstance(arms, list):
            for arm in arms:
                if (found := _find(root, arm, select, depth + 1)) is not None:
                    return found
    return None


def _closed_set(root: Any, node: Any, depth: int) -> set[str] | None:
    """The closed set of values ``node`` allows, from ``enum`` or ``const``.

    Looks through ``$ref``, the union of ``anyOf`` / ``oneOf`` arms and the
    intersection of ``allOf`` arms. ``null`` is left out. ``None`` when the set
    is open.
    """
    if depth > _MAX_SCHEMA_DEPTH or not isinstance(node, dict):
        return None
    if isinstance(values := node.get("enum"), list):
        return {text for value in values if (text := _value_text(value)) is not None}
    if "const" in node:
        text = _value_text(node["const"])
        return set() if text is None else {text}
    if "$ref" in node:
        target = _follow_ref(root, node)
        return None if target is None else _closed_set(root, target, depth + 1)
    if isinstance(arms := node.get("allOf"), list):
        sets = [found for arm in arms if (found := _closed_set(root, arm, depth + 1)) is not None]
        return set.intersection(*sets) if sets else None
    for key in ("anyOf", "oneOf"):
        if isinstance(arms := node.get(key), list):
            union: set[str] = set()
            for arm in arms:
                if isinstance(arm, dict) and arm.get("type") == "null":
                    continue
                found = _closed_set(root, arm, depth + 1)
                if found is None:
                    return None
                union |= found
            return union
    return None


def _value_text(value: Any) -> str | None:
    """An enum value as the catalogue writes it, or ``None`` for ``null``."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _follow_ref(root: Any, node: dict[str, Any]) -> Any:
    """The node ``node``'s ``$ref`` points at, when it is a local JSON pointer into ``root`` over objects."""
    reference = node.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#"):
        return None
    target = root
    for part in reference[1:].split("/"):
        if not part:
            continue
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or key not in target:
            return None
        target = target[key]
    return target


assert_no_config_artifact_drift = check_config_artifact_drift


__all__ = [
    "DIAL_KEYWORD",
    "DIAL_TIERS",
    "assert_no_config_artifact_drift",
    "check_catalogue_against_schema",
    "check_config_artifact_drift",
    "config_schema_json",
    "emit_config_artifacts",
]
