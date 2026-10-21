#  Project:   scalo
#  File:      src/scalo/_openapi.py
#  Purpose:   Stdlib-only OpenAPI pieces every spec reader shares: x-scalo, methods, $ref, media, parameters
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""What every scalo module that writes or reads an OpenAPI spec shares, so each reads it the same way.

Stdlib only: :mod:`scalo.cli.openapi` imports this without FastAPI, which
importing anything under :mod:`scalo.api` would load.
"""

from collections.abc import Mapping
from typing import Any

# The vendor extension scalo.api writes onto every operation.
EXTENSION = "x-scalo"

# The operation methods scalo reads, in the order the OpenAPI Path Item Object lists them.
METHODS = ("get", "put", "post", "delete", "patch")

# A ``$ref`` chain longer than this, or an ``allOf`` nested deeper, is treated as a cycle.
MAX_REF_HOPS = 32

# Headers a client sets itself or a proxy owns, so no generated command or tool takes one as input.
_RESERVED_HEADERS = frozenset(
    {"accept", "authorization", "content-length", "content-type", "forwarded", "host", "x-real-ip"}
)
_RESERVED_HEADER_PREFIXES = ("x-forwarded-", "x-oidc-")


def unescape_pointer(segment: str) -> str:
    """One JSON pointer segment as the key it names: ``~1`` is ``/``, ``~0`` is ``~`` (RFC 6901)."""
    return segment.replace("~1", "/").replace("~0", "~")


class RefResolver:
    """Follows local ``$ref`` pointers (``#/components/...``) in one spec.

    A pointer that leads nowhere resolves to an empty schema rather than raising,
    so one stray reference never takes the whole document down.
    """

    def __init__(self, spec: Mapping[str, Any]) -> None:
        self._spec = spec

    def target(self, ref: str) -> Any:
        """The value a local JSON pointer names, ``None`` when it names nothing."""
        if not ref.startswith("#/"):
            return None
        node: Any = self._spec
        for raw in ref[2:].split("/"):
            key = unescape_pointer(raw)
            if not isinstance(node, Mapping) or key not in node:
                return None
            node = node[key]
        return node

    def resolve(self, value: Any) -> dict[str, Any]:
        """``value`` with its ``$ref`` chain followed, ``{}`` when it ends nowhere."""
        seen: set[str] = set()
        for _ in range(MAX_REF_HOPS):
            if not isinstance(value, Mapping):
                return {}
            ref = value.get("$ref")
            if not isinstance(ref, str):
                return dict(value)
            if ref in seen:
                return {}
            seen.add(ref)
            value = self.target(ref)
        return {}


def non_null_member(schema: Mapping[str, Any], resolver: RefResolver) -> Any | None:
    """The first ``anyOf`` or ``oneOf`` member that is not ``{"type": "null"}``, as written, else ``None``."""
    for key in ("anyOf", "oneOf"):
        for member in schema.get(key) or ():
            if resolver.resolve(member).get("type") != "null":
                return member
    return None


def non_null_type(schema: Mapping[str, Any]) -> Any:
    """The schema's ``type``, or its first non-null entry when it is a list such as ``["string", "null"]``."""
    raw = schema.get("type")
    if isinstance(raw, list):
        return next((name for name in raw if name != "null"), None)
    return raw


def is_read_only(schema: Any, resolver: RefResolver) -> bool:
    """Whether a property is ``readOnly``, directly, through its ``$ref`` or inside a nullable wrapper."""
    resolved = resolver.resolve(schema)
    if resolved.get("readOnly") is True:
        return True
    member = non_null_member(resolved, resolver)
    return member is not None and resolver.resolve(member).get("readOnly") is True


def merge_all_of(schema: Any, resolver: RefResolver) -> tuple[dict[str, Any], list[str]]:
    """The ``properties`` and ``required`` of an object schema, through ``$ref`` and ``allOf``.

    Each ``$ref`` is merged once per call: a schema that names itself ends, and
    one that many members share costs one visit rather than one per path to it.

    Args:
        schema: The object schema, resolved or not.
        resolver: Follows the members' references.

    Returns:
        ``(properties, required)``. Later members win a property clash.
    """
    return _merge_all_of(schema, resolver, set(), 0)


def _merge_all_of(schema: Any, resolver: RefResolver, seen: set[str], depth: int) -> tuple[dict[str, Any], list[str]]:
    ref = schema.get("$ref") if isinstance(schema, Mapping) else None
    if isinstance(ref, str):
        if ref in seen:
            return {}, []
        seen.add(ref)
    resolved = resolver.resolve(schema)
    properties: dict[str, Any] = dict(resolved.get("properties") or {})
    required: list[str] = [name for name in resolved.get("required") or () if isinstance(name, str)]
    if depth < MAX_REF_HOPS:
        for member in resolved.get("allOf") or ():
            member_properties, member_required = _merge_all_of(member, resolver, seen, depth + 1)
            properties.update(member_properties)
            required.extend(name for name in member_required if name not in required)
    return properties, required


def is_json_media_type(media_type: str) -> bool:
    """``application/json`` or a ``+json`` structured suffix, in any case, as a spec key or a ``Content-Type``."""
    essence = media_type.split(";")[0].strip().lower()
    return essence == "application/json" or essence.endswith("+json")


def json_media(content: Any) -> Mapping[str, Any] | None:
    """The first JSON media type entry of a ``content`` map, ``application/merge-patch+json`` included."""
    if not isinstance(content, Mapping):
        return None
    for media_type, entry in content.items():
        if is_json_media_type(str(media_type)) and isinstance(entry, Mapping):
            return entry
    return None


def is_reserved_header(name: str) -> bool:
    """Whether a header is one the client sets itself or a proxy owns, so never a caller's input."""
    lower = name.lower()
    return lower in _RESERVED_HEADERS or lower.startswith(_RESERVED_HEADER_PREFIXES)


def wire_value(value: Any) -> Any:
    """A value as a query string or header carries it: booleans as ``true`` and ``false``, lists item by item."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | tuple):
        return [wire_value(item) for item in value]
    return value


def merged_parameters(
    item: Mapping[str, Any], operation: Mapping[str, Any], resolver: RefResolver
) -> list[dict[str, Any]]:
    """Path-item and operation parameters, resolved, the operation's winning a clash.

    Args:
        item: The path item, whose ``parameters`` every operation under it shares.
        operation: The operation.
        resolver: Follows the parameters' references.

    Returns:
        One resolved parameter per ``(in, name)``, in first-seen order. A parameter
        without a string ``in`` and ``name`` is left out.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in [*(item.get("parameters") or ()), *(operation.get("parameters") or ())]:
        parameter = resolver.resolve(raw)
        location, name = parameter.get("in"), parameter.get("name")
        if isinstance(location, str) and isinstance(name, str):
            merged[(location, name)] = parameter
    return list(merged.values())
